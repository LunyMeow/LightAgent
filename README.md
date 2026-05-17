# 🦙 LLAMA-AGENT

**LLaMA 3.1 tabanlı otonom AI sistem mühendisi** — terminal kontrolü, dosya sistemi hakimiyeti ve web araması ile donatılmış tam yetkili bir ajan.

---

## 📁 Proje Yapısı

```
llama_agent/
├── main.py              # Giriş noktası (CLI)
├── agent_loop.py        # Ana ajan döngüsü (ReAct mimarisi)
├── config.py            # Merkezi konfigürasyon
├── requirements.txt     # Python bağımlılıkları
├── setup.sh             # Otomatik kurulum scripti
│
├── tools/
│   ├── system_tools.py  # Shell, Dosya, Proje Analizi araçları
│   └── browser_tool.py  # Web içerik çekme aracı
│
├── security/
│   └── validator.py     # Güvenlik katmanı
│
├── memory/
│   └── store.py         # Oturum hafızası
│
├── workspace/           # Ajanın çalışma alanı (tüm dosyalar buraya)
├── memory/              # Oturum JSON'ları
└── logs/                # Günlük log dosyaları
```

---

## 🚀 Hızlı Başlangıç

### 1. Kurulum

```bash
# Tek komutla kur
bash setup.sh

# Veya manuel:
pip install -r requirements.txt
python -m playwright install chromium  # web aracı için
```

### 2. LLaMA 3.1 Modelini İndir

```bash
ollama pull llama3.1
```

### 3. Ollama Servisini Başlat

```bash
ollama serve
```

### 4. Ajanı Başlat

```bash
# İnteraktif mod
python3 main.py

# Tek görev modu
python3 main.py -t "workspace içinde bir TODO uygulaması oluştur"

# Farklı model kullan
python3 main.py --model llama3.1:8b
```

---

## 🛠️ Mevcut Araçlar

| Araç | Açıklama | Örnek |
|------|----------|-------|
| `shell` | Terminal komutu çalıştırır | `ls -la`, `pip install flask` |
| `file_read` | Dosya içeriği okur | `app.py`, `config.json` |
| `file_write` | Dosyaya yazar | JSON: `{"path": "app.py", "content": "..."}` |
| `file_list` | Dizin listeler | `.`, `src/` |
| `tree` | Proje yapısını analiz eder | Tüm dosya mimarisi |
| `web` | Web'den içerik çeker | `https://docs.python.org/...` |

---

## 🧠 Mimari: ReAct Döngüsü

```
Görev
  │
  ▼
Düşün (Thought)
  │
  ▼
Araç Seç (Action)
  │
  ▼
Sonucu Gözlemle (Observation)
  │
  ├── Tamamlandı? → Nihai Cevap
  │
  └── Devam → Düşün...
```

---

## 🔒 Güvenlik

- **İzin listesi**: Sadece güvenli shell komutları çalışır
- **Yasaklı desenler**: `rm -rf`, `sudo`, fork bomb, vb.
- **Workspace izolasyonu**: Dosya işlemleri sadece `./workspace/` içinde
- **URL doğrulama**: Geçersiz URL'ler engellenir

---

## ⚙️ Konfigürasyon

`config.py` dosyasından ayarları değiştirebilirsiniz:

```python
Config.MODEL = "llama3.1"           # Model adı
Config.OLLAMA_BASE_URL = "http://localhost:11434"
Config.MAX_ITERATIONS = 20          # Maksimum ajan adımı
Config.TEMPERATURE = 0.1            # Düşük = daha deterministik
```

Ortam değişkenleri ile de ayarlayabilirsiniz:
```bash
export AGENT_MODEL=llama3.1:70b
export OLLAMA_URL=http://192.168.1.100:11434
python3 main.py
```

---

## 💬 Örnek Kullanımlar

```
Sen > workspace içinde bir Python Flask REST API oluştur, CRUD endpoint'leri olsun
Sen > mevcut projeyi analiz et ve README.md yaz
Sen > https://fastapi.tiangolo.com adresinden FastAPI özelliklerini özetle
Sen > workspace/app.py dosyasını oku ve bug'ları bul
Sen > requirements.txt'teki kütüphaneleri kur
```

---

## 🔧 CLI Komutları

| Komut | Açıklama |
|-------|----------|
| `/help` | Yardım menüsü |
| `/memory` | Hafıza özetini göster |
| `/sessions` | Önceki oturumlar |
| `/new` | Yeni oturum başlat |
| `/workspace` | Workspace içeriği |
| `/config` | Aktif konfigürasyon |
| `/clear` | Ekranı temizle |
| `/exit` | Çık |

---

## 📊 Log Dosyaları

Tüm ajan aktiviteleri `logs/` dizinine kaydedilir:
```bash
tail -f logs/agent_20250101.log
```