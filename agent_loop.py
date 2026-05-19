"""
LLAMA-AGENT :: Core Agent Loop (ReAct Architecture)
Thought -> Action -> Observation -> Repeat -> Final Answer
"""
import json
import re
import logging
import datetime
import os
import requests
from config import Config
from memory.store import MemoryStore
from tools.system_tools import ShellTool, FileTool, ProjectAnalysisTool
from tools.browser_tool import WebTool
from security.validator import SecurityValidator
from typing import Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(Config.LOG_DIR, f"agent_{datetime.datetime.now().strftime('%Y%m%d')}.log"))
    ]
)
logger = logging.getLogger("agent.core")


SYSTEM_PROMPT = """You are LLAMA-CORE, an autonomous AI agent with full control over a Linux terminal and filesystem.

STRICT RULE: Every response must contain EXACTLY ONE JSON object. No prose, no explanation, no multiple JSON blocks.

AVAILABLE TOOLS:
- shell      -> run a shell command.
   Format 1 (basic):        "mkdir test"
   Format 2 (with timeout): {"cmd": "npm install", "timeout": 120}
   Examples: "bash test/hello.sh"  or  {"cmd": "python train.py", "timeout": 300}

- file_write -> create/overwrite a file. The "input" field must be an OBJECT:
                {"path": "subdir/file.html", "content": "file content here"}
- file_read  -> read a file. Input: "path/to/file"
- file_list  -> list a directory. Input: "." or "subdir/"
- tree       -> show project tree. Input: "."
- web        -> fetch a URL. Input: "https://..."

FILE WRITE EXAMPLE (correct format):
{"thought": "writing the file now", "action": "file_write", "input": {"path": "test/index.html", "content": "<html>...</html>"}, "final": false}

CRITICAL RULES:
- You MUST actually call tools to do work. You CANNOT claim a file was created without calling file_write.
- "final": true is ONLY allowed AFTER you have confirmed the tool succeeded (you received a tool output).
- If you need to create a file, you MUST call file_write. Do not skip it. Do not pretend it was done.
- HTML files are NOT executable. NEVER run "bash file.html". After writing HTML, set final: true.
- To create a directory  -> shell: "mkdir dirname"
- To create/write a file -> file_write with input as an object: {"path": "...", "content": "..."}
- To run a bash script   -> shell: "bash path/to/script.sh"
- ONE action per response, ONE JSON object only
- Preserve exact content/language the user specifies

RESPONSE FORMAT (output nothing else, no markdown, no explanation):
{"thought": "brief reasoning", "action": "tool_name", "input": ..., "final": false}

WHEN DONE (only after tool confirmed success):
{"thought": "file was written successfully", "action": "none", "input": "", "final": true, "answer": "what was accomplished"}
"""

# Sentinel prefix for path confirmation requests
_PATH_CONFIRM_PREFIX = "__PATH_CONFIRM_NEEDED__:"


