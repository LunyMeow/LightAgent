"""
LLAMA-AGENT :: Hafıza Sistemi
Konuşma geçmişini ve görev bağlamını yönetir.
"""
import json 
import os
import datetime
from config import Config


class MemoryStore:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = os.path.join(Config.MEMORY_DIR, f"session_{self.session_id}.json")
        self.short_term: list[dict] = []   # Aktif konuşma geçmişi
        self.observations: list[dict] = [] # Araç çıktıları
        self._load()

    def _load(self):
        """Varsa önceki oturumu yükler."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.short_term = data.get("short_term", [])
                    self.observations = data.get("observations", [])
            except Exception:
                pass

    def save(self):
        """Oturumu diske yazar."""
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": self.session_id,
                "short_term": self.short_term,
                "observations": self.observations,
                "saved_at": datetime.datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

    def add_message(self, role: str, content: str):
        """Konuşmaya mesaj ekler. role: 'user' | 'assistant' | 'system'"""
        self.short_term.append({
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        self.save()

    def add_observation(self, action: str, tool: str, result: str, iteration: int):
        """Araç gözlemi ekler."""
        self.observations.append({
            "iteration": iteration,
            "tool": tool,
            "action": action,
            "result": result[:2000],  # Bellek taşmasını önle
            "timestamp": datetime.datetime.now().isoformat(),
        })
        self.save()

    def get_context_for_prompt(self, last_n: int = 10) -> str:
        """LLM için özetlenmiş bağlam döndürür."""
        lines = []
        # Son N mesajı ekle
        for msg in self.short_term[-last_n:]:
            prefix = {"user": "👤 User", "assistant": "🤖 Agent", "system": "⚙️ System"}.get(msg["role"], msg["role"])
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def get_recent_observations(self, last_n: int = 5) -> str:
        """Son araç gözlemlerini döndürür."""
        recent = self.observations[-last_n:]
        lines = []
        for obs in recent:
            lines.append(f"[{obs['tool']}] → {obs['result'][:300]}")
        return "\n".join(lines)

    def clear(self):
        """Kısa süreli hafızayı temizler."""
        self.short_term = []
        self.observations = []
        self.save()

    def list_sessions(self) -> list[str]:
        """Tüm oturumları listeler."""
        sessions = []
        for f in os.listdir(Config.MEMORY_DIR):
            if f.startswith("session_") and f.endswith(".json"):
                sessions.append(f.replace("session_", "").replace(".json", ""))
        return sorted(sessions)