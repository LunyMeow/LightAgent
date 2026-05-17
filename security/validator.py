"""
LLAMA-AGENT :: Güvenlik Katmanı
Tüm shell ve araç girdilerini doğrular.
"""
import re
import logging
from config import Config

logger = logging.getLogger("agent.security")


class SecurityValidator:

    @staticmethod
    def is_safe_command(command: str) -> tuple[bool, str]:
        """
        Komutu güvenlik açısından denetler.
        Returns: (is_safe: bool, reason: str)
        """
        if not command or not command.strip():
            return False, "Boş komut."

        # Yasaklı desen kontrolü
        for pattern in Config.FORBIDDEN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Yasaklı desen tespit edildi: `{pattern}`"
                logger.warning(f"🚫 GÜVENLİK ENGELİ: {reason} | Komut: {command!r}")
                return False, reason

        # Temel komut izin listesi kontrolü
        base_cmd = command.strip().split()[0]
        if base_cmd not in Config.ALLOWED_COMMANDS:
            reason = f"Komut izin listesinde değil: `{base_cmd}`"
            logger.warning(f"⚠️  İZİNSİZ KOMUT: {reason}")
            return False, reason

        # Workspace dışına çıkma girişimi
        if "../.." in command or command.strip().startswith("/") and "/workspace" not in command:
            # sadece absolute path ile başlayan ve workspace içi olmayan komutları engelle
            if re.search(r'\s/(?!home|tmp|workspace)', command):
                reason = "Workspace dışı mutlak yol erişimi engellendi."
                logger.warning(f"🚫 YOLU ENGELLENDİ: {command!r}")
                return False, reason

        return True, "OK"

    @staticmethod
    def is_safe_path(path: str) -> tuple[bool, str]:
        """Dosya yolunun workspace içinde olduğunu kontrol eder."""
        import os
        abs_path = os.path.realpath(path)
        workspace = os.path.realpath(Config.WORKSPACE_DIR)
        if not abs_path.startswith(workspace):
            return False, f"Yol workspace dışında: {abs_path}"
        return True, "OK"

    @staticmethod
    def sanitize_url(url: str) -> tuple[bool, str]:
        """URL'nin geçerli ve erişilebilir olduğunu kontrol eder."""
        import re
        pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if not pattern.match(url):
            return False, f"Geçersiz URL formatı: {url}"
        # Yerel ağ adreslerini engelle (isteğe bağlı, production için)
        # if re.search(r'192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.', url):
        #     return False, "Yerel ağ URL'leri engellendi."
        return True, "OK"