"""X-Factor — Benzer gecmis olay oruntulerinin karta iliştirilmesi.

Senaryonun bonus maddesi: *"Benzer gecmis olay oruntulerini yakalayip kartin
uzerine iliştirmek."*

Iki ayri kaynaktan eslesme uretiyoruz:

**1. Bilinen ariza oruntuleri (pattern library).**
Operasyon dunyasinda tekrar eden, adi konmus ariza imzalari. Her oruntu bir
kok neden tipi kumesi, beklenen semptom zinciri ve bir ilk mudahale
playbook'u tasir. Bir olay, kok nedeni ve semptom profili bir oruntuye
uyuyorsa kartina "bu, bilinen X oruntusu" notu dusulur. Bu, nobetci muhendise
"bunu daha once gorduk, su adimlari izle" demenin yoludur.

**2. Gecmis calistirma arsivi (incident history).**
Her calistirmada uretilen olaylarin imzasi `output/incident_history.json`
dosyasina eklenir. Sonraki calistirmalarda yeni olaylar bu arsivle
karsilastirilir. Ayrica **ayni calistirmadaki kardes olaylar** da
karsilastirilir — bu, boluünmus tek bir arizayi yakalamak icin degerli:
`session-service` bellek sizintisinin erken evresi (gc_pressure) ve gec
evresi (oom_risk) ayri kartlara dustugunde, ikisi birbirine benzer olarak
iliştirilir ve operator bunlarin ayni hikaye oldugunu gorur.

**Determinizm notu.** Kartin cekirdegi (kok neden, kanit, karsi hipotez,
oncelik) tamamen deterministiktir. `similar_incidents` bolumu ise dogasi
geregi arsivin durumuna baglidir: ayni girdi + ayni arsiv -> ayni sonuc.
Arsiv silinirse yalnizca kardes eslesmeleri kalir.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from src import config
from src.models import Incident

# --------------------------------------------------------------------------
# 1) Bilinen ariza oruntuleri
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KnownPattern:
    key: str
    name: str
    description: str
    root_types: frozenset[str]
    symptom_types: frozenset[str]
    playbook: tuple[str, ...]
    typical_resolution: str


KNOWN_PATTERNS: tuple[KnownPattern, ...] = (
    KnownPattern(
        key="rack-network-partition",
        name="Kabin/omurga ag kesintisi",
        description=(
            "Tek bir fiziksel konumdaki (rack veya veri merkezi) ag baglantisi "
            "koptugunda, o kabindeki tum servisler es zamanli olarak "
            "erisilemez hale gelir. Bagimlilik grafiginde birbirine uzak "
            "servislerin ayni anda bozulmasi bu oruntunun ayirt edici "
            "isaretidir — neden mantiksal degil fizikseldir."
        ),
        root_types=frozenset({"network_down", "pkt_loss", "network_flap"}),
        symptom_types=frozenset(
            {"conn_refused", "timeout", "thread_pool", "http_5xx", "latency_high"}
        ),
        playbook=(
            "Kabin ustu switch ve uplink port sayaclarini kontrol edin.",
            "Etkilenen sunucularin tamaminin ayni kabin/DC'de olup olmadigini dogrulayin.",
            "Yedek hatta gecisi (failover) tetikleyin, trafigi diger DC'ye kaydirin.",
            "Fiziksel katman ekibini (kablo/SFP) devreye alin.",
        ),
        typical_resolution="Yedek hatta gecis ile 5-15 dk, fiziksel onarim ile 1-4 saat.",
    ),
    KnownPattern(
        key="storage-exhaustion-cascade",
        name="Disk dolmasi -> veritabani yazma kaskadi",
        description=(
            "Bir veritabani sunucusunun diski dolduğunda once yazma islemleri "
            "reddedilir, ardindan bu veritabanina yazan tum uygulama "
            "servislerinde islem hatalari ve zaman asimlari zinciri olusur. "
            "Kok neden depolama katmanindadir; uygulama alarmlarinin sayica "
            "cokluğu yaniltıcıdır."
        ),
        root_types=frozenset({"disk_full", "disk_warn"}),
        symptom_types=frozenset(
            {"db_write_fail", "txn_fail", "timeout", "http_5xx", "queue_backlog"}
        ),
        playbook=(
            "Diski acil bosaltin: eski log, temp ve arsiv dosyalarini temizleyin.",
            "Yazma trafigini gecici olarak kisin ya da kuyruga alin.",
            "Dolmaya sebep olan dosya/tabloyu tespit edin (ani buyume var mi?).",
            "Kalici kapasite artisi ve doluluk alarmi esigi revizyonu planlayin.",
        ),
        typical_resolution="Acil bosaltma ile 10-30 dk; kalici cozum icin kapasite planlamasi.",
    ),
    KnownPattern(
        key="memory-leak-slow-burn",
        name="Bellek sizintisi (yavas gelisen)",
        description=(
            "Bir serviste bellek kullanimi saatler icinde kademeli artar. Once "
            "cop toplama (GC) duraklamalari uzar ve gecikme yukselir, ardindan "
            "bellek tukenme riski alarmlari gelir. Keskin bir patlama "
            "uretmedigi icin klasik esik tabanli korelasyonun kacirdigi "
            "oruntudur; zaman icinde yayilan imzasiyla taninir."
        ),
        root_types=frozenset({"oom_risk", "gc_pressure", "mem_high"}),
        symptom_types=frozenset(
            {"latency_high", "timeout", "thread_pool", "http_5xx", "cpu_high"}
        ),
        playbook=(
            "Servisi kontrollu sekilde ornek ornek yeniden baslatin (rolling restart).",
            "Yeniden baslatmadan once heap dump alin — sizinti kaynagi icin sart.",
            "Son dagitimi (deployment) gozden gecirin; sizinti genelde yeni kodla gelir.",
            "GC parametrelerini ve heap boyutunu gecici olarak ayarlayin.",
        ),
        typical_resolution="Yeniden baslatma ile aninda rahatlama; kalici cozum kod duzeltmesi.",
    ),
    KnownPattern(
        key="upstream-provider-outage",
        name="Dis saglayici kesintisi",
        description=(
            "Kontrolumuz disindaki bir dis servis (odeme saglayicisi, KYC, SMS) "
            "erisilemez ya da asiri yavas hale gelir. Hata, o saglayiciya "
            "bagimli tum is akislarinda islem hatasi olarak gorunur. Kok neden "
            "kendi altyapimizda degildir; mudahale teknik degil sozlesmeseldir."
        ),
        root_types=frozenset({"ext_unreach", "ext_slow"}),
        symptom_types=frozenset(
            {"txn_fail", "timeout", "http_5xx", "latency_high", "queue_backlog"}
        ),
        playbook=(
            "Saglayicinin durum sayfasini ve SLA kanalini kontrol edin.",
            "Devre kesiciyi (circuit breaker) devreye alin — kendi servislerinizi koruyun.",
            "Varsa yedek saglayiciya yonlendirin; yoksa islemleri kuyruga alin.",
            "Saglayiciyla resmi iletisimi baslatin ve etki suresini kayit altina alin.",
        ),
        typical_resolution="Saglayiciya bagli; devre kesici ile kendi tarafimizdaki etki dakikalar icinde sinirlanir.",
    ),
    KnownPattern(
        key="db-pool-exhaustion",
        name="Veritabani baglanti havuzu tukenmesi",
        description=(
            "Baglanti havuzu dolar; yeni istekler baglanti bekler ve zaman "
            "asimina ugrar. Genellikle uzun suren sorgular, baglanti sizintisi "
            "veya ani yuk artisi tetikler. Veritabaninin kendisi ayakta "
            "oldugu icin 'DB saglikli' gorunur — yaniltici olan budur."
        ),
        root_types=frozenset({"db_conn_pool"}),
        symptom_types=frozenset(
            {"timeout", "latency_high", "queue_backlog", "txn_fail", "thread_pool"}
        ),
        playbook=(
            "Aktif baglantilari ve en uzun suren sorgulari listeleyin.",
            "Kilitlenmis ya da asiri uzun sorgulari sonlandirin.",
            "Havuz boyutunu gecici artirin; baglanti sizintisi olup olmadigini kontrol edin.",
            "Ani yuk artisi varsa kaynagini (batch isi, kampanya) tespit edin.",
        ),
        typical_resolution="Uzun sorgularin sonlandirilmasiyla 5-15 dk.",
    ),
    KnownPattern(
        key="batch-window-collision",
        name="Toplu is penceresi cakismasi",
        description=(
            "Birden fazla toplu is ayni pencerede calisir ve ayni kaynaklar "
            "icin yarisir. Isler uzar, birbirini bekler ve gece penceresi "
            "tasar. Genelde bir isin normalden uzun surmesiyle domino baslar."
        ),
        root_types=frozenset({"batch_overlap", "batch_slow"}),
        symptom_types=frozenset({"queue_backlog", "latency_high", "cpu_high", "timeout"}),
        playbook=(
            "Calisan toplu isleri ve baslangic saatlerini listeleyin.",
            "Dusuk oncelikli isi durdurun ya da erteleyin.",
            "Cakisan pencereleri kalici olarak ayirin (zamanlayici revizyonu).",
            "Uzayan isin neden uzadigini (veri hacmi artisi?) inceleyin.",
        ),
        typical_resolution="Dusuk oncelikli isin durdurulmasiyla dakikalar icinde.",
    ),
)

# Bir oruntunun karta iliştirilmesi icin gereken minimum uyum.
PATTERN_MATCH_THRESHOLD = 0.45

# Iki olayin "benzer" sayilmasi icin gereken minimum benzerlik.
INCIDENT_MATCH_THRESHOLD = 0.40


def match_known_patterns(incident: Incident) -> list[dict]:
    """Olayi bilinen ariza oruntuleriyle karsilastirir."""
    root = incident.root_cause
    if root is None:
        return []

    types = Counter(a.alarm_type for a in incident.alarms)
    total = max(1, sum(types.values()))

    results: list[dict] = []
    for pattern in KNOWN_PATTERNS:
        # (a) Kok neden tipi oruntuye uyuyor mu? — belirleyici bilesen.
        root_hit = root.alarm_type in pattern.root_types
        root_score = 1.0 if root_hit else 0.0

        # (b) Semptom profili ne kadar ortusuyor? (alarm agirlikli)
        symptom_mass = sum(n for t, n in types.items() if t in pattern.symptom_types)
        symptom_score = symptom_mass / total

        # (c) Oruntunun beklenen semptomlarindan kaci gerceklesti?
        seen_symptoms = sorted(set(types) & pattern.symptom_types)
        coverage = len(seen_symptoms) / max(1, len(pattern.symptom_types))

        score = 0.55 * root_score + 0.30 * symptom_score + 0.15 * coverage
        if not root_hit or score < PATTERN_MATCH_THRESHOLD:
            continue

        results.append(
            {
                "pattern_key": pattern.key,
                "name": pattern.name,
                "confidence": round(score, 3),
                "description": pattern.description,
                "matched_root_type": root.alarm_type,
                "matched_symptoms": seen_symptoms,
                "symptom_share": round(symptom_score, 3),
                "playbook": list(pattern.playbook),
                "typical_resolution": pattern.typical_resolution,
            }
        )

    results.sort(key=lambda r: (-r["confidence"], r["pattern_key"]))
    return results


# --------------------------------------------------------------------------
# 2) Olay imzasi ve gecmis arsivi
# --------------------------------------------------------------------------


@dataclass(slots=True)
class IncidentSignature:
    """Bir olayin karsilastirilabilir parmak izi."""

    incident_id: str
    run_id: str
    occurred_at: str
    root_type: str
    root_service: str
    services: list[str]
    locations: list[str]
    type_histogram: dict[str, float]
    max_severity: int
    alarm_count: int
    duration_minutes: float
    window_kinds: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "occurred_at": self.occurred_at,
            "root_type": self.root_type,
            "root_service": self.root_service,
            "services": self.services,
            "locations": self.locations,
            "type_histogram": self.type_histogram,
            "max_severity": self.max_severity,
            "alarm_count": self.alarm_count,
            "duration_minutes": self.duration_minutes,
            "window_kinds": self.window_kinds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IncidentSignature:
        return cls(
            incident_id=data.get("incident_id", ""),
            run_id=data.get("run_id", ""),
            occurred_at=data.get("occurred_at", ""),
            root_type=data.get("root_type", ""),
            root_service=data.get("root_service", ""),
            services=list(data.get("services", [])),
            locations=list(data.get("locations", [])),
            type_histogram=dict(data.get("type_histogram", {})),
            max_severity=int(data.get("max_severity", 0)),
            alarm_count=int(data.get("alarm_count", 0)),
            duration_minutes=float(data.get("duration_minutes", 0.0)),
            window_kinds=list(data.get("window_kinds", [])),
        )


def build_signature(incident: Incident, run_id: str) -> IncidentSignature:
    counts = Counter(a.alarm_type for a in incident.alarms)
    total = max(1, sum(counts.values()))
    root = incident.root_cause
    return IncidentSignature(
        incident_id=incident.incident_id,
        run_id=run_id,
        occurred_at=incident.start.isoformat(),
        root_type=root.alarm_type if root else "",
        root_service=root.service if root else "",
        services=incident.services,
        locations=incident.locations,
        type_histogram={t: round(n / total, 4) for t, n in counts.most_common()},
        max_severity=incident.max_severity,
        alarm_count=incident.alarm_count,
        duration_minutes=incident.duration_minutes,
        window_kinds=incident.window_kinds,
    )


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _root_family(alarm_type: str) -> str:
    """Kok neden tipini kaba bir aileye indirger (tam eslesme olmazsa kismi puan)."""
    for pattern in KNOWN_PATTERNS:
        if alarm_type in pattern.root_types:
            return pattern.key
    return alarm_type


def compare(a: IncidentSignature, b: IncidentSignature) -> tuple[float, list[str]]:
    """Iki imza arasindaki benzerlik (0-1) ve insan okunur gerekceler.

    **Kok neden kapisi.** Salt servis ortakligi benzerlik sayilmaz. Bu veri
    setinde `order-service`, `session-service` gibi yogun servisler neredeyse
    her olaya dokunuyor; yalnizca kume ortusmesine bakildiginda ag kesintisi
    ile bellek sizintisi "benzer" cikiyordu. Anlamli bir oruntu eslesmesi icin
    iki olayin ya ayni kok neden tipini/ailesini ya da ayni kok servisi
    paylasmasi gerekir. Aksi halde puan 0 dondurulur.
    """
    reasons: list[str] = []

    # (1) Kok neden tipi
    if a.root_type and a.root_type == b.root_type:
        root_score = 1.0
        reasons.append(f"ayni kok neden tipi (`{a.root_type}`)")
    elif a.root_type and _root_family(a.root_type) == _root_family(b.root_type):
        root_score = 0.6
        reasons.append(
            f"ayni ariza ailesi (`{a.root_type}` ~ `{b.root_type}`)"
        )
    else:
        root_score = 0.0

    same_root_service = bool(a.root_service) and a.root_service == b.root_service
    if root_score == 0.0 and not same_root_service:
        # Kok neden kapisi: ortak servis tek basina benzerlik degildir.
        return 0.0, []

    # (2) Etkilenen servis kumesi
    service_score = _jaccard(a.services, b.services)
    shared_services = sorted(set(a.services) & set(b.services))
    if shared_services:
        reasons.append(
            f"{len(shared_services)} ortak servis ({', '.join(shared_services[:4])}"
            f"{'...' if len(shared_services) > 4 else ''})"
        )

    # (3) Alarm tipi profili
    profile_score = _cosine(a.type_histogram, b.type_histogram)
    if profile_score >= 0.7:
        reasons.append(f"alarm tipi profili cok benzer (kosinus {profile_score:.2f})")

    # (4) Fiziksel konum
    location_score = _jaccard(a.locations, b.locations)

    # (5) Siddet yakinligi
    severity_score = 1.0 - abs(a.max_severity - b.max_severity) / 4.0

    # (6) Ayni kok servis — guclu isaret
    if same_root_service:
        reasons.append(f"ayni kok servis (`{a.root_service}`)")
        service_score = min(1.0, service_score + 0.25)

    score = (
        0.30 * root_score
        + 0.28 * service_score
        + 0.24 * profile_score
        + 0.10 * location_score
        + 0.08 * severity_score
    )
    return round(score, 3), reasons


# --------------------------------------------------------------------------
# Arsiv
# --------------------------------------------------------------------------

HISTORY_PATH = config.OUTPUT_DIR / "incident_history.json"
MAX_HISTORY_RUNS = 20


def load_history(path=None) -> list[IncidentSignature]:
    path = path or HISTORY_PATH
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [IncidentSignature.from_dict(item) for item in payload.get("signatures", [])]


def append_history(
    signatures: list[IncidentSignature], run_id: str, path=None
) -> None:
    """Bu calistirmanin imzalarini arsive ekler (son MAX_HISTORY_RUNS calistirma)."""
    path = path or HISTORY_PATH
    existing = [s for s in load_history(path) if s.run_id != run_id]

    run_ids: list[str] = []
    for sig in existing:
        if sig.run_id not in run_ids:
            run_ids.append(sig.run_id)
    keep = set(run_ids[-(MAX_HISTORY_RUNS - 1) :]) if run_ids else set()
    existing = [s for s in existing if s.run_id in keep]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "runs": len(keep) + 1,
                "signatures": [s.to_dict() for s in existing + signatures],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------


def attach_similar(
    incidents: list[Incident], run_id: str, path=None
) -> dict[str, dict]:
    """Her olay icin bilinen oruntu + benzer olay eslesmelerini uretir.

    Donen sozluk `incident_id -> {known_patterns, similar_incidents}` seklinde;
    `incident_cards.build_card` bunu karta gomer.
    """
    signatures = {inc.incident_id: build_signature(inc, run_id) for inc in incidents}
    history = load_history(path)

    out: dict[str, dict] = {}
    for incident in incidents:
        sig = signatures[incident.incident_id]
        matches: list[dict] = []

        # (a) Ayni calistirmadaki kardes olaylar
        for other in incidents:
            if other.incident_id == incident.incident_id:
                continue
            score, reasons = compare(sig, signatures[other.incident_id])
            if score < INCIDENT_MATCH_THRESHOLD:
                continue
            matches.append(
                {
                    "source": "ayni_calistirma",
                    "incident_id": other.incident_id,
                    "run_id": run_id,
                    "occurred_at": other.start.isoformat(),
                    "similarity": score,
                    "root_cause": (
                        f"{other.root_cause.service}/{other.root_cause.alarm_type}"
                        if other.root_cause
                        else None
                    ),
                    "alarm_count": other.alarm_count,
                    "why": reasons,
                }
            )

        # (b) Gecmis calistirmalarin arsivi
        for past in history:
            score, reasons = compare(sig, past)
            if score < INCIDENT_MATCH_THRESHOLD:
                continue
            matches.append(
                {
                    "source": "gecmis_arsiv",
                    "incident_id": past.incident_id,
                    "run_id": past.run_id,
                    "occurred_at": past.occurred_at,
                    "similarity": score,
                    "root_cause": f"{past.root_service}/{past.root_type}",
                    "alarm_count": past.alarm_count,
                    "why": reasons,
                }
            )

        matches.sort(key=lambda m: (-m["similarity"], m["incident_id"]))

        out[incident.incident_id] = {
            "known_patterns": match_known_patterns(incident),
            "similar_incidents": matches[:5],
            "history_runs_compared": len({s.run_id for s in history}),
        }

    return out
