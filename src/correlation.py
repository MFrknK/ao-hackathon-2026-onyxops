"""Gorev 3.1 — Topolojik birlestirme.

Faz 2 kumeleri **servis bazlidir**: her kume tek bir servisin zaman icindeki
yogunlasmasini temsil eder. Ama gercek bir olay nadiren tek serviste kalir —
`billing-db` diski dolunca `billing-service` yazma hatasi verir, `invoice-batch`
takilir. Bu uc kume tek bir olaydir.

Bu modul kumeleri iki gerekceyle birlestirir:

1. **Bagimlilik yakinligi** — servisler bagimlilik grafiginde en fazla
   `MERGE_MAX_HOPS` atlama mesafesinde ve **baslangic anlari** arasindaki fark
   `MERGE_ONSET_GAP_MIN` dakikadan az.

2. **Mekansal yakinlik** — ayni `veri_merkezi/kabin` ikilisini paylasiyorlar ve
   baslangic farki `MERGE_LOCALITY_ONSET_GAP_MIN` dakikadan az. Ortak guc/ag
   altyapisi varsayimi; rack-A ag kesintisi gibi olaylar bagimlilik grafiginde
   birbirine uzak servisleri ayni anda vurur.

**Neden baslangic ani, aralik ortusmesi degil?** Slow-burn kumeleri 20-40
dakikaya yayiliyor. 2 saatlik bir pencerede "araliklari ortusuyor mu" testi
neredeyse her kumeyi her kumeye baglar ve gecisli birlesme sonucunda 56 kume
tek bir olaya coker (ilk denemede tam olarak bu oldu). Oysa bir arizanin
imzasi, bagimli servislerin **birbiri ardina bozulmaya baslamasidir**.

Birlestirme **birlesim-bulma** (union-find) ile gecisli uygulanir: A~B ve B~C
ise A, B, C tek olaydir. Gecisliligin tum geceyi yutmamasi icin bir fren var:
birlesme sonucu olusacak olayin suresi `INCIDENT_MAX_SPAN_MIN` degerini
asiyorsa birlestirme reddedilir. Adaylar en yakin baslangictan uzaga dogru
islenir, boylece en guclu baglar once kurulur.

Her birlestirme gerekcesi metin olarak saklanir ve olay kartinda kanit olarak
gosterilir.
"""

from __future__ import annotations

from src import config
from src.models import Incident, TemporalCluster
from src.topology import DependencyGraph


class _SpanGuardedUnionFind:
    """Birlesim-bulma + "olusacak olay cok uzun olmasin" freni."""

    def __init__(self, clusters: list[TemporalCluster]):
        self.parent = list(range(len(clusters)))
        self.start = [c.start for c in clusters]
        self.end = [c.end for c in clusters]

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int, max_span_min: float) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False

        start = min(self.start[ra], self.start[rb])
        end = max(self.end[ra], self.end[rb])
        if (end - start).total_seconds() / 60.0 > max_span_min:
            return False

        # Kucuk indeks kok olur -> deterministik sonuc.
        winner, loser = (ra, rb) if ra < rb else (rb, ra)
        self.parent[loser] = winner
        self.start[winner] = start
        self.end[winner] = end
        return True


def _onset_gap_minutes(a: TemporalCluster, b: TemporalCluster) -> float:
    """Iki kumenin **ilk alarm** anlari arasindaki mutlak fark (dakika)."""
    return abs((a.start - b.start).total_seconds()) / 60.0


def _link_reason(
    a: TemporalCluster, b: TemporalCluster, graph: DependencyGraph
) -> str | None:
    """Iki kume ayni olaya mi ait? Gerekceyi dondurur, degilse None."""
    gap = _onset_gap_minutes(a, b)

    def when() -> str:
        return "es zamanli" if gap < 1 else f"{gap:.0f} dk arayla"

    # 1) Bagimlilik yakinligi
    if gap <= config.MERGE_ONSET_GAP_MIN:
        related, how = graph.are_related(a.service, b.service, config.MERGE_MAX_HOPS)
        if related:
            return (
                f"{a.service} ve {b.service} {when()} bozulmaya basladi; {how} "
                "(bagimlilik yakinligi)."
            )

    # 2) Mekansal yakinlik — ortak rack/DC
    if gap <= config.MERGE_LOCALITY_ONSET_GAP_MIN:
        shared = sorted(a.locations & b.locations)
        if shared:
            return (
                f"{a.service} ve {b.service} {when()} bozulmaya basladi ve ayni "
                f"fiziksel konumu paylasiyor ({', '.join(shared)}) — ortak "
                "altyapi (mekansal yakinlik)."
            )

    return None


