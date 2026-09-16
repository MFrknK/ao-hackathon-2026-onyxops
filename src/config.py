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
#
# Bu degerler sezgiyle degil, **veriden olculerek** kalibre edildi. Her alarm
# tipinin zaman ekseni uzerindeki standart sapmasi hesaplandi. 121 dakikalik
# gozlem penceresinde tam duzgun (olayla iliskisiz) dagilimin beklenen std
# degeri 121/sqrt(12) = 34.9'dur. Olcum:
#
#   Zamanda SIKISMIS (= olay imzasi)      Zamanda DUZGUN (= arka plan)
#   -----------------------------------   ---------------------------------
#   batch_overlap  0.5   network_down 0.8  txn_fail      16.8  timeout    28.0
#   pkt_loss       0.8   ext_unreach  0.9  http_5xx      28.2  db_conn_pool 30.1
#   ext_slow       1.0   disk_full    1.5  network_flap  32.9  ntp_drift  33.2
#   thread_pool    2.2   conn_refused 2.6  latency_high  33.7  log_rotate 34.4
#   oom_risk       4.9   batch_slow   4.9  mem_high      35.9  cpu_high   36.5
#   db_write_fail  6.7   gc_pressure  7.7  disk_warn     36.2
#
# Ilk kalibrasyonda `network_flap` 0.85 onseline sahipti ve buyuk olayda kok
# neden olarak secildi. Oysa olcum bu tipin std'sinin 32.9 oldugunu, yani
# duzgun dagilmis arka plan oldugunu gosteriyor: 202 alarmi iki saate yayilmis
# durumda. `mem_high` ve `cpu_high` icin de ayni durum gecerli. Bu tiplerin
# onseli dusuruldu; gercek kok neden sinyali olan network_down / pkt_loss /
# disk_full / ext_unreach one cikarildi.
ALARM_TYPE_PRIOR = {
    # --- Zamanda sikismis: guclu kok neden adaylari ---
    "network_down": 1.00,   # std 0.8  — 12 alarm, 3 dakikaya sikismis
    "disk_full": 0.95,      # std 1.5  — tek serviste, 5 dakika
    "db_write_fail": 0.95,  # std 6.7
    "ext_unreach": 0.90,    # std 0.9
    "batch_overlap": 0.85,  # std 0.5  — en keskin imza
    "pkt_loss": 0.80,       # std 0.8
    "oom_risk": 0.80,       # std 4.9
    "ext_slow": 0.70,       # std 1.0
    "conn_refused": 0.60,   # std 2.6  — hem neden hem semptom olabilir
    "gc_pressure": 0.55,    # std 7.7  — oom_risk'in oncusu
    "batch_slow": 0.50,     # std 4.9  — genelde batch_overlap'in sonucu
    "thread_pool": 0.45,    # std 2.2  — yavas bagimliligin turevi
    "db_conn_pool": 0.45,   # std 30.1 — sinirda; olay icinde anlamli
    # --- Zamanda duzgun dagilmis: arka plan / semptom ---
    "txn_fail": 0.30,       # std 16.8 — is katmani semptomu
    "queue_backlog": 0.30,
    "network_flap": 0.20,   # std 32.9 — 202 alarm, 2 saate yayilmis gurultu
    "mem_high": 0.20,       # std 35.9
    "cpu_high": 0.20,       # std 36.5
    "http_5xx": 0.15,       # std 28.2 — saf semptom
    "latency_high": 0.10,   # std 33.7
    "timeout": 0.10,        # std 28.0 — tanim geregi bagimlilik semptomu
    # --- Bakim ciriltisi (zaten Faz 2'de eleniyor) ---
    "disk_warn": 0.10,
    "cert_expiry": 0.05,
    "backup_warn": 0.05,
    "ntp_drift": 0.05,
    "log_rotate": 0.05,
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
