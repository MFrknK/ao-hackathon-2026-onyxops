"""Gorev 3.2 / 3.3 — Kok neden puanlamasi, karsi hipotez ve aciklama.

Olay icindeki her alarm 0-100 arasi puanlanir. Puan, agirliklari
`config.SCORE_WEIGHTS` icinde acikca yazili bes bilesenin toplamidir; hicbir
kara kutu yok, her kartta kirilim gosterilir.

| Bilesen      | Agirlik | Mantik |
|--------------|---------|--------|
| `temporal`   | 35 | Olay penceresinin basina yakinlik. Neden sonuctan once gelir. |
| `centrality` | 25 | Servise kac servisin (gecisli olarak) dayandigi. |
| `type_prior` | 25 | Alarm tipi egilimi: `network_down` 1.00 ... `timeout` 0.10. |
| `severity`   | 10 | `(severity - 1) / 4`. |
| `blast`      |  5 | Alarmin servisinin olay icindeki alarm payi. |

En yuksek puanli alarm **kok neden**, en yuksek puanli *farkli servisten* alarm
**karsi hipotez** olur. Ayni servisten ikinci bir alarmi "alternatif" saymak
operatore hicbir sey soylemez; karsi hipotezin degeri baska bir yere bakmayi
onermesindedir.
"""

from __future__ import annotations

from collections import Counter

from src import config
from src.models import Alarm, Incident
from src.topology import DependencyGraph


# --------------------------------------------------------------------------
# Puanlama
# --------------------------------------------------------------------------


def score_alarm(
    alarm: Alarm,
    incident: Incident,
    graph: DependencyGraph,
    service_shares: dict[str, float],
) -> dict[str, float]:
    """Tek bir alarmin kok neden puanini bilesenleriyle birlikte hesaplar."""
    weights = config.SCORE_WEIGHTS

    # 1) Zaman — olayin basinda olan kazanir.
    span = (incident.end - incident.start).total_seconds()
    if span <= 0:
        temporal = 1.0
    else:
        offset = (alarm.timestamp - incident.start).total_seconds()
        temporal = 1.0 - (offset / span)
    temporal = max(0.0, min(1.0, temporal))

    # 2) Topolojik merkezilik — altinda cok servis yatan servis.
    centrality = graph.centrality(alarm.service)

    # 3) Alarm tipi egilimi — neden mi, semptom mu.
    type_prior = alarm.type_prior

    # 4) Siddet.
    severity = (alarm.severity - 1) / 4.0

    # 5) Etki genisligi — servisin olay icindeki alarm payi.
    blast = service_shares.get(alarm.service, 0.0)

    components = {
        "temporal": weights["temporal"] * temporal,
        "centrality": weights["centrality"] * centrality,
        "type_prior": weights["type_prior"] * type_prior,
        "severity": weights["severity"] * severity,
        "blast": weights["blast"] * blast,
    }
    components = {k: round(v, 2) for k, v in components.items()}
    components["total"] = round(sum(components.values()), 2)
    return components


def _service_shares(incident: Incident) -> dict[str, float]:
    counts = Counter(a.service for a in incident.alarms)
    total = max(1, sum(counts.values()))
    return {svc: n / total for svc, n in counts.items()}


# --------------------------------------------------------------------------
# Aciklama (sablon motoru)
# --------------------------------------------------------------------------


