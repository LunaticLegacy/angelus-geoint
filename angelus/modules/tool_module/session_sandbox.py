"""OS-enforced, session-scoped Shell execution using Bubblewrap.

This module deliberately receives one already-authorized workspace path rather
than an Angelus core or state root.  The resulting mount namespace makes that
workspace the only writable host location visible to an Agent command.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
from typing import Any

from llmfetcher import Tool, ToolParameter, ToolSchema
from llmfetcher.execution import current_execution_controller


class SessionSandboxError(ValueError):
    """Raised before an untrusted command reaches a host process."""


_RUNTIME_MOUNTS = ("/usr", "/usr/local", "/bin", "/sbin", "/lib", "/lib64", "/etc")
_MAX_OUTPUT_BYTES = 1_000_000
_MAX_ADDRESS_SPACE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_OPEN_FILES = 256


def resolve_sandbox_cwd(workspace: Path, requested_cwd: object) -> str:
    """Return a sandbox-internal cwd without accepting host path references."""
    if requested_cwd in {None, "", "/workspace"}:
        return "/workspace"
    if not isinstance(requested_cwd, str):
        raise SessionSandboxError("working directory must be a string")
    if requested_cwd.startswith("/workspace/"):
        requested_cwd = requested_cwd.removeprefix("/workspace/")
    candidate = PurePosixPath(requested_cwd)
    if candidate.is_absolute():
        raise SessionSandboxError("working directory must be /workspace or one of its subdirectories")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise SessionSandboxError("working directory must stay within /workspace")
    host_target = (workspace / Path(*candidate.parts)).resolve()
    try:
        host_target.relative_to(workspace)
    except ValueError as exc:
        raise SessionSandboxError("working directory must stay within /workspace") from exc
    if not host_target.is_dir():
        raise SessionSandboxError("working directory does not exist inside the session workspace")
    return f"/workspace/{candidate.as_posix()}"


def build_bwrap_command(workspace: Path, command: str, sandbox_cwd: str, *, sandbox_binary: str) -> list[str]:
    """Build a no-network mount namespace command without leaking host paths."""
    args = [
        sandbox_binary,
        "--die-with-parent", "--new-session",
        "--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-ipc", "--unshare-uts", "--hostname", "angelus-session",
        "--clearenv", "--setenv", "HOME", "/workspace", "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "--setenv", "LANG", "C.UTF-8", "--setenv", "LC_ALL", "C.UTF-8", "--setenv", "TMPDIR", "/tmp",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
    ]
    for value in _RUNTIME_MOUNTS:
        if Path(value).exists():
            args.extend(("--ro-bind", value, value))
    args.extend((
        "--bind", str(workspace), "/workspace", "--chdir", sandbox_cwd, "--",
        "/usr/bin/prlimit", f"--as={_MAX_ADDRESS_SPACE_BYTES}", f"--nofile={_MAX_OPEN_FILES}", "--",
        "/bin/sh", "-lc", command,
    ))
    return args


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass


def _result(process: subprocess.Popen[str], stdout: str, stderr: str) -> str:
    lines: list[str] = []
    if stdout:
        lines.append("[stdout]\n" + stdout.rstrip("\n"))
    if stderr:
        lines.append("[stderr]\n" + stderr.rstrip("\n"))
    if process.returncode != 0:
        lines.append(f"[exit code] {process.returncode}")
    return "\n".join(lines) if lines else "(no output)"


def create_session_shell_tool(workspace: Path, *, sandbox_binary: str = "bwrap", max_timeout: float = 60.0) -> Tool:
    """Create the one Shell tool permitted to see a session workspace.

    Bubblewrap is mandatory.  A missing or unusable installation produces a
    safe, user-visible error and never falls back to a host ``subprocess``.
    """
    root = workspace.resolve()
    if not root.is_dir():
        raise SessionSandboxError("session workspace is unavailable")

    def shell(**kwargs: Any) -> str:
        command = kwargs.get("command")
        if not isinstance(command, str) or not command.strip():
            return "Error: command must be a non-empty string"
        binary = shutil.which(sandbox_binary) if os.path.sep not in sandbox_binary else sandbox_binary
        if not binary or not Path(binary).is_file():
            return "Error: session sandbox is unavailable (bubblewrap is required; host Shell was not started)"
        try:
            cwd = resolve_sandbox_cwd(root, kwargs.get("cwd"))
        except SessionSandboxError as exc:
            return f"Error: {exc}"
        timeout = kwargs.get("timeout", 30.0)
        try:
            timeout = min(max(float(timeout), 1.0), max_timeout)
        except (TypeError, ValueError):
            return "Error: timeout must be a number"
        controller = current_execution_controller()
        if controller is not None and controller.force_stopped.is_set():
            return "Error: command force-stopped before execution"
        process: subprocess.Popen[str] | None = None
        unregister = None
        try:
            process = subprocess.Popen(
                build_bwrap_command(root, command, cwd, sandbox_binary=binary),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
            )
            if controller is not None:
                unregister = controller.register_force_canceller(lambda _request: _kill_process_group(process))
            stdout, stderr = process.communicate(timeout=timeout)
            if len(stdout.encode("utf-8", errors="replace")) + len(stderr.encode("utf-8", errors="replace")) > _MAX_OUTPUT_BYTES:
                return "Error: sandbox command output exceeded 1000000 bytes"
        except subprocess.TimeoutExpired:
            if process is not None:
                _kill_process_group(process)
                process.communicate()
            return f"Error: command timed out after {timeout:g} seconds"
        except Exception as exc:
            return f"Error: session sandbox failed to start ({exc})"
        finally:
            if unregister is not None:
                unregister()
        if controller is not None and controller.force_stopped.is_set():
            return "Error: command force-stopped during execution"
        assert process is not None
        return _result(process, stdout, stderr)

    return Tool(
        name="shell",
        description="在当前会话隔离工作区中执行 Shell 命令。网络、其他会话状态与宿主目录不可见。",
        schemas=ToolSchema(properties=[
            ToolParameter(name="command", type="string", description="在隔离工作区执行的 Shell 命令", required=True),
            ToolParameter(name="timeout", type="number", description=f"最大执行秒数（1–{max_timeout:g}）", default=30.0, required=False),
            ToolParameter(name="cwd", type="string", description="可选的 /workspace 子目录或相对目录", required=False),
        ]),
        handler=shell,
    )


__all__ = ["SessionSandboxError", "build_bwrap_command", "create_session_shell_tool", "resolve_sandbox_cwd"]