def merge_clusters(
    clusters: list[TemporalCluster], graph: DependencyGraph
) -> list[Incident]:
    """Zamansal kumeleri topolojik/mekansal yakinliga gore olaylara birlestirir."""
    if not clusters:
        return []

    ordered = sorted(clusters, key=lambda c: (c.start, c.service, c.cluster_id))
    uf = _SpanGuardedUnionFind(ordered)

    # Once tum aday ciftleri ve gerekcelerini topla.
    candidates: list[tuple[float, int, int, str]] = []
    limit = max(config.MERGE_ONSET_GAP_MIN, config.MERGE_LOCALITY_ONSET_GAP_MIN)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            gap = _onset_gap_minutes(ordered[i], ordered[j])
            if gap > limit:
                break  # zaman sirali: sonraki j'ler daha da uzak
            reason = _link_reason(ordered[i], ordered[j], graph)
            if reason is not None:
                candidates.append((gap, i, j, reason))

    # En yakin baslangictan uzaga dogru birlestir ki en guclu baglar once
    # kurulsun ve sure freni zayif baglari kessin.
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))

    reasons: dict[int, list[str]] = {}
    for _gap, i, j, reason in candidates:
        if uf.union(i, j, config.INCIDENT_MAX_SPAN_MIN):
            reasons.setdefault(uf.find(i), []).append(reason)

    # Kokleri topla
    groups: dict[int, list[int]] = {}
    for idx in range(len(ordered)):
        groups.setdefault(uf.find(idx), []).append(idx)

    # Gerekceleri nihai koke tasi (union sirasinda kok degismis olabilir).
    final_reasons: dict[int, list[str]] = {}
    for root, texts in reasons.items():
        final_reasons.setdefault(uf.find(root), []).extend(texts)

    incidents: list[Incident] = []
    ordered_roots = sorted(groups, key=lambda r: min(ordered[i].start for i in groups[r]))

    for number, root in enumerate(ordered_roots, start=1):
        members = [ordered[i] for i in sorted(groups[root])]
        seen: set[str] = set()
        unique_reasons: list[str] = []
        for text in final_reasons.get(root, []):
            if text not in seen:
                seen.add(text)
                unique_reasons.append(text)

        incidents.append(
            Incident(
                incident_id=f"INC-{number:03d}",
                clusters=members,
                merge_reasons=unique_reasons,
            )
        )

    incidents.sort(key=lambda inc: inc.start)
    for number, incident in enumerate(incidents, start=1):
        incident.incident_id = f"INC-{number:03d}"

    return incidents


def _main() -> None:
    """`python -m src.correlation` — birlestirme ozeti."""
    from src.baseline import BaselineModel
    from src.clustering import build_clusters
    from src.data_loader import load_all
    from src.noise_filter import filter_noise

    data = load_all()
    model = BaselineModel(data.alarms)
    noise = filter_noise(data.alarms, model)
    result, _ = build_clusters(noise.signal)
    incidents = merge_clusters(result.clusters, data.graph)

    print()
    print("Faz 3.1 - Topolojik birlestirme")
    print("-" * 78)
    print(f"  kume  : {len(result.clusters)}")
    print(f"  olay  : {len(incidents)}")
    print()
    for inc in incidents:
        print(
            f"  {inc.incident_id}  {inc.alarm_count:>4} alarm  "
            f"{inc.start.strftime('%H:%M')}-{inc.end.strftime('%H:%M')}  "
            f"({len(inc.clusters)} kume, sev_max={inc.max_severity})"
        )
        print(f"           servisler: {', '.join(inc.services)}")
        if inc.merge_reasons:
            print(f"           gerekce  : {inc.merge_reasons[0]}")
    print()


if __name__ == "__main__":
    _main()
