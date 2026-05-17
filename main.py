"""
LLAMA-AGENT :: Entry Point
Interactive CLI and programmatic usage.
"""
import sys
import os
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_loop import AgentLoop
from config import Config

# ANSI colors
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
GRAY   = "\033[90m"


def print_banner():
    print(f"""
{CYAN}{BOLD}
+======================================================+
|           LLAMA-AGENT  v1.0                          |
|           Autonomous AI System Engineer              |
+======================================================+
|  Model    : {Config.MODEL:<40}|
|  Ollama   : {Config.OLLAMA_BASE_URL:<40}|
|  Workspace: {Config.WORKSPACE_DIR:<40}|
+======================================================+
{RESET}""")


def print_help():
    print(f"""
{YELLOW}Commands:{RESET}
  {GREEN}/help{RESET}         This help menu
  {GREEN}/clear{RESET}        Clear screen
  {GREEN}/memory{RESET}       Show conversation memory
  {GREEN}/sessions{RESET}     List saved sessions
  {GREEN}/new{RESET}          Start a new session
  {GREEN}/workspace{RESET}    List workspace contents
  {GREEN}/config{RESET}       Show current config
  {GREEN}/exit{RESET}         Quit

{YELLOW}Example tasks:{RESET}
  "create a Python Flask REST API with CRUD endpoints"
  "analyze the current project structure"
  "summarize https://docs.python.org/3/library/os.html"
  "write a file called greeting.txt with content Merhaba Dunya"
  "create a bash script that prints Hello World and run it"
""")


def check_ollama():
    # DeepSeek kullanıyorsak Ollama kontrolünü atla
    if Config.is_deepseek():
        print(f"{GREEN}[OK] Using DeepSeek API | Model: {Config.MODEL}{RESET}\n")
        return True

    import requests
    try:
        resp = requests.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        model_found = any(Config.MODEL == m or Config.MODEL in m for m in models)

        if not models:
            print(f"{RED}[!!] No models installed!{RESET}")
            print(f"{CYAN}     Fix: ollama pull {Config.MODEL}{RESET}\n")
            return False

        if not model_found:
            print(f"{YELLOW}[??] Model '{Config.MODEL}' not found.{RESET}")
            print(f"{GRAY}     Installed: {', '.join(models)}{RESET}")
            print(f"{CYAN}     Fix 1: ollama pull {Config.MODEL}{RESET}")
            print(f"{CYAN}     Fix 2: python3 main.py --model {models[0]}{RESET}\n")
            return False

        print(f"{GREEN}[OK] Ollama connected | Model: {Config.MODEL}{RESET}\n")
        return True
    except Exception:
        print(f"{RED}[!!] Cannot connect to Ollama: {Config.OLLAMA_BASE_URL}{RESET}")
        print(f"{CYAN}     Fix: run 'ollama serve' in a new terminal{RESET}\n")
        return False


def interactive_mode(session_id=None, verbose=True):
    print_banner()

    if not check_ollama():
        print(f"{YELLOW}Press Enter to continue anyway, or Ctrl+C to quit...{RESET}")
        try:
            input()
        except KeyboardInterrupt:
            sys.exit(0)

    agent = AgentLoop(session_id=session_id, verbose=verbose)
    print(f"{GRAY}Session: {agent.memory.session_id}{RESET}")
    print(f"{GRAY}Type /help for commands.{RESET}\n")

    while True:
        try:
            user_input = input(f"{CYAN}{BOLD}You > {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{GRAY}Exiting...{RESET}")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/exit", "/quit", "exit", "quit"):
            print(f"{GREEN}Goodbye! {RESET}")
            break

        elif cmd == "/help":
            print_help()

        elif cmd == "/clear":
            os.system("clear" if os.name == "posix" else "cls")
            print_banner()

        elif cmd == "/memory":
            ctx = agent.memory.get_context_for_prompt()
            obs = agent.memory.get_recent_observations()
            print(f"\n{YELLOW}-- Conversation History --{RESET}\n{ctx or '(empty)'}")
            print(f"\n{YELLOW}-- Recent Observations --{RESET}\n{obs or '(empty)'}\n")

        elif cmd == "/sessions":
            sessions = agent.memory.list_sessions()
            if sessions:
                print(f"\n{YELLOW}Saved Sessions:{RESET}")
                for s in sessions[-10:]:
                    print(f"  {GRAY}* {s}{RESET}")
            else:
                print(f"{GRAY}No saved sessions.{RESET}")
            print()

        elif cmd == "/new":
            agent = AgentLoop(verbose=verbose)
            print(f"{GREEN}[OK] New session started: {agent.memory.session_id}{RESET}\n")

        elif cmd == "/workspace":
            from tools.system_tools import FileTool
            print(f"\n{YELLOW}-- Workspace --{RESET}")
            print(FileTool.list_dir("."))
            print()

        elif cmd == "/config":
            print(f"\n{YELLOW}-- Configuration --{RESET}")
            print(f"  Model     : {Config.MODEL}")
            print(f"  Ollama    : {Config.OLLAMA_BASE_URL}")
            print(f"  Workspace : {Config.WORKSPACE_DIR}")
            print(f"  Max iters : {Config.MAX_ITERATIONS}")
            print(f"  Allowed   : {', '.join(Config.ALLOWED_COMMANDS)}\n")

        else:
            print(f"{GRAY}-----------------------------------------{RESET}")
            try:
                answer = agent.run(user_input)
                print(f"\n{GREEN}{BOLD}Agent Answer:{RESET}")
                print(f"{answer}")
            except Exception as e:
                print(f"{RED}[!!] Error: {e}{RESET}")
            print(f"{GRAY}-----------------------------------------{RESET}\n")


def single_task_mode(task, output_json=False):
    agent = AgentLoop(verbose=not output_json)
    result = agent.run(task)
    if output_json:
        print(json.dumps({"task": task, "result": result}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}\nRESULT:\n{result}\n{'='*50}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="LLAMA-AGENT - Autonomous AI System Engineer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                             # interactive mode
  python main.py -t "create a Flask API"    # single task
  python main.py --session abc123           # resume session
  python main.py -t "task" --json           # JSON output (automation)
  python main.py --model llama3.2:3b        # use specific model
        """
    )
    parser.add_argument("-t", "--task",   help="Run a single task and exit")
    parser.add_argument("--session",      help="Resume a previous session by ID")
    parser.add_argument("--json",         action="store_true", help="Output result as JSON")
    parser.add_argument("--quiet",        action="store_true", help="Minimal output")
    parser.add_argument("--model",        help="Override model (default: llama3.1)")
    args = parser.parse_args()

    if args.model:
        Config.MODEL = args.model

    if args.task:
        single_task_mode(args.task, output_json=args.json)
    else:
        interactive_mode(session_id=args.session, verbose=not args.quiet)


if __name__ == "__main__":
    main()