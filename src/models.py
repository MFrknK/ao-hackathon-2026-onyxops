"""Pipeline boyunca tasinan veri siniflari.

Tum asamalar (yukleme -> gurultu -> kumeleme -> birlestirme -> kart) bu
nesneler uzerinde calisir. Her sinif kendi JSON temsilini uretebilir ki
cikti sozlesmesi tek yerde tanimli kalsin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src import config

# --------------------------------------------------------------------------


@dataclass(slots=True)
class HostInfo:
    """host_inventory.csv satiri (Gorev 1.1)."""

    host: str
    service: str
    datacenter: str
    rack: str
    environment: str
    criticality: str

    @property
    def location(self) -> str:
        """Mekansal yakinlik karsilastirmalarinda kullanilan anahtar."""
        return f"{self.datacenter}/{self.rack}"


@dataclass(slots=True)
class Dependency:
    """service_dependencies.csv satiri (Gorev 1.2).

    Okuma yonu: `source` servisi `target` servisine bagimlidir. Yani `target`
    bozulursa `source` etkilenir.
    """

    source: str
    target: str
    kind: str        # senkron | asenkron
    criticality: str  # hedef servisin is kritikligi


@dataclass(slots=True)
class Alarm:
    """Zenginlestirilmis alarm kaydi (Gorev 1.3)."""

    alarm_id: str
    timestamp: datetime
    source_system: str
    host: str
    service: str
    severity: int
    alarm_type: str
    message: str

    # --- Zenginlestirme (host envanterinden) ---
    datacenter: str = ""
    rack: str = ""
    environment: str = ""
    criticality: str = ""
    host_service: str = ""

    # --- Faz 2 isaretleri ---
    is_noise: bool = False
    noise_reason: str = ""

    @property
    def location(self) -> str:
        return f"{self.datacenter}/{self.rack}"

    @property
    def severity_label(self) -> str:
        return config.SEVERITY_LABELS.get(self.severity, str(self.severity))

    @property
    def type_prior(self) -> float:
        """Alarm tipinin 'kok neden olma' egilimi (0.0 semptom - 1.0 neden)."""
        return config.ALARM_TYPE_PRIOR.get(self.alarm_type, config.DEFAULT_TYPE_PRIOR)

    def to_dict(self) -> dict:
        return {
            "alarm_id": self.alarm_id,
            "timestamp": self.timestamp.isoformat(),
            "source_system": self.source_system,
            "host": self.host,
            "service": self.service,
            "severity": self.severity,
            "severity_label": self.severity_label,
            "alarm_type": self.alarm_type,
            "message": self.message,
            "datacenter": self.datacenter,
            "rack": self.rack,
            "criticality": self.criticality,
        }


@dataclass(slots=True)
class NoiseEntry:
    """Gurultu Defteri kaydi — elenen alarm hicbir zaman silinmez (Gorev 2.1)."""

    alarm: Alarm
    rule: str     # kuralin makine adi
    reason: str   # insan tarafindan okunabilir gerekce

    def to_dict(self) -> dict:
        return {
            **self.alarm.to_dict(),
            "noise_rule": self.rule,
            "noise_reason": self.reason,
        }


@dataclass(slots=True)
class TemporalCluster:
    """Faz 2.2 ciktisi: ayni servis icinde zamansal olarak bitisik alarmlar."""

    cluster_id: str
    service: str
    alarms: list[Alarm]
    window_kind: str  # "burst" | "slow_burn"

    @property
    def start(self) -> datetime:
        return self.alarms[0].timestamp

    @property
    def end(self) -> datetime:
        return self.alarms[-1].timestamp

    @property
    def hosts(self) -> set[str]:
        return {a.host for a in self.alarms}

    @property
    def locations(self) -> set[str]:
        return {a.location for a in self.alarms}

    @property
    def max_severity(self) -> int:
        return max(a.severity for a in self.alarms)

    def __len__(self) -> int:
        return len(self.alarms)


@dataclass(slots=True)
class Incident:
    """Faz 3 ciktisi: topolojik olarak birlestirilmis bir veya daha fazla kume."""

    incident_id: str
    clusters: list[TemporalCluster]
    merge_reasons: list[str] = field(default_factory=list)

    # Faz 3.2 / 3.3 tarafindan doldurulur
    root_cause: Alarm | None = None
    root_cause_score: dict[str, float] = field(default_factory=dict)
    counter_hypothesis: Alarm | None = None
    counter_score: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    counter_reason: str = ""
    explanation_source: str = "template"  # "template" | "llm"

    # Faz 4 tarafindan doldurulur
    priority_score: float = 0.0
    priority_breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def alarms(self) -> list[Alarm]:
        out = [a for c in self.clusters for a in c.alarms]
        out.sort(key=lambda a: (a.timestamp, a.alarm_id))
        return out

    @property
    def alarm_count(self) -> int:
        return sum(len(c.alarms) for c in self.clusters)

    @property
    def services(self) -> list[str]:
        return sorted({a.service for c in self.clusters for a in c.alarms})

    @property
    def hosts(self) -> list[str]:
        return sorted({a.host for c in self.clusters for a in c.alarms})

    @property
    def locations(self) -> list[str]:
        return sorted({a.location for c in self.clusters for a in c.alarms})

    @property
    def start(self) -> datetime:
        return min(c.start for c in self.clusters)

    @property
    def end(self) -> datetime:
        return max(c.end for c in self.clusters)

    @property
    def duration_minutes(self) -> float:
        return round((self.end - self.start).total_seconds() / 60.0, 1)

    @property
    def max_severity(self) -> int:
        return max(c.max_severity for c in self.clusters)

    @property
    def window_kinds(self) -> list[str]:
        return sorted({c.window_kind for c in self.clusters})
