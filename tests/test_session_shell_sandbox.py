"""Contract tests for the mandatory OS-level session Shell sandbox."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from angelus.modules.tool_module.session_sandbox import (
    SessionSandboxError,
    build_bwrap_command,
    create_session_shell_tool,
    resolve_sandbox_cwd,
)
from angelus.modules.settings_module.profile_store import DEFAULT_RUN_PROFILE


class SessionShellSandboxTests(unittest.TestCase):
    def test_new_session_profile_defaults_to_inheriting_service_network(self) -> None:
        self.assertEqual("host_network", DEFAULT_RUN_PROFILE["shell_network_mode"])

    def test_only_workspace_paths_are_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"; (workspace / "reports").mkdir(parents=True)
            self.assertEqual("/workspace", resolve_sandbox_cwd(workspace, None))
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(workspace, "reports"))
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(workspace, "/workspace/reports"))
            with self.assertRaises(SessionSandboxError): resolve_sandbox_cwd(workspace, "/home/luna")
            with self.assertRaises(SessionSandboxError): resolve_sandbox_cwd(workspace, "../other-session")

    def test_short_name_workspace_path_is_accepted(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows 8.3 short names are a Windows-only path form")
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "a-long-workspace-directory-name" / "workspace"
            (workspace / "reports").mkdir(parents=True)
            buffer = ctypes.create_unicode_buffer(1024)
            if not ctypes.windll.kernel32.GetShortPathNameW(str(workspace), buffer, len(buffer)):
                self.skipTest("8.3 short name generation is disabled on this volume")
            short_workspace = Path(buffer.value)
            if short_workspace == workspace:
                self.skipTest("this path has no distinct 8.3 short name")
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(short_workspace, "reports"))

    def test_unnormalised_workspace_path_is_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            (workspace / "reports").mkdir(parents=True)
            unnormalised = workspace / ".." / "workspace"
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(unnormalised, "reports"))
            with self.assertRaises(SessionSandboxError):
                resolve_sandbox_cwd(unnormalised, "../other-session")

    def test_symlinks_inside_workspace_are_allowed_and_escapes_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            (workspace / "reports").mkdir(parents=True)
            outside = Path(directory) / "outside"
            outside.mkdir()
            try:
                (workspace / "inside-link").symlink_to(workspace / "reports", target_is_directory=True)
                (workspace / "outside-link").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks are unavailable here: {exc}")
            self.assertEqual("/workspace/inside-link", resolve_sandbox_cwd(workspace, "inside-link"))
            with self.assertRaises(SessionSandboxError):
                resolve_sandbox_cwd(workspace, "outside-link")

    def test_bwrap_command_has_namespace_and_single_writable_workspace_mount(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"; workspace.mkdir()
            command = build_bwrap_command(workspace, "pwd", "/workspace", sandbox_binary="/usr/bin/bwrap")
            self.assertIn("--unshare-user", command)
            self.assertIn("--unshare-pid", command)
            self.assertIn("--unshare-net", command)
            self.assertIn("--clearenv", command)
            self.assertIn("--as=2147483648", command)
            self.assertIn("--nofile=256", command)
            self.assertEqual(["--bind", str(workspace), "/workspace"], command[command.index("--bind"):command.index("--bind") + 3])
            self.assertNotIn(".angelus-state", " ".join(command))

    def test_host_network_mode_keeps_filesystem_isolation_but_does_not_unshare_network(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"; workspace.mkdir()
            command = build_bwrap_command(workspace, "pwd", "/workspace", sandbox_binary="/usr/bin/bwrap", network_mode="host_network")
            self.assertNotIn("--unshare-net", command)
            self.assertEqual(["--bind", str(workspace), "/workspace"], command[command.index("--bind"):command.index("--bind") + 3])
            with self.assertRaises(SessionSandboxError):
                build_bwrap_command(workspace, "pwd", "/workspace", sandbox_binary="/usr/bin/bwrap", network_mode="invalid")

    def test_missing_bwrap_never_falls_back_to_host_shell(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"; workspace.mkdir()
            tool = create_session_shell_tool(workspace, sandbox_binary="missing-bwrap")
            with patch("angelus.modules.tool_module.session_sandbox.shutil.which", return_value=None):
                result = tool.handler(command="pwd")
            self.assertIn("bubblewrap is required", result)
            self.assertIn("host Shell was not started", result)


if __name__ == "__main__":
    unittest.main()
