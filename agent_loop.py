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
- shell      -> run a shell command. Example: "mkdir test" or "bash test/hello.sh"
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


class AgentLoop:
    def __init__(self, session_id=None, verbose=True):
        self.memory = MemoryStore(session_id)
        self.verbose = verbose
        self._tools_used_this_run = []   # track what was actually executed
        self.tools = {
            "shell":      lambda inp: ShellTool.run(inp),
            "file_read":  lambda inp: FileTool.read(inp),
            "file_write": self._file_write_handler,
            "file_list":  lambda inp: FileTool.list_dir(inp or "."),
            "tree":       lambda inp: ProjectAnalysisTool.run(inp or "."),
            "web":        lambda inp: WebTool.fetch(inp),
        }
        logger.info(f"Agent started. Session: {self.memory.session_id}")

    def _file_write_handler(self, inp):
        """
        Robust file_write handler.
        Accepts: dict, JSON string, or 'path\n---\ncontent'.
        """
        if isinstance(inp, dict):
            path    = inp.get("path", "output.txt")
            content = inp.get("content", "")
            return FileTool.write(path, content)

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
                "num_ctx": Config.CONTEXT_WINDOW,
            }
        }
        try:
            resp = requests.post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=180
            )
            if resp.status_code == 404:
                available = self._get_available_models()
                hint = (
                    f"Available models: {', '.join(available)}\nFix: ollama pull {Config.MODEL}"
                    if available else
                    f"No models installed! Fix: ollama pull {Config.MODEL}"
                )
                raise RuntimeError(f"Model not found: '{Config.MODEL}'\n{hint}")
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {Config.OLLAMA_BASE_URL}\n"
                f"Fix: run 'ollama serve' in a terminal."
            )
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama timed out (180s). Model too large or low RAM?")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}")

    def _call_deepseek(self, messages):
        payload = Config.get_deepseek_payload(messages)
        headers = {
            "Authorization": f"Bearer {Config.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            resp = requests.post(
                f"{Config.DEEPSEEK_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=180
            )
            resp.raise_for_status()
            data = resp.json()
            # DeepSeek may return reasoning + content blocks
            content = data["choices"][0]["message"].get("content") or ""
            # If content is empty, try reasoning_content
            if not content.strip():
                content = data["choices"][0]["message"].get("reasoning_content", "")
            return content
        except requests.exceptions.Timeout:
            raise RuntimeError("DeepSeek timeout (180s)")
        except Exception as e:
            raise RuntimeError(f"DeepSeek API error: {e}")

    def _parse_response(self, text):
        """
        Extract the first valid JSON action block from model output.
        Handles: markdown fences, markdown links, multiple JSON blocks,
        nested objects in 'input'.
        """
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = text.strip()

        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
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

    def _guard_task(self, task):
        """Check user task for disallowed intent. Returns (blocked, label)."""
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

    def _guard_shell(self, command):
        """Block wrong or dangerous shell usage. Returns (blocked, reason)."""
        cmd = command.strip().lower()
        if re.match(r'(bash|sh)\s+\S+\.(html|htm|css|json|xml|svg|md)', cmd):
            return True, "HTML/CSS/JSON files cannot be run with bash. File is written — set final: true."
        return False, ""

    def _log(self, msg, level="info"):
        if not self.verbose:
            return
        icons = {
            "info": "i ", "success": "OK", "error": "!!",
            "warning": "? ", "thought": ">>", "action": "->",
            "obs": "  ", "final": "**",
        }
        print(f"[{icons.get(level, '  ')}] {msg}")

    def run(self, task):
        self._log(f"Task started: {task}", "info")
        self._tools_used_this_run = []

        # Guard: check task intent
        blocked, label = self._guard_task(task)
        if blocked:
            msg = (
                f"This request ({label}) is outside what this agent is designed for.\n"
                f"Supported tasks: coding, file management, project creation, web research."
            )
            self._log(msg, "warning")
            return msg

        self.memory.add_message("user", task)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        context = self.memory.get_context_for_prompt(last_n=6)
        if context:
            messages.append({"role": "user", "content": f"Previous context:\n{context}\n\nNew task: {task}"})
        else:
            messages.append({"role": "user", "content": f"Task: {task}"})

        final_answer = "Task finished but no answer was produced."

        for iteration in range(Config.MAX_ITERATIONS):
            self._log(f"-- Iteration {iteration + 1}/{Config.MAX_ITERATIONS} --", "info")

            try:
                if Config.is_deepseek():
                    raw = self._call_deepseek(messages)
                else:
                    raw = self._call_ollama(messages)
            except RuntimeError as e:
                self._log(str(e), "error")
                return str(e)

            parsed = self._parse_response(raw)

            if not parsed:
                self._log(f"Could not parse JSON. Raw:\n{raw[:300]}", "warning")
                messages.append({"role": "assistant", "content": raw})

                # Try to salvage key fields via regex
                salvaged = {}
                for key in ("thought", "action", "input", "final", "answer"):
                    m = re.search(rf'"{key}"\s*:\s*"([^"]*?)"', raw)
                    if m:
                        salvaged[key] = m.group(1)
                if "action" in salvaged:
                    self._log(f"Salvaged partial: {salvaged}", "warning")
                    thought  = salvaged.get("thought", "")
                    action   = salvaged.get("action", "none")
                    inp      = salvaged.get("input", "")
                    is_final = salvaged.get("final", False) in (True, "true", "True")
                    if thought:
                        self._log(f"Thought: {thought}", "thought")
                    if is_final and self._tools_used_this_run:
                        final_answer = salvaged.get("answer", thought)
                        self._log("Task complete!", "final")
                        self._log(final_answer, "success")
                        break
                    if action and action != "none" and action in self.tools:
                        observation = self.tools[action](inp)
                        self._tools_used_this_run.append(action)
                        obs_preview = observation[:300] + "..." if len(observation) > 300 else observation
                        self._log(f"Output: {obs_preview}", "obs")
                        self.memory.add_observation(inp, action, observation, iteration)
                        messages.append({"role": "user", "content": f"Tool output ({action}):\n{observation}\n\nContinue."})
                    continue

                messages.append({
                    "role": "user",
                    "content": (
                        "Output ONLY a single valid JSON object. No extra text.\n"
                        'Example: {"thought":"writing file", "action":"file_write", '
                        '"input":{"path":"dir/file.html","content":"..."},"final":false}'
                    )
                })
                continue

            thought  = parsed.get("thought", "")
            action   = parsed.get("action", "none")
            inp      = parsed.get("input", "")
            is_final = parsed.get("final", False)

            if thought:
                self._log(f"Thought: {thought}", "thought")

            # CRITICAL: block premature final — must have used at least one tool
            if is_final:
                if not self._tools_used_this_run:
                    self._log("Model tried to finish without using any tool — forcing it to act.", "warning")
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": (
                            "You said the task is done, but you have not used any tool yet. "
                            "You MUST actually call the appropriate tool (e.g. file_write) to complete the task. "
                            "Do not claim the task is done without executing a tool first."
                        )
                    })
                    continue
                final_answer = parsed.get("answer", thought)
                self._log("Task complete!", "final")
                self._log(final_answer, "success")
                break

            if action and action != "none" and action in self.tools:
                if action == "shell":
                    shell_inp = str(inp)
                    blocked_cmd, reason = self._guard_shell(shell_inp)
                    if blocked_cmd:
                        self._log(f"Blocked: {shell_inp}", "warning")
                        messages.append({"role": "assistant", "content": raw})
                        messages.append({"role": "user", "content": f"Command blocked: {reason}"})
                        continue

                safe_inp = inp if action == "file_write" else (
                    json.dumps(inp, ensure_ascii=False) if isinstance(inp, (dict, list)) else str(inp)
                )

                preview = str(safe_inp)
                self._log(
                    f"Tool: {action}  input: {preview[:100]}{'...' if len(preview) > 100 else ''}",
                    "action"
                )

                observation = self.tools[action](safe_inp)
                self._tools_used_this_run.append(action)
                obs_preview = observation[:300] + "..." if len(observation) > 300 else observation
                self._log(f"Output: {obs_preview}", "obs")

                self.memory.add_observation(inp, action, observation, iteration)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"Tool output ({action}):\n{observation}\n\nContinue with the task."
                })
            else:
                messages.append({"role": "assistant", "content": raw})
                if action not in ("none", "", None):
                    messages.append({
                        "role": "user",
                        "content": f"Tool '{action}' does not exist. Available: {', '.join(self.tools.keys())}"
                    })

        else:
            self._log(f"Max iterations ({Config.MAX_ITERATIONS}) reached.", "warning")
            final_answer = "Task reached max iterations. Partially completed."

        self.memory.add_message("assistant", final_answer)
        return final_answer

    def chat(self, message):
        return self.run(message)