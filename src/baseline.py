"""Servis taban orani (baseline) ve cift duyarlikli artis penceresi modeli.

Faz 2'nin hem gurultu filtresi hem de kumeleme adimi bu modele dayanir.

**Neden gerekli?** Veri kesfi sunu gosterdi: 27 servisin tamami 2 saat boyunca
kesintisiz alarm uretiyor. `mobile-bff` 121 dakikada 278 alarm cikariyor, yani
dakikada ~2.3. Boyle bir akista "bu alarm yalniz mi?" veya "onceki alarmla
arasi 4 dakikadan az mi?" sorulari hicbir sey ayirt etmiyor: her sey her seye
bitisik, tum pencere tek bir kumeye cokerdi.

**Cozum.** Her servisin kendi normalini olcuyoruz. Taban orani olarak dakika
basi alarm sayisinin **medyani** aliniyor — medyan, olay patlamalarindan
etkilenmedigi icin "normal gece trafigi"ni temsil ediyor. Ustune iki ayri
duyarlikta dedektor calisiyor:

* **BURST**  — 3 dakikalik pencere, tabanin 3 katini asma sarti. Ani patlamayi
  keskin sinirlarla keser (rack-A ag kesintisi, disk dolmasi).
* **SLOW**   — 9 dakikalik pencere, tabanin 1.8 katini asma sarti. Keskin tepe
  yapmayan, saatlere yayilan sinsi kotulesmeyi yakalar (session-service bellek
  sizintisi).

Ikisinin de disinda kalan akis arka plan gurultusudur. Alarm tipi dagilimi bu
yorumu dogruluyor: `cert_expiry`, `ntp_drift`, `log_rotate`, `disk_warn`,
`backup_warn` tiplerinin zamandaki standart sapmasi ~34 dk; 121 dakikalik
pencerede tam duzgun dagilimin beklenen degeri 121/sqrt(12) = 34.9. Buna
karsilik `network_down` (0.8), `pkt_loss` (0.8), `ext_unreach` (0.9),
`disk_full` (1.5) dakikalar icine sikismis — bunlar olaydir.
"""

from __future__ import annotations

import statistics
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from src import config
from src.models import Alarm


@dataclass(slots=True, frozen=True)
class ActivityWindow:
    """Bir servisin taban oranini astigi kesintisiz zaman araligi."""

    service: str
    kind: str  # "burst" | "slow"
    start: datetime
    end: datetime
    peak_count: int
    baseline_per_min: float

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end

    @property
    def duration_minutes(self) -> float:
        return round((self.end - self.start).total_seconds() / 60.0, 1)

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "kind": self.kind,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_minutes": self.duration_minutes,
            "peak_count": self.peak_count,
            "baseline_per_min": round(self.baseline_per_min, 2),
        }


