"""Proje geneli sabitler, dosya yollari ve ayarlanabilir esikler.

Tum modullerin tek dogruluk kaynagi burasi. Esikler (pencere genislikleri,
puan agirliklari) tek yerden degistirilebilsin diye burada toplandi.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Yollar
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
PROMPTS_DIR = ROOT / "prompts"
DEMO_DIR = ROOT / "demo"
SRC_DIR = ROOT / "src"
OUTPUT_DIR = ROOT / "output"

ALARMS_CSV = DATA_DIR / "alarms.csv"
ALARMS_JSON = DATA_DIR / "alarms.json"
DEPENDENCIES_CSV = DATA_DIR / "service_dependencies.csv"
HOSTS_CSV = DATA_DIR / "host_inventory.csv"

INCIDENTS_JSON = OUTPUT_DIR / "incidents.json"
NOISE_LEDGER_JSON = OUTPUT_DIR / "noise_ledger.json"
ACTION_LOG_JSON = OUTPUT_DIR / "action_log.json"

# --------------------------------------------------------------------------
# Veri paketi beklentileri (Gorev 0.2 dogrulamasi)
# --------------------------------------------------------------------------

EXPECTED_ALARM_COUNT = 3000
EXPECTED_SERVICE_COUNT = 27
EXPECTED_HOST_COUNT = 56
EXPECTED_DEPENDENCY_COUNT = 32

OBSERVATION_WINDOW = ("2026-09-10T01:30:00", "2026-09-10T03:30:00")

# Veri sozlugu pencereyi 01:30-03:30 olarak verir; gercek kayitlar saniye
# duzeyinde tasar (son alarm 03:30:20). Dogrulamada bu payi taniyoruz.
OBSERVATION_WINDOW_TOLERANCE_MIN = 5

# --------------------------------------------------------------------------
# Yarisma gereksinimleri
# --------------------------------------------------------------------------

MAX_INCIDENT_CARDS = 15

REQUIRED_DIRS = ["src", "docs", "prompts", "demo", "data"]
REQUIRED_FILES = [
    "README.md",
    "AI_JURI.md",
    "submission.json",
    ".env.example",
    "CLAUDE.md",
    "docs/plan.md",
    "docs/fazlar.md",
    "docs/mimari.md",
]

# --------------------------------------------------------------------------
# Faz 2 — Servis taban orani (baseline) modeli
# --------------------------------------------------------------------------
#
# Veri kesfi su gercegi ortaya koydu: her servis 2 saat boyunca kesintisiz
# arka plan alarmi uretiyor (mobile-bff ~2.3 alarm/dk). Bu yuzden "yalniz mi"
# testi tek basina hicbir seyi elemiyor. Bunun yerine her servisin kendi
# taban oranini olcup, o oranin uzerine cikan **artis pencerelerini** (spike)
# tespit ediyoruz. Gercek olaylar bu pencerelerin icinde yasiyor.

BASELINE_BIN_MINUTES = 1          # zaman serisi cozunurlugu
SPIKE_MERGE_GAP_MIN = 2           # bu kadar yakin artis pencereleri birlesir

# Iki ayri duyarlikta artis dedektoru calistiriyoruz — plandaki "cift pencere"
# tam olarak budur:
#
#   BURST  : dar pencere, yuksek esik. Ani patlamayi keskin sinirlarla keser.
#   SLOW   : genis pencere, dusuk esik. Taban oranin biraz uzerinde saatlerce
#            suren, keskin tepe yapmayan sinsi kotulesme dalgalarini yakalar.
#
# Ikisinin de disinda kalan dusuk/orta siddetli akis arka plan gurultusudur.

BURST_DETECTOR = {
    "rolling_minutes": 3,
    "multiplier": 3.0,
    "margin": 3.0,
    "min_count": 6,
}

SLOW_DETECTOR = {
    "rolling_minutes": 9,
    "multiplier": 1.8,
    "margin": 2.0,
    "min_count": 9,
}

# --------------------------------------------------------------------------
# Faz 2 — Gurultu filtresi
# --------------------------------------------------------------------------

# Bir dusuk-siddet alarminin "yalniz" olup olmadigina bakilan pencere.
NOISE_LONELINESS_WINDOW_MIN = 30

# "Yalnizlik" testi icin siddet tavani (1 = bilgi, 2 = uyari).
NOISE_MAX_SEVERITY = 2

# Hicbir artis penceresine dusmeyen alarmlar bu siddete kadar gurultu sayilir.
# Siddet 4-5 kayitlar asla sessizce elenmez; kumelenemezlerse "Diger" kartina
# artik olarak duserler. Kritik bir alarmi gurultu ilan etmek, onu kartsiz
# birakmaktan daha buyuk hatadir.
BACKGROUND_MAX_SEVERITY = 3

# Kosulsuz bakim ciriltisi.
#
# Bu bes tipin zaman icindeki standart sapmasi 33-36 dk; 121 dakikalik
# pencerede tam duzgun dagilimin beklenen degeri 121/sqrt(12) = 34.9. Yani
# istatistiksel olarak olaylardan tamamen bagimsizlar. Mesaj icerikleri de
# bunu dogruluyor: "Disk kullanimi yuzde 29 dolu" kaydi siddet 4 tasisa bile
# bir olay degildir. Bu yuzden siddetten bagimsiz olarak elenirler.
MAINTENANCE_CHATTER_TYPES = {
    "cert_expiry",
    "backup_warn",
    "ntp_drift",
    "log_rotate",
    "disk_warn",
}

# --------------------------------------------------------------------------
# Faz 2 — Cift pencereli zamansal kumeleme
# --------------------------------------------------------------------------

# Kisa pencere: ani patlama (burst) olaylarini yakalar.
BURST_WINDOW_MIN = 4

# Uzun pencere: yavas gelisen (slow-burn) olaylari yakalar.
SLOW_BURN_WINDOW_MIN = 20

# Bir slow-burn kumesinin gecerli sayilmasi icin gereken minimum alarm sayisi.
SLOW_BURN_MIN_ALARMS = 4

# Slow-burn kumesi arka plan gurultusuyle karismasin diye siddet esigi.
SLOW_BURN_MIN_SEVERITY = 3

# Bir burst kumesinin gecerli sayilmasi icin gereken minimum alarm sayisi.
BURST_MIN_ALARMS = 3

# --------------------------------------------------------------------------
# Faz 3 — Topolojik birlestirme
# --------------------------------------------------------------------------

# Birlestirme olcusu **baslangic ani yakinligi**dir, aralik ortusmesi degil.
#
# Neden: slow-burn kumeleri 20-40 dakikaya yayiliyor; "araliklari ortusuyor mu"
# testi 2 saatlik pencerede neredeyse her kumeyi her kumeye baglayip hepsini
# tek olaya cokertiyor. Oysa bir arizanin imzasi, bagimli servislerin
# **birbiri ardina bozulmaya baslamasidir**. Bu yuzden kumelerin ilk alarm
# anlari karsilastiriliyor.
MERGE_ONSET_GAP_MIN = 6

# Bagimlilik grafiginde kac atlamaya kadar "komsu" sayilir.
MERGE_MAX_HOPS = 2

# Ayni rack/DC uzerinden birlestirme icin daha dar bir baslangic penceresi.
MERGE_LOCALITY_ONSET_GAP_MIN = 4

# Gecisli birlesmenin freni: birlesme sonucu olusacak olay bu sureyi asiyorsa
# birlestirme reddedilir. A~B ve B~C zincirinin tum geceyi yutmasini engeller.
INCIDENT_MAX_SPAN_MIN = 30

# --------------------------------------------------------------------------
# Faz 3 — Kok neden puanlamasi
# --------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "temporal": 35.0,     # Olayin basinda olmak
    "centrality": 25.0,   # Topolojik merkezilik (kac servis bagimli)
    "type_prior": 25.0,   # Alarm tipi neden mi semptom mu
    "severity": 10.0,     # Siddet
    "blast": 5.0,         # Ayni host/servisteki alarm yogunlugu
}

# Alarm tipi egilimi: 1.0 = guclu neden adayi, 0.0 = saf semptom.
ALARM_TYPE_PRIOR = {
    # Altyapi / ag katmani — genellikle kok neden
    "network_down": 1.00,
    "network_flap": 0.85,
    "pkt_loss": 0.75,
    # Depolama
    "disk_full": 0.90,
    "disk_warn": 0.45,
    # Veritabani
    "db_write_fail": 0.95,
    "db_conn_pool": 0.70,
    # Bellek / calisma zamani
    "oom_risk": 0.80,
    "mem_high": 0.60,
    "gc_pressure": 0.55,
    "cpu_high": 0.55,
    "thread_pool": 0.50,
    # Dis bagimliliklar
    "ext_unreach": 0.85,
    "ext_slow": 0.60,
    # Toplu isler
    "batch_overlap": 0.75,
    "batch_slow": 0.50,
    # Bakim / bilgi
    "cert_expiry": 0.30,
    "backup_warn": 0.25,
    "ntp_drift": 0.25,
    "log_rotate": 0.15,
    # Semptomlar — bagimli servislerde gorulur
    "conn_refused": 0.40,
    "queue_backlog": 0.35,
    "txn_fail": 0.30,
    "http_5xx": 0.25,
    "latency_high": 0.15,
    "timeout": 0.10,
}

DEFAULT_TYPE_PRIOR = 0.35

# --------------------------------------------------------------------------
# Faz 4 — Kart onceliklendirme
# --------------------------------------------------------------------------

CRITICALITY_WEIGHT = {
    "kritik": 1.00,
    "yuksek": 0.75,
    "orta": 0.50,
    "dusuk": 0.25,
}

PRIORITY_WEIGHTS = {
    "severity": 0.40,   # Ortalama/maksimum siddet
    "breadth": 0.35,    # Etkilenen servis + host genisligi
    "volume": 0.15,     # Alarm hacmi
    "criticality": 0.10,  # Is kritikligi
}

SEVERITY_LABELS = {
    1: "bilgi",
    2: "uyari",
    3: "kucuk",
    4: "buyuk",
    5: "kritik",
}