class AgentLoop:
    def __init__(self, session_id=None, verbose=True):
        self.memory = MemoryStore(session_id)
        self.verbose = verbose
        self._tools_used_this_run = []
        self.tools = {
            "shell":      lambda inp: ShellTool.run(inp),
            "file_read":  lambda inp: FileTool.read(inp),
            "file_write": self._file_write_handler,
            "file_list":  lambda inp: FileTool.list_dir(inp or "."),
            "tree":       lambda inp: ProjectAnalysisTool.run(inp or "."),
            "web":        lambda inp: WebTool.fetch(inp),
        }
        logger.info(f"Agent started. Session: {self.memory.session_id}")

    # ──────────────────────────────────────────────
    # Input handlers
    # ──────────────────────────────────────────────

    def _file_write_handler(self, inp):
        """Accepts dict, JSON string, or 'path\n---\ncontent'. Does NOT confirm path here — caller handles sentinel."""
        if isinstance(inp, dict):
            return FileTool.write(inp.get("path", "output.txt"), inp.get("content", ""))
        if isinstance(inp, str):
            try:
                data = json.loads(inp)
                if isinstance(data, dict):
                    return FileTool.write(data.get("path", "output.txt"), data.get("content", ""))
            except json.JSONDecodeError:
                pass
            if "\n---\n" in inp:
                path, content = inp.split("\n---\n", 1)
                return FileTool.write(path.strip(), content)
        return FileTool.write("output.txt", str(inp))

    def _file_write_confirmed(self, inp):
        """Same as _file_write_handler but with confirmed_outside=True."""
        if isinstance(inp, dict):
            return FileTool.write(inp.get("path", "output.txt"), inp.get("content", ""), confirmed_outside=True)
        if isinstance(inp, str):
            try:
                data = json.loads(inp)
                if isinstance(data, dict):
                    return FileTool.write(data.get("path", "output.txt"), data.get("content", ""), confirmed_outside=True)
            except json.JSONDecodeError:
                pass
        return FileTool.write("output.txt", str(inp), confirmed_outside=True)

    def _normalize_shell_inp(self, inp):
        """Pass shell input as-is. ShellTool._parse_input handles all formats."""
        return inp

    def _extract_cmd_str(self, inp) -> str:
        """Extract the raw command string for guard checks."""
        if isinstance(inp, dict):
            return inp.get("cmd", "")
        if isinstance(inp, str):
            stripped = inp.strip()
            if stripped.startswith("{"):
                try:
                    data = json.loads(stripped)
                    if isinstance(data, dict) and "cmd" in data:
                        return data["cmd"]
                except json.JSONDecodeError:
                    pass
            return stripped
        return str(inp)

    # ──────────────────────────────────────────────
    # API calls
    # ──────────────────────────────────────────────

    def _get_available_models(self):
        try:
            resp = requests.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    def _call_ollama(self, messages):
        payload = {
            "model": Config.MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": Config.TEMPERATURE,
                "num_ctx": 8192,
                "num_thread": os.cpu_count(),
                "num_batch": 512,
                "use_mlock": True,
                "use_mmap": False,
                "num_gpu": 0,
                "num_predict": 1024,
            }
        }
        try:
            resp = requests.post(f"{Config.OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
            if resp.status_code == 404:
                available = self._get_available_models()
                hint = (f"Available models: {', '.join(available)}\nFix: ollama pull {Config.MODEL}"
                        if available else f"No models installed! Fix: ollama pull {Config.MODEL}")
                raise RuntimeError(f"Model not found: '{Config.MODEL}'\n{hint}")
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to Ollama at {Config.OLLAMA_BASE_URL}\nFix: run 'ollama serve'.")
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama timed out (180s).")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}")

    def _call_deepseek(self, messages):
        payload = Config.get_deepseek_payload(messages)
        headers = {"Authorization": f"Bearer {Config.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        try:
            resp = requests.post(f"{Config.DEEPSEEK_BASE_URL}/chat/completions",
                                 headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            data    = resp.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not content.strip():
                content = data["choices"][0]["message"].get("reasoning_content", "")
            return content
        except requests.exceptions.Timeout:
            raise RuntimeError("DeepSeek timeout (180s)")
        except Exception as e:
            raise RuntimeError(f"DeepSeek API error: {e}")

    # ──────────────────────────────────────────────
    # Parsing
    # ──────────────────────────────────────────────

    def _parse_response(self, text):
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = text.strip()

        depth = 0; start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0: start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = text[start:i+1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and ("action" in parsed or "thought" in parsed):
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return None

    # ──────────────────────────────────────────────
    # Guards
    # ──────────────────────────────────────────────

    def _guard_task(self, task):
        BLOCKED = [
            (r'(security.{0,5}scan|vulnerability.{0,5}scan|vuln.{0,5}scan)', "security scanning"),
            (r'(güvenlik).{0,20}(tara|zaa|açık|scan)', "security scanning"),
            (r'(zaaf|vuln|açık).{0,20}(bul|find|scan|tara)', "security scanning"),
            (r'(sql.{0,3}injection|sqli|\bxss\b|\bcsrf\b|\brce\b)', "exploit testing"),
            (r'(brute.{0,5}force|password.{0,5}crack|hash.{0,5}crack)', "brute-force/cracking"),
            (r'(unut|forget|ignore).{0,40}(kural|rule|param|sistem|system|prompt)', "prompt injection"),
            (r'(parametreleri).{0,20}(unut|forget|ignore|reset)', "prompt injection"),
            (r'(önceki|previous|prior).{0,40}(unut|forget|ignore|reset)', "prompt injection"),
            (r'jailbreak|do anything now|dan mode', "jailbreak"),
        ]
        tl = task.lower()
        for pattern, label in BLOCKED:
            if re.search(pattern, tl, re.IGNORECASE):
                return True, label
        return False, ""

    def _guard_shell(self, cmd_str: str):
        cmd = cmd_str.strip().lower()
        if re.match(r'(bash|sh)\s+\S+\.(html|htm|css|json|xml|svg|md)', cmd):
            return True, "HTML/CSS/JSON files cannot be run with bash. Set final: true."
        return False, ""

    def _guard_and_confirm_shell(self, inp, confirmation_cb=None) -> Tuple[bool, str]:
        """Full security + policy check for shell. Returns (allowed, reason)."""
        cmd_str = self._extract_cmd_str(inp)

        if not cmd_str.strip():
            return False, "Empty command."

        # 1. Hard security (forbidden patterns)
        safe, reason = SecurityValidator.is_safe_command(cmd_str)
        if not safe:
            return False, f"Security block: {reason}"

        # 2. HTML/bash guard
        blocked, reason = self._guard_shell(cmd_str)
        if blocked:
            return False, reason

        # 3. Allowlist + policy
        allowed, base_cmd, needs_confirm = SecurityValidator.check_command_with_policy(cmd_str)

        if allowed:
            return True, "OK"

        if not needs_confirm:
            # policy == "never"
            return False, f"Command policy=never: `{base_cmd}` not allowed."

        # policy == "ask" — need user confirmation
        if confirmation_cb:
            if SecurityValidator.should_auto_approve(cmd_str):
                logger.info(f"Auto-approved (safe read): {cmd_str}")
                return True, "Auto-approved"

            risk = SecurityValidator.get_command_risk_level(cmd_str)
            display = cmd_str if len(cmd_str) < 80 else cmd_str[:77] + "..."
            prompt = (
                f"\n⚠️  Command not on allowlist:\n"
                f"   Command   : {display}\n"
                f"   Risk level: {risk.upper()}\n"
                f"   Base cmd  : {base_cmd}\n\n"
                f"  [Y] Allow once\n"
                f"  [N] Deny\n"
                f"  [S] Allow for this session (don't ask again)\n"
                f"  Choice: "
            )
            answer = confirmation_cb(prompt)
            ans = answer.strip().lower() if answer else "n"
            if ans in ('y', 'yes', 'e', 'evet'):
                logger.info(f"User approved once: {cmd_str}")
                return True, "User approved"
            elif ans in ('s', 'session', 'b'):
                # Add to allowed list for this session
                Config.ALLOWED_COMMANDS.append(base_cmd)
                logger.info(f"Session approved: {cmd_str}")
                return True, "Session approved"
            else:
                return False, f"User denied: {cmd_str}"

        return False, f"Command not on allowlist: `{base_cmd}`"

    # ──────────────────────────────────────────────
    # Path confirmation (for workspace-outside access)
    # ──────────────────────────────────────────────

    def _handle_path_confirm(self, sentinel: str, action: str, inp,
                              messages, raw, iteration, confirmation_cb) -> str | None:
        """
        Called when FileTool returns __PATH_CONFIRM_NEEDED__:<abs_path>.
        Asks user, then retries the operation with confirmed_outside=True.
        Returns observation string, or None if denied.
        """
        abs_path = sentinel[len(_PATH_CONFIRM_PREFIX):]
        policy   = Config.get_path_policy()  # should be "ask" to reach here

        if not confirmation_cb:
            return f"SECURITY BLOCK: Path outside workspace: {abs_path} (non-interactive, denied)"

        prompt = (
            f"\n⚠️  Path outside workspace:\n"
            f"   Path      : {abs_path}\n"
            f"   Workspace : {Config.WORKSPACE_DIR}\n\n"
            f"  [Y] Allow once\n"
            f"  [N] Deny\n"
            f"  [S] Allow for this session (set PATH_PERMISSION_POLICY=always)\n"
            f"  Choice: "
        )
        answer = confirmation_cb(prompt)
        ans = answer.strip().lower() if answer else "n"

        if ans in ('y', 'yes', 'e', 'evet'):
            logger.info(f"User approved outside path: {abs_path}")
        elif ans in ('s', 'session', 'b'):
            Config.PATH_PERMISSION_POLICY = "always"
            logger.info(f"Session: PATH_PERMISSION_POLICY set to always")
        else:
            logger.info(f"User denied outside path: {abs_path}")
            return f"DENIED: Access to {abs_path} was rejected."

        # Retry with confirmed_outside=True
        if action == "file_write":
            return self._file_write_confirmed(inp)
        elif action == "file_read":
            return FileTool.read(abs_path, confirmed_outside=True)
        return f"ERROR: Cannot retry action '{action}' with confirmed path."

    # ──────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────

    def _log(self, msg, level="info"):
        if not self.verbose:
            return
        icons = {"info": "i ", "success": "OK", "error": "!!", "warning": "? ",
                 "thought": ">>", "action": "->", "obs": "  ", "final": "**"}
        print(f"[{icons.get(level, '  ')}] {msg}")

    # ──────────────────────────────────────────────
    # User confirmation
    # ──────────────────────────────────────────────

    def _get_user_confirmation(self, prompt: str) -> str:
        if not self.verbose:
            logger.warning(f"Non-interactive, auto-deny: {prompt[:80]}")
            return "n"
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return "n"

    # ──────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────

    def run(self, task, interactive=True):
        self._log(f"Task started: {task}", "info")
        self._tools_used_this_run = []

        blocked, label = self._guard_task(task)
        if blocked:
            msg = (f"This request ({label}) is outside what this agent is designed for.\n"
                   f"Supported: coding, file management, project creation, web research.")
            self._log(msg, "warning")
            return msg

        self.memory.add_message("user", task)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        context  = self.memory.get_context_for_prompt(last_n=6)
        if context:
            messages.append({"role": "user", "content": f"Previous context:\n{context}\n\nNew task: {task}"})
        else:
            messages.append({"role": "user", "content": f"Task: {task}"})

        final_answer = "Task finished but no answer was produced."

        def confirmation_cb(prompt):
            return self._get_user_confirmation(prompt) if interactive else "n"

        for iteration in range(Config.MAX_ITERATIONS):
            self._log(f"-- Iteration {iteration + 1}/{Config.MAX_ITERATIONS} --", "info")

            try:
                raw = self._call_deepseek(messages) if Config.is_deepseek() else self._call_ollama(messages)
            except RuntimeError as e:
                self._log(str(e), "error")
                return str(e)

            parsed = self._parse_response(raw)

            # ── Parse failed ──
            if not parsed:
                self._log(f"Could not parse JSON. Raw:\n{raw[:300]}", "warning")
                messages.append({"role": "assistant", "content": raw})

                salvaged = {}
                for key in ("thought", "action", "input", "final", "answer"):
                    m = re.search(rf'"{key}"\s*:\s*"([^"]*?)"', raw)
                    if m:
                        salvaged[key] = m.group(1)

                if "action" in salvaged:
                    self._log(f"Salvaged partial: {salvaged}", "warning")
                    s_action  = salvaged.get("action", "none")
                    s_inp     = salvaged.get("input", "")
                    s_thought = salvaged.get("thought", "")
                    s_final   = salvaged.get("final", False) in (True, "true", "True")
                    if s_thought:
                        self._log(f"Thought: {s_thought}", "thought")
                    if s_final and self._tools_used_this_run:
                        final_answer = salvaged.get("answer", s_thought)
                        self._log("Task complete!", "final"); self._log(final_answer, "success"); break
                    if s_action and s_action != "none" and s_action in self.tools:
                        if s_action == "shell":
                            allowed, msg = self._guard_and_confirm_shell(s_inp, confirmation_cb)
                            if not allowed:
                                self._log(f"Command blocked: {msg}", "warning")
                                messages.append({"role": "user", "content": f"Command blocked: {msg}"}); continue
                            observation = self.tools[s_action](self._normalize_shell_inp(s_inp))
                        else:
                            observation = self.tools[s_action](s_inp)
                        # Check path sentinel
                        if isinstance(observation, str) and observation.startswith(_PATH_CONFIRM_PREFIX):
                            observation = self._handle_path_confirm(observation, s_action, s_inp,
                                                                    messages, raw, iteration, confirmation_cb)
                            if observation is None:
                                observation = "Path access denied."
                        self._tools_used_this_run.append(s_action)
                        self._log(f"Output: {observation[:300]}", "obs")
                        self.memory.add_observation(s_inp, s_action, observation, iteration)
                        messages.append({"role": "user", "content": f"Tool output ({s_action}):\n{observation}\n\nContinue."})
                    continue

                messages.append({"role": "user", "content": (
                    "Output ONLY a single valid JSON object. No extra text.\n"
                    'Example: {"thought":"writing file","action":"file_write",'
                    '"input":{"path":"dir/file.html","content":"..."},"final":false}'
                )})
                continue

            # ── Parsed OK ──
            thought  = parsed.get("thought", "")
            action   = parsed.get("action", "none")
            inp      = parsed.get("input", "")
            is_final = parsed.get("final", False)

            if thought:
                self._log(f"Thought: {thought}", "thought")

            if is_final:
                if not self._tools_used_this_run:
                    self._log("Premature final — forcing tool use.", "warning")
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({"role": "user", "content": (
                        "You said done but used no tool yet. "
                        "You MUST call the appropriate tool first (e.g. file_write)."
                    )})
                    continue
                final_answer = parsed.get("answer", thought)
                self._log("Task complete!", "final"); self._log(final_answer, "success"); break

            if action and action != "none" and action in self.tools:

                # ── Shell ──
                if action == "shell":
                    allowed, msg = self._guard_and_confirm_shell(inp, confirmation_cb)
                    if not allowed:
                        self._log(f"Command blocked: {msg}", "warning")
                        messages.append({"role": "assistant", "content": raw})
                        messages.append({"role": "user", "content": f"Command blocked: {msg}"}); continue
                    safe_inp = self._normalize_shell_inp(inp)

                # ── file_write / file_read ──
                elif action in ("file_write", "file_read"):
                    safe_inp = inp   # path sentinel handled after observation

                # ── Everything else ──
                else:
                    safe_inp = (json.dumps(inp, ensure_ascii=False)
                                if isinstance(inp, (dict, list)) else str(inp))

                preview = str(safe_inp)
                self._log(f"Tool: {action}  input: {preview[:100]}{'...' if len(preview)>100 else ''}", "action")

                observation = self.tools[action](safe_inp)

                # ── Path confirmation sentinel ──
                if isinstance(observation, str) and observation.startswith(_PATH_CONFIRM_PREFIX):
                    observation = self._handle_path_confirm(
                        observation, action, inp, messages, raw, iteration, confirmation_cb
                    )
                    if observation is None:
                        observation = "Path access denied."

                self._tools_used_this_run.append(action)
                obs_preview = observation[:300] + ("..." if len(observation) > 300 else "")
                self._log(f"Output: {obs_preview}", "obs")
                self.memory.add_observation(inp, action, observation, iteration)
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"Tool output ({action}):\n{observation}\n\nContinue with the task."})

            else:
                messages.append({"role": "assistant", "content": raw})
                if action not in ("none", "", None):
                    messages.append({"role": "user", "content":
                                     f"Tool '{action}' does not exist. Available: {', '.join(self.tools.keys())}"})

        else:
            self._log(f"Max iterations ({Config.MAX_ITERATIONS}) reached.", "warning")
            final_answer = "Task reached max iterations. Partially completed."

        self.memory.add_message("assistant", final_answer)
        return final_answer

    def chat(self, message):
        return self.run(message)