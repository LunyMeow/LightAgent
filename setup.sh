#!/usr/bin/env bash
# =====================================================
# LLAMA-AGENT :: Otomatik Kurulum Scripti
# =====================================================
set -e

CYAN='\033[96m'
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
RESET='\033[0m'
BOLD='\033[1m'

echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║    🦙  LLAMA-AGENT  Kurulum Scripti      ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# Python kontrolü
echo -e "${YELLOW}[1/6] Python kontrolü...${RESET}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 bulunamadı. Lütfen Python 3.10+ kurun.${RESET}"
    exit 1
fi
PYTHON_VER=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✅ Python ${PYTHON_VER} bulundu.${RESET}"

# pip kontrolü
echo -e "${YELLOW}[2/6] pip kontrolü...${RESET}"
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 bulunamadı.${RESET}"
    exit 1
fi
echo -e "${GREEN}✅ pip bulundu.${RESET}"

# Sanal ortam (opsiyonel ama önerilen)
echo -e "${YELLOW}[3/6] Sanal ortam oluşturuluyor...${RESET}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Sanal ortam oluşturuldu: ./venv${RESET}"
else
    echo -e "${GREEN}✅ Sanal ortam zaten mevcut.${RESET}"
fi

# Sanal ortamı aktifleştir
source venv/bin/activate 2>/dev/null || true

# Python bağımlılıkları
echo -e "${YELLOW}[4/6] Python kütüphaneleri kuruluyor...${RESET}"
pip3 install --quiet --upgrade pip
pip3 install --quiet requests

# Playwright (opsiyonel)
echo -e "${YELLOW}[4b] Playwright kurulmaya çalışılıyor (web aracı için)...${RESET}"
if pip3 install --quiet playwright 2>/dev/null; then
    python3 -m playwright install chromium --quiet 2>/dev/null || true
    echo -e "${GREEN}✅ Playwright kuruldu (web desteği aktif).${RESET}"
else
    echo -e "${YELLOW}⚠️  Playwright kurulamadı. Web aracı requests moduna geçer.${RESET}"
fi

echo -e "${GREEN}✅ Python bağımlılıkları tamamlandı.${RESET}"

# Ollama kontrolü
echo -e "${YELLOW}[5/6] Ollama kontrolü...${RESET}"
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}⚠️  Ollama bulunamadı. Kurulum için:${RESET}"
    echo -e "   ${CYAN}curl -fsSL https://ollama.com/install.sh | sh${RESET}"
    echo ""
else
    echo -e "${GREEN}✅ Ollama bulundu.${RESET}"
    
    # ollama serve başlat (arka planda)
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${YELLOW}   Ollama servisi başlatılıyor...${RESET}"
        ollama serve &
        sleep 3
    fi

    # Model kontrolü
    echo -e "${YELLOW}   llama3.1 modeli kontrol ediliyor...${RESET}"
    if ollama list 2>/dev/null | grep -q "llama3.1"; then
        echo -e "${GREEN}✅ llama3.1 modeli mevcut.${RESET}"
    else
        echo -e "${YELLOW}⚠️  llama3.1 bulunamadı. İndiriliyor... (Bu birkaç dakika sürebilir)${RESET}"
        ollama pull llama3.1 || echo -e "${YELLOW}   Manuel kurulum: ollama pull llama3.1${RESET}"
    fi
fi

# Dizin yapısını oluştur
echo -e "${YELLOW}[6/6] Dizinler hazırlanıyor...${RESET}"
mkdir -p workspace memory logs
echo -e "${GREEN}✅ workspace/, memory/, logs/ hazır.${RESET}"

# requirements.txt oluştur
cat > requirements.txt << 'EOF'
# LLAMA-AGENT Bağımlılıkları
requests>=2.31.0
playwright>=1.40.0   # Opsiyonel: web aracı için
EOF

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║         🎉 Kurulum Tamamlandı!           ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "Başlatmak için:"
echo -e "  ${CYAN}python3 main.py${RESET}                    # İnteraktif mod"
echo -e "  ${CYAN}python3 main.py -t 'görev'${RESET}         # Tek görev"
echo -e "  ${CYAN}python3 main.py --model llama3.1${RESET}   # Model belirt"
echo ""