def _ordinal_evidence(
    incident: Incident, root: Alarm, graph: DependencyGraph
) -> list[str]:
    """Kok neden kararini destekleyen, veriden turetilmis kanit cumleleri."""
    evidence: list[str] = []
    alarms = incident.alarms

    # Zaman kaniti
    lead = (alarms[0].timestamp - incident.start).total_seconds()
    offset = (root.timestamp - incident.start).total_seconds() / 60.0
    earlier = sum(1 for a in alarms if a.timestamp < root.timestamp)
    if earlier == 0:
        evidence.append(
            f"Zaman: {root.alarm_id} olayin ilk alarmi "
            f"({root.timestamp.strftime('%H:%M:%S')}); diger "
            f"{len(alarms) - 1} kayit bundan sonra geldi."
        )
    else:
        evidence.append(
            f"Zaman: {root.alarm_id} olay basladiktan {offset:.1f} dk sonra "
            f"geldi; onunde yalnizca {earlier} kayit var."
        )
    del lead

    # Topoloji kaniti
    evidence.append(f"Topoloji: {graph.describe(root.service)}.")

    downstream = graph.impact_set(root.service, max_hops=config.MERGE_MAX_HOPS)
    hit = sorted(set(incident.services) & set(downstream))
    if hit:
        evidence.append(
            f"Yayilim: {root.service} bozulunca etkilenmesi beklenen "
            f"{len(hit)} servisin tamami bu olayda alarm uretti "
            f"({', '.join(hit[:5])}{'...' if len(hit) > 5 else ''})."
        )

    # Tip kaniti
    evidence.append(
        f"Alarm tipi: '{root.alarm_type}' neden egilimi {root.type_prior:.2f} "
        f"(1.00 = saf neden, 0.00 = saf semptom)."
    )

    # Semptom dagilimi
    symptom_types = Counter(
        a.alarm_type for a in alarms if a.type_prior <= 0.35
    )
    if symptom_types:
        top = ", ".join(f"{t} x{n}" for t, n in symptom_types.most_common(3))
        evidence.append(
            f"Semptom profili: olaydaki turev alarmlarin cogunlugu {top} — "
            "bunlar neden degil, sonuc kayitlaridir."
        )

    # Mekansal kanit
    locations = Counter(a.location for a in alarms)
    if len(locations) == 1:
        loc = next(iter(locations))
        evidence.append(
            f"Konum: olaydaki {len(alarms)} alarmin tamami {loc} konumunda — "
            "ortak fiziksel altyapi supheli."
        )
    else:
        top_loc, top_n = locations.most_common(1)[0]
        if top_n / len(alarms) >= 0.6:
            evidence.append(
                f"Konum: alarmlarin %{100 * top_n / len(alarms):.0f}'i "
                f"{top_loc} konumunda yogunlasmis."
            )

    return evidence


def _build_explanation(
    incident: Incident, root: Alarm, graph: DependencyGraph
) -> str:
    """Kok neden kararini dogal dille anlatir."""
    dependents = sorted(graph.dependents_of(root.service))
    affected = [s for s in incident.services if s != root.service]

    lines = [
        f"{root.timestamp.strftime('%H:%M:%S')}'de {root.host} sunucusundaki "
        f"{root.service} servisi '{root.alarm_type}' alarmi uretti "
        f"(siddet {root.severity}/{root.severity_label}): \"{root.message}\".",
    ]

    if dependents:
        lines.append(
            f"{root.service}, bagimlilik grafiginde {len(dependents)} servisin "
            f"dogrudan dayandigi bir bilesen ({', '.join(dependents[:4])}"
            f"{'...' if len(dependents) > 4 else ''})."
        )

    if affected:
        lines.append(
            f"Bu alarmin ardindan {len(affected)} bagimli serviste "
            f"({', '.join(affected[:5])}{'...' if len(affected) > 5 else ''}) "
            f"toplam {incident.alarm_count - 1} turev alarm olustu; "
            f"olay {incident.duration_minutes:.0f} dakika surdu."
        )
    else:
        lines.append(
            f"Olay {root.service} servisinde sinirli kaldi; "
            f"{incident.duration_minutes:.0f} dakikada {incident.alarm_count} "
            "alarm uretti."
        )

    lines.append(
        "Zaman onceligi, topolojik merkezilik ve alarm tipinin neden egilimi "
        "birlikte degerlendirildiginde bu kayit olayin tetikleyicisi olarak "
        "en yuksek puani aldi."
    )

    return " ".join(lines)


