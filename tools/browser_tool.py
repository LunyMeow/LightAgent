"""
LLAMA-AGENT :: Web Aracı
URL'den içerik çeker, web bilgisi sağlar.
Playwright tercih edilir; yoksa requests+BeautifulSoup fallback.
"""
import logging
from security.validator import SecurityValidator

logger = logging.getLogger("agent.tools.browser")


class WebTool:
    name = "web"
    description = "Bir URL'ye gidip içerik çeker. Dökümantasyon veya güncel bilgi için kullanılır."

    @staticmethod
    def fetch(url: str, max_chars: int = 6000) -> str:
        safe, reason = SecurityValidator.sanitize_url(url)
        if not safe:
            return f"❌ GÜVENLİK ENGELİ: {reason}"

        # Playwright dene (headless Chromium)
        try:
            from playwright.sync_api import sync_playwright
            return WebTool._fetch_playwright(url, max_chars)
        except ImportError:
            logger.warning("Playwright yüklü değil, requests fallback kullanılıyor.")
        except Exception as e:
            logger.warning(f"Playwright hatası: {e}, fallback deneniyor.")

        # Fallback: requests + BeautifulSoup
        try:
            return WebTool._fetch_requests(url, max_chars)
        except Exception as e:
            return f"❌ WEB HATASI: {str(e)}"

    @staticmethod
    def _fetch_playwright(url: str, max_chars: int) -> str:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                title = page.title()
                content = page.inner_text("body")
                content = "\n".join(line.strip() for line in content.splitlines() if line.strip())
                logger.info(f"Web fetch (playwright): {url} → {len(content)} chars")
                return f"🌐 Sayfa: {title}\nURL: {url}\n\n{content[:max_chars]}"
            finally:
                browser.close()

    @staticmethod
    def _fetch_requests(url: str, max_chars: int) -> str:
        import requests
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.result = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style', 'nav', 'footer'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script', 'style', 'nav', 'footer'):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip and data.strip():
                    self.result.append(data.strip())

        headers = {"User-Agent": "Mozilla/5.0 (compatible; LlamaAgent/1.0)"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        parser = TextExtractor()
        parser.feed(resp.text)
        content = "\n".join(parser.result)
        content = "\n".join(line for line in content.splitlines() if line.strip())
        logger.info(f"Web fetch (requests): {url} → {len(content)} chars")
        return f"🌐 URL: {url}\n\n{content[:max_chars]}"