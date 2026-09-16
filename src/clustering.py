"""Gorev 2.2 — Cift pencereli zamansal kumeleme.

Gurultu filtresinden gecen alarmlari iki farkli pencere mantigiyla kumeler:

**Kisa pencere (burst).** Servisin taban oranini astigi *artis penceresi*
icindeki alarmlar tek bir kumeye girer. Ani patlama seklindeki olaylar
(rack-A ag kesintisi, disk dolmasi, dis saglayici erisilmezligi) boyle
yakalanir. Pencerenin kendisi `BaselineModel` tarafindan, servisin kendi
normaline gore belirlenir — sabit bir "4 dakika" esigi bu veri setinde ise
yaramaz, cunku bazi servisler dakikada 2 alarm uretirken bazilari saatte 2
uretiyor.

**Uzun pencere (slow-burn).** Artis uretmeyen, ama saatlere yayilarak sinsice
kotulesenler. Artis penceresine girmemis sinyal alarmlari, servis bazinda en
fazla `SLOW_BURN_WINDOW_MIN` (20 dk) boslukla zincirlenir. Zincirin gecerli
sayilmasi icin en az 4 alarm ve en az bir siddet >= 3 kaydi gerekir; boylece
arka plan artiklari yanlislikla olaya donusmez. `session-service` bellek
sizintisi (02:11 gc_pressure -> 02:52 oom_risk) tam olarak bu yolla cikar.

Hicbir kumeye giremeyen sinyal alarmlari `residual` listesinde tasinir —
Faz 4'te "Diger / Kumelenmemis" kartina dahil edilirler. Veri kaybi sifir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src import config
from src.baseline import BaselineModel
from src.models import Alarm, TemporalCluster


@dataclass(slots=True)
class ClusterResult:
    clusters: list[TemporalCluster] = field(default_factory=list)
    residual: list[Alarm] = field(default_factory=list)

    @property
    def clustered_count(self) -> int:
        return sum(len(c.alarms) for c in self.clusters)

    def kind_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cluster in self.clusters:
            counts[cluster.window_kind] = counts.get(cluster.window_kind, 0) + 1
        return dict(sorted(counts.items()))


# --------------------------------------------------------------------------


def _window_pass(
    alarms: list[Alarm],
    windows_by_service: dict[str, list],
    window_kind: str,
    min_alarms: int,
    counter: list[int],
    require_severity: int = 0,
) -> tuple[list[TemporalCluster], list[Alarm]]:
    """Verilen artis pencerelerinden kume uretir; sahiplenilmeyenleri dondurur."""
    clusters: list[TemporalCluster] = []
    claimed: set[str] = set()

    by_service: dict[str, list[Alarm]] = defaultdict(list)
    for alarm in alarms:
        by_service[alarm.service].append(alarm)

    for service in sorted(by_service):
        bucket = sorted(by_service[service], key=lambda a: (a.timestamp, a.alarm_id))
        for window in windows_by_service.get(service, ()):
            members = [
                a
                for a in bucket
                if a.alarm_id not in claimed and window.contains(a.timestamp)
            ]
            if len(members) < min_alarms:
                continue
            if require_severity and max(a.severity for a in members) < require_severity:
                continue
            counter[0] += 1
            clusters.append(
                TemporalCluster(
                    cluster_id=f"CL-{counter[0]:03d}",
                    service=service,
                    alarms=members,
                    window_kind=window_kind,
                )
            )
            claimed.update(a.alarm_id for a in members)

    leftover = [a for a in alarms if a.alarm_id not in claimed]
    return clusters, leftover


# --------------------------------------------------------------------------


def build_clusters(signal: list[Alarm]) -> tuple[ClusterResult, BaselineModel]:
    """Sinyal alarmlarini cift pencereli mantikla kumeler.

    Taban orani modeli **sinyal uzerinde yeniden** kurulur: gurultu ayiklandigi
    icin artis pencereleri artik gercek olaylarin sinirlarini cok daha keskin
    ciziyor.
    """
    if not signal:
        return ClusterResult(), None  # type: ignore[return-value]

    signal_model = BaselineModel(signal)
    counter = [0]

    # 1) Kisa pencere: keskin patlamalar once sahiplenilir.
    burst_clusters, leftover = _window_pass(
        signal,
        signal_model.burst_windows,
        window_kind="burst",
        min_alarms=config.BURST_MIN_ALARMS,
        counter=counter,
    )

    # 2) Uzun pencere: patlamaya girmeyen, yavas kotulesen dalgalar.
    slow_clusters, residual = _window_pass(
        leftover,
        signal_model.slow_windows,
        window_kind="slow_burn",
        min_alarms=config.SLOW_BURN_MIN_ALARMS,
        counter=counter,
        require_severity=config.SLOW_BURN_MIN_SEVERITY,
    )

    clusters = burst_clusters + slow_clusters
    clusters.sort(key=lambda c: (c.start, c.service))

    return ClusterResult(clusters=clusters, residual=residual), signal_model


def _main() -> None:
    """`python -m src.clustering` — kumeleme ozeti."""
    from src.data_loader import load_all
    from src.noise_filter import filter_noise

    data = load_all()
    model = BaselineModel(data.alarms)
    noise = filter_noise(data.alarms, model)
    result, _ = build_clusters(noise.signal)

    print()
    print("Faz 2.2 - Cift pencereli zamansal kumeleme")
    print("-" * 74)
    print(f"  sinyal alarm   : {len(noise.signal)}")
    print(f"  kume sayisi    : {len(result.clusters)}  {result.kind_counts()}")
    print(f"  kumelenen alarm: {result.clustered_count}")
    print(f"  artik (residual): {len(result.residual)}")
    print(
        f"  denge kontrolu : {result.clustered_count + len(result.residual)} "
        f"== {len(noise.signal)}"
    )
    print()
    print(
        f"  {'kume':<8}{'servis':<24}{'tip':<11}{'n':>4}  zaman araligi"
    )
    for cluster in result.clusters:
        print(
            f"  {cluster.cluster_id:<8}{cluster.service:<24}"
            f"{cluster.window_kind:<11}{len(cluster):>4}  "
            f"{cluster.start.strftime('%H:%M:%S')} - "
            f"{cluster.end.strftime('%H:%M:%S')}  sev_max={cluster.max_severity}"
        )
    print()


if __name__ == "__main__":
    _main()
