"""Faz 4 — Olay karti uretimi ve 15 kart ust siniri.

Gorev 4.1  Olaylari zorunlu JSON semasina cevirir; her kartin onerilen
           aksiyonu `status: "open"` ve bir sahip (owner) ile birlikte gelir.
Gorev 4.2  Kartlari `severity x breadth` agirlikli oncelik formuluyle siralar,
           en kritik olanlari birer karta ayirir ve geri kalan **her seyi**
           tek bir "Diger / Kumelenmemis" kartinda toplar.

**Veri kaybi sifir.** Uc ayri akis kartlara baglanir:
  1. Kendi kartini alan olaylar,
  2. Sinira takilan olaylar -> "Diger" karti,
  3. Hicbir kumeye giremeyen artik sinyal alarmlari -> "Diger" karti.
Gurultu olarak elenenler ise ayri bir deftere (noise_ledger) yazilir; toplam
her zaman 3.000'e denk gelir ve `pipeline` bunu acikca dogrular.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from src import config
from src.models import Alarm, Incident
from src.root_cause import (
    evidence_for,
    recommend_action,
    suggest_owner,
)
from src.similarity import append_history, attach_similar, build_signature
from src.topology import DependencyGraph


# --------------------------------------------------------------------------
# Gorev 4.2 — Oncelik formulu
# --------------------------------------------------------------------------


def compute_priority(incident: Incident, totals: dict[str, int]) -> dict[str, float]:
    """Ciddiyet x etki genisligi agirlikli oncelik puani (0-1).

    Bilesenler kendi icinde 0-1'e normalize edilir:

    * `severity`    — olaydaki en yuksek siddet (1-5 -> 0-1).
    * `breadth`     — etkilenen servis + host sayisinin tum olaylar icindeki
                      en genisine orani. Bir arizanin kac yere dokundugu.
    * `volume`      — alarm hacminin en buyuk olaya orani.
    * `criticality` — etkilenen servislerin is kritikligi ortalamasi.
    """
    weights = config.PRIORITY_WEIGHTS

    severity = (incident.max_severity - 1) / 4.0

    breadth_raw = len(incident.services) + 0.25 * len(incident.hosts)
    breadth = breadth_raw / max(1.0, totals["max_breadth"])

    volume = incident.alarm_count / max(1, totals["max_volume"])

    crit_values = [
        config.CRITICALITY_WEIGHT.get(a.criticality, 0.5) for a in incident.alarms
    ]
    criticality = sum(crit_values) / len(crit_values) if crit_values else 0.5

    parts = {
        "severity": weights["severity"] * severity,
        "breadth": weights["breadth"] * min(1.0, breadth),
        "volume": weights["volume"] * min(1.0, volume),
        "criticality": weights["criticality"] * criticality,
    }
    parts = {k: round(v, 4) for k, v in parts.items()}
    parts["total"] = round(sum(parts.values()), 4)
    return parts


def rank_incidents(incidents: list[Incident]) -> list[Incident]:
    """Olaylari oncelige gore siralar (yuksekten dusuge)."""
    if not incidents:
        return []

    totals = {
        "max_breadth": max(
            len(i.services) + 0.25 * len(i.hosts) for i in incidents
        ),
        "max_volume": max(i.alarm_count for i in incidents),
    }

    for incident in incidents:
        incident.priority_breakdown = compute_priority(incident, totals)
        incident.priority_score = incident.priority_breakdown["total"]

    return sorted(
        incidents,
        key=lambda i: (-i.priority_score, i.start, i.incident_id),
    )


# --------------------------------------------------------------------------
# Gorev 4.1 — Kart semasi
# --------------------------------------------------------------------------


def _time_range(start: datetime, end: datetime) -> dict:
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "duration_minutes": round((end - start).total_seconds() / 60.0, 1),
    }


def _title(incident: Incident) -> str:
    root = incident.root_cause
    if root is None:
        return f"{len(incident.services)} serviste korelasyonlu alarm yogunlugu"

    label = {
        "network_down": "Ag baglantisi koptu",
        "network_flap": "Ag linki kararsiz",
        "pkt_loss": "Paket kaybi",
        "disk_full": "Disk doldu",
        "db_write_fail": "Veritabani yazma hatasi",
        "db_conn_pool": "Veritabani baglanti havuzu tukendi",
        "oom_risk": "Bellek tukenme riski",
        "gc_pressure": "Cop toplama baskisi",
        "mem_high": "Bellek kullanimi yuksek",
        "cpu_high": "CPU kullanimi yuksek",
        "thread_pool": "Is parcacigi havuzu doydu",
        "ext_unreach": "Dis servis erisilemiyor",
        "ext_slow": "Dis servis yavas",
        "batch_overlap": "Toplu is penceresi cakismasi",
        "batch_slow": "Toplu is uzuyor",
        "conn_refused": "Baglanti reddedildi",
        "http_5xx": "Sunucu hata orani yuksek",
        "latency_high": "Yanit suresi yuksek",
        "timeout": "Bagimlilik zaman asimi",
        "txn_fail": "Islem hatalari",
        "queue_backlog": "Kuyruk birikimi",
    }.get(root.alarm_type, root.alarm_type)

    scope = (
        f"{len(incident.services)} servise yayildi"
        if len(incident.services) > 1
        else "tek serviste sinirli"
    )
    return f"{root.service}: {label} — {scope}"


def build_card(
    incident: Incident,
    graph: DependencyGraph,
    generated_at: datetime,
    similar: dict | None = None,
) -> dict:
    """Bir olayi zorunlu JSON semasina cevirir."""
    root = incident.root_cause
    counter = incident.counter_hypothesis

    card: dict = {
        "incident_id": incident.incident_id,
        "title": _title(incident),
        "status": "open",
        "priority_score": round(incident.priority_score, 4),
        "priority_breakdown": incident.priority_breakdown,
        "alarm_count": incident.alarm_count,
        "affected_services": incident.services,
        "affected_hosts": incident.hosts,
        "affected_locations": incident.locations,
        "max_severity": incident.max_severity,
        "severity_label": config.SEVERITY_LABELS.get(
            incident.max_severity, str(incident.max_severity)
        ),
        "time_range": _time_range(incident.start, incident.end),
        "window_kinds": incident.window_kinds,
        "cluster_count": len(incident.clusters),
        "alarm_ids": [a.alarm_id for a in incident.alarms],
        "alarm_type_histogram": dict(
            Counter(a.alarm_type for a in incident.alarms).most_common()
        ),
        "source_systems": sorted({a.source_system for a in incident.alarms}),
    }

    if root is not None:
        card["root_cause_hypothesis"] = {
            "alarm_id": root.alarm_id,
            "timestamp": root.timestamp.isoformat(),
            "service": root.service,
            "host": root.host,
            "alarm_type": root.alarm_type,
            "severity": root.severity,
            "message": root.message,
            "location": root.location,
            "confidence": round(incident.root_cause_score.get("total", 0.0) / 100, 3),
            "score_breakdown": incident.root_cause_score,
            "explanation": incident.explanation,
            "explanation_source": incident.explanation_source,
        }
        card["evidence"] = evidence_for(incident, graph)
        card["recommended_action"] = {
            "action": recommend_action(root, incident),
            "owner": suggest_owner(root),
            "status": "open",
            "created_at": generated_at.isoformat(),
            "updated_at": generated_at.isoformat(),
            "history": [
                {
                    "status": "open",
                    "at": generated_at.isoformat(),
                    "note": "Olay karti otomatik olarak acildi.",
                }
            ],
        }

    if counter is not None:
        card["counter_hypothesis"] = {
            "alarm_id": counter.alarm_id,
            "timestamp": counter.timestamp.isoformat(),
            "service": counter.service,
            "host": counter.host,
            "alarm_type": counter.alarm_type,
            "severity": counter.severity,
            "score": incident.counter_score.get("total", 0.0),
            "reason": incident.counter_reason,
        }

    card["correlation_reasons"] = incident.merge_reasons

    # X-Factor: bilinen ariza oruntusu + benzer gecmis olaylar.
    card["similar_patterns"] = similar or {
        "known_patterns": [],
        "similar_incidents": [],
        "history_runs_compared": 0,
    }
    return card


# --------------------------------------------------------------------------
# Gorev 4.2 — "Diger / Kumelenmemis" karti
# --------------------------------------------------------------------------


def build_unclustered_card(
    overflow: list[Incident],
    residual: list[Alarm],
    generated_at: datetime,
) -> dict | None:
    """Sinira takilan olaylar + artik alarmlar icin tek toplayici kart."""
    alarms: list[Alarm] = [a for inc in overflow for a in inc.alarms]
    alarms.extend(residual)
    if not alarms:
        return None

    alarms.sort(key=lambda a: (a.timestamp, a.alarm_id))
    services = sorted({a.service for a in alarms})
    hosts = sorted({a.host for a in alarms})

    reasons: list[str] = []
    if overflow:
        capped = [i for i in overflow if _passes_quality_gate(i)]
        weak = [i for i in overflow if not _passes_quality_gate(i)]
        if capped:
            reasons.append(
                f"{len(capped)} olay, oncelik siralamasinda ilk "
                f"{config.MAX_INCIDENT_CARDS - 1} icine giremedigi icin buraya "
                "alindi."
            )
        if weak:
            reasons.append(
                f"{len(weak)} olay kalite kapisini gecemedi: tek serviste kaldi, "
                f"siddeti {config.CARD_QUALITY_MIN_SEVERITY} altinda ve kok neden "
                "adayi zamanda duzgun dagilmis bir arka plan tipi "
                f"(neden egilimi < {config.CARD_QUALITY_MIN_TYPE_PRIOR}). "
                "Kendi kartini hak edecek kanit yok, ama kayitlar burada duruyor."
            )
    if residual:
        reasons.append(
            f"{len(residual)} alarm gurultu esigini gecti ama hicbir zamansal "
            "kumeye girecek yogunluga ulasmadi (tekil/seyrek sinyal)."
        )

    return {
        "incident_id": "INC-UNCLUSTERED",
        "title": f"Diger / Kumelenmemis — {len(alarms)} alarm, {len(services)} servis",
        "status": "open",
        "priority_score": 0.0,
        "priority_breakdown": {},
        "alarm_count": len(alarms),
        "affected_services": services,
        "affected_hosts": hosts,
        "affected_locations": sorted({a.location for a in alarms}),
        "max_severity": max(a.severity for a in alarms),
        "severity_label": config.SEVERITY_LABELS.get(
            max(a.severity for a in alarms), ""
        ),
        "time_range": _time_range(alarms[0].timestamp, alarms[-1].timestamp),
        "window_kinds": [],
        "cluster_count": sum(len(i.clusters) for i in overflow),
        "alarm_ids": [a.alarm_id for a in alarms],
        "alarm_type_histogram": dict(
            Counter(a.alarm_type for a in alarms).most_common()
        ),
        "source_systems": sorted({a.source_system for a in alarms}),
        "root_cause_hypothesis": {
            "alarm_id": None,
            "service": None,
            "explanation": (
                "Bu kart tek bir kok nedene indirgenemez; 15 kart siniri "
                "disinda kalan olaylari ve hicbir kumeye girmeyen artik "
                "sinyalleri veri kaybi olmadan tasir. Icerigi olay bazinda "
                "asagida listelenmistir."
            ),
            "explanation_source": "template",
            "confidence": 0.0,
            "score_breakdown": {},
        },
        "evidence": reasons,
        "recommended_action": {
            "action": (
                "Dusuk oncelikli artik sinyalleri toplu olarak gozden gecirin; "
                "tekrar eden bir oruntu varsa esikleri yeniden ayarlayin."
            ),
            "owner": "platform-oncall",
            "status": "open",
            "created_at": generated_at.isoformat(),
            "updated_at": generated_at.isoformat(),
            "history": [
                {
                    "status": "open",
                    "at": generated_at.isoformat(),
                    "note": "Toplayici kart otomatik olarak acildi.",
                }
            ],
        },
        "correlation_reasons": reasons,
        "rolled_up_incidents": [
            {
                "incident_id": inc.incident_id,
                "services": inc.services,
                "alarm_count": inc.alarm_count,
                "priority_score": round(inc.priority_score, 4),
                "time_range": _time_range(inc.start, inc.end),
                "root_cause": (
                    inc.root_cause.alarm_id if inc.root_cause else None
                ),
            }
            for inc in overflow
        ],
    }


# --------------------------------------------------------------------------


def _passes_quality_gate(incident: Incident) -> bool:
    """Olay kendi kartini hak ediyor mu? (bkz. config.CARD_QUALITY_*)"""
    if len(incident.services) >= config.CARD_QUALITY_MIN_SERVICES:
        return True
    if incident.max_severity >= config.CARD_QUALITY_MIN_SEVERITY:
        return True
    root = incident.root_cause
    if root is not None and root.type_prior >= config.CARD_QUALITY_MIN_TYPE_PRIOR:
        return True
    return False


def build_cards(
    incidents: list[Incident],
    residual: list[Alarm],
    graph: DependencyGraph,
    generated_at: datetime,
    run_id: str = "",
) -> tuple[list[dict], dict]:
    """Olaylari kartlara cevirir; kalite kapisini ve 15 kart sinirini uygular."""
    ranked = rank_incidents(incidents)

    # 1) Kalite kapisi — kanitsiz olaylar kendi kartini almaz.
    qualified = [inc for inc in ranked if _passes_quality_gate(inc)]
    rejected = [inc for inc in ranked if not _passes_quality_gate(inc)]

    # 2) Artik alarm veya elenen olay varsa toplayici kart zorunlu.
    needs_bucket = (
        bool(residual)
        or bool(rejected)
        or len(qualified) > config.MAX_INCIDENT_CARDS
    )
    capacity = (
        config.MAX_INCIDENT_CARDS - 1 if needs_bucket else config.MAX_INCIDENT_CARDS
    )

    kept = qualified[:capacity]
    overflow = qualified[capacity:] + rejected

    # Kart kimliklerini oncelik sirasina gore yeniden numaralandir.
    for number, incident in enumerate(kept, start=1):
        incident.incident_id = f"INC-{number:03d}"

    # X-Factor: benzerlik **numaralandirmadan sonra** hesaplanir, aksi halde
    # eslesmeler eski kimliklere isaret ederdi.
    similar = attach_similar(kept, run_id or generated_at.isoformat(timespec="seconds"))

    cards = [
        build_card(inc, graph, generated_at, similar.get(inc.incident_id))
        for inc in kept
    ]

    bucket = build_unclustered_card(overflow, residual, generated_at)
    if bucket is not None:
        cards.append(bucket)

    # Bu calistirmanin imzalarini arsive ekle ki sonraki calistirmalar
    # "benzer gecmis olay" eslesmesi yapabilsin.
    effective_run_id = run_id or generated_at.isoformat(timespec="seconds")
    append_history(
        [build_signature(inc, effective_run_id) for inc in kept], effective_run_id
    )

    stats = {
        "incidents_detected": len(ranked),
        "pattern_matches": sum(
            1 for c in cards if (c.get("similar_patterns") or {}).get("known_patterns")
        ),
        "incidents_passing_quality_gate": len(qualified),
        "incidents_below_quality_gate": len(rejected),
        "cards_with_own_slot": len(kept),
        "incidents_rolled_up": len(overflow),
        "residual_alarms": len(residual),
        "total_cards": len(cards),
        "cap": config.MAX_INCIDENT_CARDS,
    }
    return cards, stats
