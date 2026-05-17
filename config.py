"""
LLAMA-AGENT :: Merkezi Konfigürasyon
"""
import os

class Config:
    # --- Provider Seçimi ---
    PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
    # seçenekler: "ollama" | "deepseek"

    # --- Model Ayarları ---
    MODEL = os.getenv("AGENT_MODEL", "qwen2.5-coder:7b")

    # --- Ollama ---
    OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # --- DeepSeek ---
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY","test")
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    DEEPSEEK_MODELS = {
        "flash": "deepseek-v4-flash",
        "pro": "deepseek-v4-pro"
    }

    # aktif model (DeepSeek için override)
    if PROVIDER == "deepseek":
        MODEL = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODELS["pro"])

    # --- DeepSeek özel parametreleri ---
    DEEPSEEK_THINKING = True
    DEEPSEEK_REASONING_EFFORT = "high"  # low | medium | high

    # --- Dizinler ---
    BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
    WORKSPACE_DIR  = os.path.join(BASE_DIR, "workspace")
    MEMORY_DIR     = os.path.join(BASE_DIR, "memory")
    LOG_DIR        = os.path.join(BASE_DIR, "logs")

    # --- Ajan Davranışı ---
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", 20))
    TEMPERATURE    = float(os.getenv("TEMPERATURE", 0.1))
    CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", 8192))

    # --- İzin Verilen Shell Komutları ---
    ALLOWED_COMMANDS = [
        # File system / shell
        "ls", "pwd", "mkdir", "rmdir", "touch", "cat", "head", "tail",
        "grep", "find", "locate", "wc", "sort", "uniq",
        "echo", "printf", "cp", "mv", "rm",
        "chmod", "chown", "ln", "stat", "file",
        "tar", "zip", "unzip", "gzip", "xz",

        # Text processing
        "sed", "awk", "cut", "tr", "jq", "yq",

        # Python / scripting
        "python", "python2", "python3", "python3.10",
        "pip", "pip3", "virtualenv",
        "bash", "sh", "zsh",

        # Package managers
        "apt", "apt-get", "yum", "dnf",
        "pacman", "brew",
        "npm", "yarn", "pnpm",
        "composer",

        # Git / version control
        "git",
        "git status",
        "git log",
        "git diff",
        "git branch",
        "git checkout",
        "git pull",
        "git clone",

        # Networking
        "curl", "wget",
        "ping", "nslookup", "dig",
        "netstat", "ss",
        "ifconfig", "ip",
        "traceroute",
        "nmap",
        "tcpdump",

        # Process / monitoring
        "ps", "top", "htop",
        "kill", "pkill",
        "df", "du", "free",
        "uptime", "whoami",
        "env", "which",

        # Docker / containers
        "docker",
        "docker-compose",
        "docker ps",
        "docker images",
        "docker logs",
        "docker exec",
        "kubectl",

        # Node.js ecosystem
        "node", "npx", "pm2",

        # Build tools
        "make", "cmake",
        "gcc", "g++",
        "go", "cargo", "rustc",
        "java", "javac",

        # Databases
        "sqlite3",
        "mysql",
        "psql",
        "redis-cli",
        "mongosh",

        # Mobile / embedded
        "adb",
        "fastboot",

        # Security / debugging
        "strace", "ltrace",
        "gdb",
        "openssl",

        # CI/CD
        "gh",          # GitHub CLI
        "gitlab-runner",

        # Misc
        "history",
        "clear",
        "time",
        "watch"
    ]

    # --- Güvenlik: Yasaklı Desenler ---
    FORBIDDEN_PATTERNS = [
        r"rm\s+-rf",
        r"rm\s+-r\s+/",
        r":(){:|:&};:",      # fork bomb
        r"/etc/shadow",
        r"/etc/passwd",
        r"sudo\s",
        r"chmod\s+777",
        r">\s*/dev/sd",
        r"mkfs\.",
        r"dd\s+if=",
        r"shutdown",
        r"reboot",
        r"halt",
    ]

    # --- Runtime helper ---
    @classmethod
    def is_deepseek(cls):
        return cls.PROVIDER == "deepseek"

    @classmethod
    def get_deepseek_payload(cls, messages):
        return {
            "model": cls.MODEL,
            "messages": messages,
            "temperature": cls.TEMPERATURE,
            "max_tokens": cls.CONTEXT_WINDOW,
            "thinking": {"type": "enabled"} if cls.DEEPSEEK_THINKING else None,
            "reasoning_effort": cls.DEEPSEEK_REASONING_EFFORT,
            "stream": False
        }

    # --- Otomatik dizin oluşturma ---
    @classmethod
    def ensure_dirs(cls):
        for d in [cls.WORKSPACE_DIR, cls.MEMORY_DIR, cls.LOG_DIR]:
            os.makedirs(d, exist_ok=True)


Config.ensure_dirs()