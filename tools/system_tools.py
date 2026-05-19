"""
LLAMA-AGENT :: System Tools
Shell commands, file operations, project analysis.
"""
import subprocess
import os
import json
import logging
from config import Config
from security.validator import SecurityValidator

logger = logging.getLogger("agent.tools.system")


class ShellTool:
    name = "shell"
    description = "Runs shell commands. Accepts string, dict, or JSON string."

    @staticmethod
    def _parse_input(command) -> tuple:
        """
        Normalizes input to (cmd_string, timeout_int).
        Accepted formats:
          "ls -la"
          {"cmd": "npm install", "timeout": 120}
          '{"cmd": "npm install", "timeout": 120}'
        """
        default_timeout = getattr(Config, 'DEFAULT_SHELL_TIMEOUT', 60)
        max_timeout     = getattr(Config, 'MAX_SHELL_TIMEOUT', 300)

        if isinstance(command, dict):
            cmd     = command.get("cmd", "")
            timeout = int(command.get("timeout", default_timeout))
            return str(cmd), min(timeout, max_timeout)

        if isinstance(command, str):
            stripped = command.strip()
            if stripped.startswith("{"):
                try:
                    data = json.loads(stripped)
                    if isinstance(data, dict) and "cmd" in data:
                        return str(data["cmd"]), min(int(data.get("timeout", default_timeout)), max_timeout)
                except json.JSONDecodeError:
                    pass
            return stripped, default_timeout

        return str(command), default_timeout

    @staticmethod
    def run(command) -> str:
        cmd, timeout = ShellTool._parse_input(command)

        if not cmd:
            return "ERROR: Empty command."

        safe, reason = SecurityValidator.is_safe_command(cmd)
        if not safe:
            return f"SECURITY BLOCK: {reason}"

        try:
            logger.info(f"Shell (timeout={timeout}s): {cmd!r}")
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=Config.WORKSPACE_DIR
            )
            output = ""
            if result.stdout.strip():
                output += f"STDOUT:\n{result.stdout.strip()}\n"
            if result.stderr.strip():
                output += f"STDERR:\n{result.stderr.strip()}\n"
            output += f"EXIT CODE: {result.returncode}"
            logger.info(f"Shell done: {cmd!r} → exit={result.returncode}")
            return output or "(No output)"
        except subprocess.TimeoutExpired:
            return (
                f"ERROR: Timed out after {timeout}s.\n"
                f"Use longer timeout: {{\"cmd\": \"{cmd}\", \"timeout\": {timeout * 2}}}"
            )
        except Exception as e:
            return f"EXECUTION ERROR: {str(e)}"

    @staticmethod
    def run_with_timeout(command: str, timeout: int = 60) -> str:
        return ShellTool.run({"cmd": command, "timeout": timeout})


class FileTool:
    name = "file"
    description = "File read, write, list, append operations."

    @staticmethod
    def _resolve_path(path: str) -> str:
        """Make path absolute. Relative paths → inside workspace."""
        if os.path.isabs(path):
            return path
        return os.path.join(Config.WORKSPACE_DIR, path)

    @staticmethod
    def read(path: str, confirmed_outside: bool = False) -> str:
        full_path = FileTool._resolve_path(path)
        inside, abs_path, needs_confirm = SecurityValidator.check_path_with_policy(full_path)

        if not inside and not confirmed_outside:
            if needs_confirm:
                # Signal caller to ask user (special sentinel)
                return f"__PATH_CONFIRM_NEEDED__:{abs_path}"
            return f"SECURITY BLOCK: Path outside workspace: {abs_path}"

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"File read: {abs_path}")
            return content if content else "(Empty file)"
        except FileNotFoundError:
            return f"ERROR: File not found: {abs_path}"
        except Exception as e:
            return f"READ ERROR: {str(e)}"

    @staticmethod
    def write(path: str, content: str, confirmed_outside: bool = False) -> str:
        full_path = FileTool._resolve_path(path)
        inside, abs_path, needs_confirm = SecurityValidator.check_path_with_policy(full_path)

        if not inside and not confirmed_outside:
            if needs_confirm:
                return f"__PATH_CONFIRM_NEEDED__:{abs_path}"
            return f"SECURITY BLOCK: Path outside workspace: {abs_path}"

        try:
            parent = os.path.dirname(abs_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"File write: {abs_path} ({len(content)} chars)")
            return f"File written: {abs_path}"
        except Exception as e:
            return f"WRITE ERROR: {str(e)}"

    @staticmethod
    def append(path: str, content: str, confirmed_outside: bool = False) -> str:
        full_path = FileTool._resolve_path(path)
        inside, abs_path, needs_confirm = SecurityValidator.check_path_with_policy(full_path)

        if not inside and not confirmed_outside:
            if needs_confirm:
                return f"__PATH_CONFIRM_NEEDED__:{abs_path}"
            return f"SECURITY BLOCK: Path outside workspace: {abs_path}"

        try:
            with open(abs_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Content appended: {abs_path}"
        except Exception as e:
            return f"APPEND ERROR: {str(e)}"

    @staticmethod
    def list_dir(path: str = ".") -> str:
        full_path = os.path.join(Config.WORKSPACE_DIR, path) if not os.path.isabs(path) else path
        try:
            entries = os.listdir(full_path)
            result  = []
            for e in sorted(entries):
                ep   = os.path.join(full_path, e)
                size = os.path.getsize(ep) if os.path.isfile(ep) else "-"
                kind = "DIR" if os.path.isdir(ep) else "FILE"
                result.append(f"[{kind}] {e}  ({size} bytes)" if size != "-" else f"[{kind}] {e}/")
            return "\n".join(result) if result else "(Empty directory)"
        except Exception as e:
            return f"LIST ERROR: {str(e)}"


class ProjectAnalysisTool:
    name = "tree"
    description = "Analyzes project directory structure."

    @staticmethod
    def run(path: str = ".") -> str:
        root = os.path.join(Config.WORKSPACE_DIR, path) if not os.path.isabs(path) else path
        if not os.path.exists(root):
            return f"ERROR: Directory not found: {root}"

        lines = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and
                           d not in ['node_modules', '__pycache__', '.git', 'venv', '.env', 'dist', 'build']]
            level = dirpath.replace(root, '').count(os.sep)
            indent = '|   ' * (level - 1) + ('+-- ' if level > 0 else '')
            lines.append(f"{indent}{os.path.basename(dirpath) or path}/")
            for i, f in enumerate(sorted(filenames)):
                connector = '`-- ' if i == len(filenames) - 1 else '+-- '
                size = os.path.getsize(os.path.join(dirpath, f))
                lines.append(f"{'|   ' * level}{connector}{f}  [{size}B]")

        summary = f"Project tree: {root}\n" + "\n".join(lines)
        extensions = {}
        for _, _, files in os.walk(root):
            for f in files:
                ext = os.path.splitext(f)[1] or "(no ext)"
                extensions[ext] = extensions.get(ext, 0) + 1
        if extensions:
            summary += "\n\nFile types:\n"
            for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
                summary += f"  {ext}: {count}\n"
        return summary