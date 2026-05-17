"""
LLAMA-AGENT :: Sistem Araçları
Shell komutları, dosya işlemleri, proje analizi.
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
    description = "Terminalde komut çalıştırır. Sadece izin listesindeki komutlar."

    @staticmethod
    def run(command: str) -> str:
        safe, reason = SecurityValidator.is_safe_command(command)
        if not safe:
            return f"❌ GÜVENLİK ENGELİ: {reason}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=Config.WORKSPACE_DIR
            )
            output = ""
            if result.stdout.strip():
                output += f"STDOUT:\n{result.stdout.strip()}\n"
            if result.stderr.strip():
                output += f"STDERR:\n{result.stderr.strip()}\n"
            output += f"EXIT CODE: {result.returncode}"
            logger.info(f"Shell: {command!r} → exit={result.returncode}")
            return output or "(Çıktı yok)"
        except subprocess.TimeoutExpired:
            return "❌ HATA: Komut 60 saniyede tamamlanamadı (timeout)."
        except Exception as e:
            return f"❌ ÇALIŞMA HATASI: {str(e)}"


class FileTool:
    name = "file"
    description = "Dosya okuma, yazma, listeleme, silme işlemleri."

    @staticmethod
    def read(path: str) -> str:
        full_path = os.path.join(Config.WORKSPACE_DIR, path) if not os.path.isabs(path) else path
        safe, reason = SecurityValidator.is_safe_path(full_path)
        if not safe:
            return f"❌ GÜVENLİK ENGELİ: {reason}"
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"File read: {full_path}")
            return content if content else "(Dosya boş)"
        except FileNotFoundError:
            return f"❌ HATA: Dosya bulunamadı: {full_path}"
        except Exception as e:
            return f"❌ OKUMA HATASI: {str(e)}"

    @staticmethod
    def write(path: str, content: str) -> str:
        full_path = os.path.join(Config.WORKSPACE_DIR, path) if not os.path.isabs(path) else path
        safe, reason = SecurityValidator.is_safe_path(full_path)
        if not safe:
            return f"❌ GÜVENLİK ENGELİ: {reason}"
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"File write: {full_path} ({len(content)} chars)")
            return f"✅ Dosya yazıldı: {full_path}"
        except Exception as e:
            return f"❌ YAZMA HATASI: {str(e)}"

    @staticmethod
    def append(path: str, content: str) -> str:
        full_path = os.path.join(Config.WORKSPACE_DIR, path) if not os.path.isabs(path) else path
        safe, reason = SecurityValidator.is_safe_path(full_path)
        if not safe:
            return f"❌ GÜVENLİK ENGELİ: {reason}"
        try:
            with open(full_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"✅ İçerik eklendi: {full_path}"
        except Exception as e:
            return f"❌ EKLEME HATASI: {str(e)}"

    @staticmethod
    def list_dir(path: str = ".") -> str:
        full_path = os.path.join(Config.WORKSPACE_DIR, path)
        try:
            entries = os.listdir(full_path)
            result = []
            for e in sorted(entries):
                ep = os.path.join(full_path, e)
                size = os.path.getsize(ep) if os.path.isfile(ep) else "-"
                kind = "📁" if os.path.isdir(ep) else "📄"
                result.append(f"{kind} {e}  ({size} bytes)" if size != "-" else f"{kind} {e}/")
            return "\n".join(result) if result else "(Dizin boş)"
        except Exception as e:
            return f"❌ LİSTE HATASI: {str(e)}"


class ProjectAnalysisTool:
    name = "tree"
    description = "Proje dizin yapısını analiz eder ve mimariyi haritalar."

    @staticmethod
    def run(path: str = ".") -> str:
        root = os.path.join(Config.WORKSPACE_DIR, path)
        if not os.path.exists(root):
            return f"❌ Dizin bulunamadı: {root}"

        lines = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Gizli ve gereksiz dizinleri atla
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in
                          ['node_modules', '__pycache__', '.git', 'venv', '.env', 'dist', 'build']]
            
            level = dirpath.replace(root, '').count(os.sep)
            indent = '│   ' * (level - 1) + ('├── ' if level > 0 else '')
            folder_name = os.path.basename(dirpath) or path
            lines.append(f"{indent}{folder_name}/")
            
            sub_indent = '│   ' * level + '├── '
            for i, f in enumerate(sorted(filenames)):
                connector = '└── ' if i == len(filenames) - 1 else '├── '
                fpath = os.path.join(dirpath, f)
                size = os.path.getsize(fpath)
                lines.append(f"{'│   ' * level}{connector}{f}  [{size}B]")

        summary = f"📁 Toplam dizin analizi: {root}\n"
        summary += "\n".join(lines)

        # Dosya türü istatistikleri
        extensions = {}
        for _, _, files in os.walk(root):
            for f in files:
                ext = os.path.splitext(f)[1] or "(uzantısız)"
                extensions[ext] = extensions.get(ext, 0) + 1
        
        if extensions:
            summary += "\n\n📊 Dosya Türleri:\n"
            for ext, count in sorted(extensions.items(), key=lambda x: -x[1]):
                summary += f"  {ext}: {count} dosya\n"

        return summary