class BaselineModel:
    """Servis bazli taban orani + cift duyarlikli artis penceresi tespiti."""

    def __init__(self, alarms: list[Alarm]):
        if not alarms:
            raise ValueError("BaselineModel bos alarm listesiyle kurulamaz")

        self.t0 = min(a.timestamp for a in alarms)
        self.t1 = max(a.timestamp for a in alarms)
        self.total_minutes = int((self.t1 - self.t0).total_seconds() // 60) + 1

        self._by_service: dict[str, list[Alarm]] = defaultdict(list)
        for alarm in alarms:
            self._by_service[alarm.service].append(alarm)

        # Host bazli zaman dizini — gurultu filtresinin yalnizlik testi icin.
        self._host_times: dict[str, list[datetime]] = defaultdict(list)
        for alarm in alarms:
            self._host_times[alarm.host].append(alarm.timestamp)
        for times in self._host_times.values():
            times.sort()

        self.baselines: dict[str, float] = {}
        self.burst_windows: dict[str, list[ActivityWindow]] = {}
        self.slow_windows: dict[str, list[ActivityWindow]] = {}

        for service in sorted(self._by_service):
            series = self._series(service)
            baseline = float(statistics.median(series))
            self.baselines[service] = baseline
            self.burst_windows[service] = self._detect(
                service, series, baseline, "burst", config.BURST_DETECTOR
            )
            self.slow_windows[service] = self._detect(
                service, series, baseline, "slow", config.SLOW_DETECTOR
            )

    # ------------------------------------------------------------- dahili

    def _bins(self) -> int:
        return self.total_minutes // config.BASELINE_BIN_MINUTES + 1

    def _bin_index(self, moment: datetime) -> int:
        return int(
            (moment - self.t0).total_seconds() // (60 * config.BASELINE_BIN_MINUTES)
        )

    def _bin_start(self, idx: int) -> datetime:
        return self.t0 + timedelta(minutes=idx * config.BASELINE_BIN_MINUTES)

    def _series(self, service: str) -> list[int]:
        series = [0] * self._bins()
        for alarm in self._by_service[service]:
            series[self._bin_index(alarm.timestamp)] += 1
        return series

    def _detect(
        self,
        service: str,
        series: list[int],
        baseline: float,
        kind: str,
        params: dict,
    ) -> list[ActivityWindow]:
        """Yuvarlanan toplam esigi asan dakikalari pencerelere donusturur."""
        half = params["rolling_minutes"] // 2
        threshold = max(
            float(params["min_count"]),
            baseline * params["multiplier"] + params["margin"],
        )

        hot = [
            idx
            for idx in range(len(series))
            if sum(series[max(0, idx - half) : idx + half + 1]) > threshold
        ]

        windows: list[ActivityWindow] = []
        last: int | None = None
        for idx in hot:
            if windows and last is not None and idx - last <= config.SPIKE_MERGE_GAP_MIN:
                prev = windows[-1]
                windows[-1] = ActivityWindow(
                    service=service,
                    kind=kind,
                    start=prev.start,
                    end=self._bin_start(idx + 1),
                    peak_count=max(prev.peak_count, series[idx]),
                    baseline_per_min=baseline,
                )
            else:
                windows.append(
                    ActivityWindow(
                        service=service,
                        kind=kind,
                        start=self._bin_start(idx),
                        end=self._bin_start(idx + 1),
                        peak_count=series[idx],
                        baseline_per_min=baseline,
                    )
                )
            last = idx

        # Kenarlari yuvarlanan pencerenin yaricapi kadar genislet ki artisi
        # tetikleyen ilk/son alarmlar disarida kalmasin.
        pad = timedelta(minutes=half * config.BASELINE_BIN_MINUTES)
        return [
            ActivityWindow(
                service=w.service,
                kind=w.kind,
                start=w.start - pad,
                end=w.end + pad,
                peak_count=w.peak_count,
                baseline_per_min=w.baseline_per_min,
            )
            for w in windows
        ]

    # ------------------------------------------------------------- sorgular

    def burst_window(self, alarm: Alarm) -> ActivityWindow | None:
        for window in self.burst_windows.get(alarm.service, ()):
            if window.contains(alarm.timestamp):
                return window
        return None

    def slow_window(self, alarm: Alarm) -> ActivityWindow | None:
        for window in self.slow_windows.get(alarm.service, ()):
            if window.contains(alarm.timestamp):
                return window
        return None

    def active_window(self, alarm: Alarm) -> ActivityWindow | None:
        """Once keskin, sonra genis dedektore bakar."""
        return self.burst_window(alarm) or self.slow_window(alarm)

    def in_spike(self, alarm: Alarm) -> bool:
        return self.active_window(alarm) is not None

    def baseline_of(self, service: str) -> float:
        return self.baselines.get(service, 0.0)

    def host_neighbours(self, alarm: Alarm, window_minutes: int) -> int:
        """Ayni sunucuda, +/- pencere icinde kac **baska** alarm var?"""
        times = self._host_times.get(alarm.host, [])
        delta = timedelta(minutes=window_minutes)
        lo = bisect_left(times, alarm.timestamp - delta)
        hi = bisect_right(times, alarm.timestamp + delta)
        return max(0, (hi - lo) - 1)

    def all_windows(self) -> list[ActivityWindow]:
        out = [
            w
            for source in (self.burst_windows, self.slow_windows)
            for windows in source.values()
            for w in windows
        ]
        out.sort(key=lambda w: (w.start, w.service, w.kind))
        return out

    def summary(self) -> dict:
        return {
            "services": len(self.baselines),
            "burst_windows": sum(len(v) for v in self.burst_windows.values()),
            "slow_windows": sum(len(v) for v in self.slow_windows.values()),
            "mean_baseline_per_min": round(
                statistics.mean(self.baselines.values()) if self.baselines else 0.0, 2
            ),
        }
