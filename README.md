# OnyxOps — Alarm Firtinasi Korelasyon Motoru

> **AO Hackathon 2026 · Senaryo S-A1**
> 2 saatlik pencerede uretilmis **3.000 alarmi**, servis bagimlilik topolojisi ve
> zaman analiziyle **en fazla 15 olay kartina** indirger; her kartta kok neden
> hipotezini, kanitlarini, karsi hipotezini ve izlenebilir bir aksiyonu sunar.

## Kurulum

```bash
python -m pip install -r requirements.txt
cp .env.example .env          # opsiyonel: LLM zenginlestirmesi icin
```

Python 3.11+ gerekir.

## Calistirma

```bash
python -m src.verify_setup     # Veri paketi ve repo iskeleti dogrulamasi
python -m src.pipeline         # Korelasyon motoru -> output/*.json
streamlit run src/app.py       # Operator panosu (http://localhost:8501)
```

## Belgeler

- [docs/plan.md](docs/plan.md) — faz faz calisma plani
- [docs/mimari.md](docs/mimari.md) — mimari, algoritmalar, cikti sozlesmesi
- [docs/fazlar.md](docs/fazlar.md) — faz gunlugu
- [AI_JURI.md](AI_JURI.md) — AI is akisi ve X-Factor kanitlari

*(Ekran goruntuleri ve olculen sonuclar Faz 6'da eklenecek.)*