def _build_counter_reason(
    root: Alarm, counter: Alarm, graph: DependencyGraph, delta: float
) -> str:
    """Karsi hipotezin neden ciddiye alinmasi gerektigini anlatir."""
    upstream = graph.upstream_set(root.service, max_hops=config.MERGE_MAX_HOPS)

    parts = [
        f"{counter.timestamp.strftime('%H:%M:%S')}'de {counter.service} "
        f"servisinde '{counter.alarm_type}' alarmi ({counter.alarm_id}, "
        f"siddet {counter.severity}) var ve puani kok nedene "
        f"{delta:.1f} puan yakin."
    ]

    if counter.service in upstream:
        parts.append(
            f"{root.service}, {counter.service} servisine bagimli — yani "
            f"gercek tetikleyici {counter.service} olabilir ve {root.service} "
            "alarmi aslinda bir semptom olabilir."
        )
    elif counter.timestamp < root.timestamp:
        parts.append(
            f"Ustelik {counter.service} alarmi kok neden adayindan once geldi; "
            "zaman sirasi ters hipotezi destekliyor."
        )
    else:
        parts.append(
            f"{counter.service} bagimsiz bir dalda; bu olayin aslinda iki ayri "
            "arizanin ust uste binmesi olma ihtimalini disarida birakmiyor."
        )

    parts.append(
        f"Dogrulama: {counter.host} uzerinde {counter.alarm_type} metriklerini "
        f"{counter.timestamp.strftime('%H:%M')} civari icin kontrol edin."
    )
    return " ".join(parts)


# --------------------------------------------------------------------------
# Aksiyon onerisi
# --------------------------------------------------------------------------

_ACTION_BY_TYPE = {
    "network_down": "Arayuzun fiziksel baglantisini ve switch port durumunu kontrol edin; gerekirse yedek hatta gecin.",
    "network_flap": "Link flap kaynagini (kablo/SFP/switch portu) tespit edin ve portu stabilize edin.",
    "pkt_loss": "Yol boyunca paket kaybi olcumu yapin; rack ustu switch ve uplink sayaclarini inceleyin.",
    "disk_full": "Diski acil bosaltin (log/temp temizligi), ardindan kalici kapasite artisi planlayin.",
    "db_write_fail": "Veritabani yazma hatalarinin kaynagini (disk, replikasyon, kilit) inceleyin ve yazma trafigini gecici olarak kisin.",
    "db_conn_pool": "Baglantı havuzu boyutunu ve sizintiyi kontrol edin; uzun suren sorgulari sonlandirin.",
    "oom_risk": "Servisi kontrollu yeniden baslatin ve heap/bellek profilini alarak sizinti kaynagini bulun.",
    "mem_high": "Bellek tuketimini profilleyin; gerekirse ornek sayisini artirin.",
    "gc_pressure": "GC duraklamalarini analiz edin, heap boyutu ve GC parametrelerini gozden gecirin.",
    "ext_unreach": "Dis saglayici durumunu dogrulayin, devre kesiciyi (circuit breaker) devreye alin ve saglayiciyla iletisime gecin.",
    "ext_slow": "Dis saglayici gecikmesini olcun; zaman asimi ve yeniden deneme politikasini gecici olarak sikilastirin.",
    "batch_overlap": "Cakisan toplu is pencerelerini ayirin; calisan islerden dusuk oncelikli olani durdurun.",
    "batch_slow": "Toplu isin kaynak rekabetini inceleyin; pencereyi uzatin veya paralelligi azaltin.",
    "cpu_high": "CPU tuketen sureci tespit edin; gerekirse yatay olcekleme yapin.",
    "thread_pool": "Is parcacigi havuzu doygunlugunun kaynagini (yavas bagimlilik) bulun ve havuz boyutunu gecici artirin.",
    "conn_refused": "Hedef servisin ayakta olup olmadigini ve dinleme portunu dogrulayin.",
    "http_5xx": "Hata orani artisinin kaynagini uygulama loglarindan izleyin; son dagitimi geri alma secenegini degerlendirin.",
    "queue_backlog": "Tuketici kapasitesini artirin ve birikmis kuyrugu bosaltin.",
    "txn_fail": "Basarisiz islem orneklerini inceleyip etkilenen musteri islemlerini yeniden kuyruklayin.",
    "timeout": "Zaman asimina ugrayan bagimliligi tespit edin ve o servisin sagligini kontrol edin.",
    "latency_high": "p99 gecikme artisinin kaynagini (bagimlilik, GC, IO) izleyin.",
}

_DEFAULT_ACTION = (
    "Kok neden adayi sunucuda ilgili servisin loglarini ve kaynak "
    "metriklerini inceleyin."
)


