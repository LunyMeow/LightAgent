"""
LLAMA-AGENT :: Security Layer
Validates all shell and tool inputs.
"""
import re
import os
import logging
from config import Config
from typing import Tuple, Optional

logger = logging.getLogger("agent.security")


class SecurityValidator:

    @staticmethod
    def is_safe_command(command: str) -> Tuple[bool, str]:
        """
        Hard security check — cannot be bypassed by any policy.
        Returns: (is_safe, reason)
        """
        if not command or not command.strip():
            return False, "Empty command."

        for pattern in Config.FORBIDDEN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Forbidden pattern: `{pattern}`"
                logger.warning(f"SECURITY BLOCK: {reason} | cmd: {command!r}")
                return False, reason

        return True, "OK"

    @staticmethod
    def is_allowed_command(command: str) -> Tuple[bool, Optional[str]]:
        """Check if command base is on the allowlist."""
        if not command or not command.strip():
            return False, None
        base_cmd = command.strip().split()[0].lower()
        for allowed in Config.ALLOWED_COMMANDS:
            if base_cmd == allowed or base_cmd.startswith(allowed + " "):
                return True, base_cmd
        return False, base_cmd

    @staticmethod
    def is_safe_path(path: str) -> Tuple[bool, str]:
        """Check if path is inside workspace."""
        abs_path  = os.path.realpath(path)
        workspace = os.path.realpath(Config.WORKSPACE_DIR)
        if not abs_path.startswith(workspace):
            return False, f"Path outside workspace: {abs_path}"
        return True, "OK"

    @staticmethod
    def check_path_with_policy(path: str) -> Tuple[bool, str, bool]:
        """
        Check path against workspace boundary + PATH_PERMISSION_POLICY.

        Returns: (is_inside_workspace, abs_path, needs_confirmation)
          - is_inside_workspace: True if path is in workspace
          - abs_path: resolved absolute path
          - needs_confirmation: True if policy == "ask" and path is outside
        """
        abs_path  = os.path.realpath(path)
        workspace = os.path.realpath(Config.WORKSPACE_DIR)
        inside    = abs_path.startswith(workspace)

        if inside:
            return True, abs_path, False

        policy = Config.get_path_policy()

        if policy == "always":
            logger.info(f"Path policy=always: allowing outside path {abs_path}")
            return True, abs_path, False
        elif policy == "never":
            logger.warning(f"Path policy=never: blocking outside path {abs_path}")
            return False, abs_path, False
        else:  # "ask"
            return False, abs_path, True   # caller must confirm

    @staticmethod
    def check_command_with_policy(command: str) -> Tuple[bool, str, bool]:
        """
        Check command against allowlist + COMMAND_PERMISSION_POLICY.

        Returns: (is_allowed, base_cmd, needs_confirmation)
          - is_allowed: True if command can run
          - base_cmd: the base command string
          - needs_confirmation: True if policy == "ask" and not on allowlist
        """
        if not command or not command.strip():
            return False, "", False

        base_cmd = command.strip().split()[0].lower()
        on_list  = any(
            base_cmd == a or base_cmd.startswith(a + " ")
            for a in Config.ALLOWED_COMMANDS
        )

        if on_list:
            return True, base_cmd, False

        policy = Config.get_command_policy()

        if policy == "always":
            logger.info(f"Command policy=always: allowing {command!r}")
            return True, base_cmd, False
        elif policy == "never":
            logger.warning(f"Command policy=never: blocking {command!r}")
            return False, base_cmd, False
        else:  # "ask"
            return False, base_cmd, True   # caller must confirm

    @staticmethod
    def should_auto_approve(command: str) -> bool:
        """Read-only commands are auto-approved regardless of policy."""
        cmd_lower = command.lower().strip()
        safe_reads = [
            "ls", "cat", "head", "tail", "grep", "find", "locate", "wc",
            "sort", "uniq", "echo", "stat", "file", "which", "whoami",
            "pwd", "ps", "df", "du", "free", "uptime", "env",
            "git status", "git log", "git diff", "git branch",
        ]
        return any(cmd_lower.startswith(s) for s in safe_reads)

    @staticmethod
    def get_command_risk_level(command: str) -> str:
        """Returns 'low' | 'medium' | 'high'."""
        cmd_lower = command.lower().strip()
        high_risk   = ["rm", "mv", "chmod", "chown", "kill", "pkill",
                       "docker rm", "docker rmi", "git push", "git reset --hard",
                       "npm install -g", "pip install --user"]
        medium_risk = ["mkdir", "touch", "cp", "tar", "zip", "unzip",
                       "python", "python3", "bash", "sh", "node",
                       "npm install", "pip install", "git commit", "git merge"]
        for c in high_risk:
            if cmd_lower.startswith(c):
                return "high"
        for c in medium_risk:
            if cmd_lower.startswith(c):
                return "medium"
        return "low"

    @staticmethod
    def sanitize_url(url: str) -> Tuple[bool, str]:
        pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not pattern.match(url):
            return False, f"Invalid URL: {url}"
        return True, "OK"