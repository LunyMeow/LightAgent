"""
LLAMA-AGENT :: Merkezi Konfigürasyon
"""
import os

class Config:
    # --- Provider ---
    PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

    # --- Model ---
    MODEL = os.getenv("AGENT_MODEL", "qwen2.5-coder:7b")

    # --- Ollama ---
    OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # --- DeepSeek ---
    DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL  = "https://api.deepseek.com"
    DEEPSEEK_MODELS    = {"flash": "deepseek-v4-flash", "pro": "deepseek-v4-pro"}
    DEEPSEEK_THINKING          = True
    DEEPSEEK_REASONING_EFFORT  = "high"  # low | medium | high

    if PROVIDER == "deepseek":
        MODEL = os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODELS["pro"])

    # --- Dizinler ---
    BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
    WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
    MEMORY_DIR    = os.path.join(BASE_DIR, "memory")
    LOG_DIR       = os.path.join(BASE_DIR, "logs")

    # --- Ajan Davranışı ---
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", 20))
    TEMPERATURE    = float(os.getenv("TEMPERATURE", 0.1))
    CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW", 8192))

    # --- Shell timeout ---
    DEFAULT_SHELL_TIMEOUT = int(os.getenv("DEFAULT_SHELL_TIMEOUT", 60))
    MAX_SHELL_TIMEOUT     = int(os.getenv("MAX_SHELL_TIMEOUT", 300))

    # ──────────────────────────────────────────────────────────────
    # İZİN POLİTİKALARI
    # Her ayar için 3 seçenek:
    #   "always"  → her zaman izin ver  (sormadan geç)
    #   "ask"     → her seferinde kullanıcıya sor
    #   "never"   → her zaman reddet   (sormadan engelle)
    # ──────────────────────────────────────────────────────────────

    # Workspace dışı YOL erişimi politikası
    # (model /tmp/, ~/Desktop/ gibi yerlere dosya yazmak istediğinde)
    PATH_PERMISSION_POLICY = os.getenv("PATH_PERMISSION_POLICY", "ask")
    # "always" → workspace dışına her zaman yaz
    # "ask"    → her seferinde kullanıcıya sor   ← varsayılan
    # "never"  → workspace dışına hiç yazma

    # İzin listesi dışındaki KOMUT çalıştırma politikası
    # (allowlist'te olmayan komutlar için)
    COMMAND_PERMISSION_POLICY = os.getenv("COMMAND_PERMISSION_POLICY", "ask")
    # "always" → izin listesi dışı komutları her zaman çalıştır
    # "ask"    → her seferinde kullanıcıya sor   ← varsayılan
    # "never"  → izin listesi dışı komutları hiç çalıştırma

    # Geçerli politika değerleri
    VALID_POLICIES = ("always", "ask", "never")

    # ──────────────────────────────────────────────────────────────

    # --- İzin Verilen Shell Komutları ---
    ALLOWED_COMMANDS = [
        "ls", "pwd", "mkdir", "touch", "cat", "head", "tail",
        "grep", "find", "wc", "echo", "cp", "mv",
        "python3", "pip", "pip3", "bash", "sh", "chmod",
        "curl", "wget",
        "git", "git status", "git log",
        "npm", "node",
        "docker", "docker-compose",
        "ping", "nslookup",
        "ps", "df", "du", "free", "which", "nmap", "adb",
    ]

    # --- Güvenlik: Yasaklı Desenler (bunlar hiçbir politika ile geçilemez) ---
    FORBIDDEN_PATTERNS = [
        r"rm\s+-rf",
        r"rm\s+-r\s+/",
        r":(){:|:&};:",
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
        r"curl.*\|\s*bash",
        r"wget.*\|\s*sh",
    ]

    # --- Runtime helpers ---
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
            "stream": False,
        }

    @classmethod
    def get_path_policy(cls) -> str:
        p = cls.PATH_PERMISSION_POLICY.lower()
        return p if p in cls.VALID_POLICIES else "ask"

    @classmethod
    def get_command_policy(cls) -> str:
        p = cls.COMMAND_PERMISSION_POLICY.lower()
        return p if p in cls.VALID_POLICIES else "ask"

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.WORKSPACE_DIR, cls.MEMORY_DIR, cls.LOG_DIR]:
            os.makedirs(d, exist_ok=True)


Config.ensure_dirs()