def recommend_action(root: Alarm, incident: Incident) -> str:
    base = _ACTION_BY_TYPE.get(root.alarm_type, _DEFAULT_ACTION)
    return (
        f"{root.host} / {root.service}: {base} "
        f"(Etki: {len(incident.services)} servis, {incident.alarm_count} alarm.)"
    )


def suggest_owner(root: Alarm) -> str:
    """Alarm tipinden sorumlu ekibi turetir."""
    t = root.alarm_type
    if t in {"network_down", "network_flap", "pkt_loss", "conn_refused"}:
        return "network-oncall"
    if t in {"db_write_fail", "db_conn_pool"}:
        return "database-oncall"
    if t in {"disk_full", "disk_warn", "backup_warn"}:
        return "storage-oncall"
    if t in {"ext_unreach", "ext_slow"}:
        return "vendor-liaison"
    if t in {"batch_overlap", "batch_slow"}:
        return "batch-oncall"
    return "platform-oncall"


# --------------------------------------------------------------------------


def analyse_incident(incident: Incident, graph: DependencyGraph) -> Incident:
    """Olayin kok nedenini, karsi hipotezini ve aciklamasini doldurur."""
    alarms = incident.alarms
    if not alarms:
        return incident

    shares = _service_shares(incident)
    scored = [
        (score_alarm(a, incident, graph, shares), a) for a in alarms
    ]
    # Deterministik siralama: puan, sonra zaman, sonra kimlik.
    scored.sort(key=lambda pair: (-pair[0]["total"], pair[1].timestamp, pair[1].alarm_id))

    root_score, root = scored[0]
    incident.root_cause = root
    incident.root_cause_score = root_score

    # Karsi hipotez: tercihen farkli servisten en yuksek puanli alarm.
    counter_pair = next(
        (pair for pair in scored[1:] if pair[1].service != root.service), None
    )
    if counter_pair is None:
        counter_pair = scored[1] if len(scored) > 1 else None

    if counter_pair is not None:
        counter_score, counter = counter_pair
        incident.counter_hypothesis = counter
        incident.counter_score = counter_score
        incident.counter_reason = _build_counter_reason(
            root, counter, graph, root_score["total"] - counter_score["total"]
        )

    incident.explanation = _build_explanation(incident, root, graph)
    incident.explanation_source = "template"
    return incident


def analyse_all(incidents: list[Incident], graph: DependencyGraph) -> list[Incident]:
    return [analyse_incident(inc, graph) for inc in incidents]


def evidence_for(incident: Incident, graph: DependencyGraph) -> list[str]:
    if incident.root_cause is None:
        return []
    return _ordinal_evidence(incident, incident.root_cause, graph)


def _main() -> None:
    """`python -m src.root_cause` — kok neden ozeti."""
    from src.baseline import BaselineModel
    from src.clustering import build_clusters
    from src.correlation import merge_clusters
    from src.data_loader import load_all
    from src.noise_filter import filter_noise

    data = load_all()
    model = BaselineModel(data.alarms)
    noise = filter_noise(data.alarms, model)
    result, _ = build_clusters(noise.signal)
    incidents = analyse_all(merge_clusters(result.clusters, data.graph), data.graph)

    print()
    print("Faz 3.2/3.3 - Kok neden puanlamasi")
    print("=" * 78)
    for inc in incidents:
        root = inc.root_cause
        print()
        print(
            f"{inc.incident_id}  {inc.start.strftime('%H:%M')}-"
            f"{inc.end.strftime('%H:%M')}  {inc.alarm_count} alarm  "
            f"{len(inc.services)} servis"
        )
        print(
            f"  KOK NEDEN  {root.alarm_id}  {root.service}/{root.host}  "
            f"{root.alarm_type}  sev={root.severity}  "
            f"puan={inc.root_cause_score['total']}"
        )
        print(f"             {inc.root_cause_score}")
        if inc.counter_hypothesis:
            c = inc.counter_hypothesis
            print(
                f"  KARSI HIP. {c.alarm_id}  {c.service}/{c.host}  "
                f"{c.alarm_type}  puan={inc.counter_score['total']}"
            )
    print()


if __name__ == "__main__":
    _main()
