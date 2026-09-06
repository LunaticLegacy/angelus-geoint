"""Contract tests for the mandatory OS-level session Shell sandbox."""
from __future__ import annotations

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


class SessionShellSandboxTests(unittest.TestCase):
    def test_only_workspace_paths_are_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"; (workspace / "reports").mkdir(parents=True)
            self.assertEqual("/workspace", resolve_sandbox_cwd(workspace, None))
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(workspace, "reports"))
            self.assertEqual("/workspace/reports", resolve_sandbox_cwd(workspace, "/workspace/reports"))
            with self.assertRaises(SessionSandboxError): resolve_sandbox_cwd(workspace, "/home/luna")
            with self.assertRaises(SessionSandboxError): resolve_sandbox_cwd(workspace, "../other-session")

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
