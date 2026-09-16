"""Gorev 2.1 — Gurultu filtresi ve Gurultu Defteri.

**Hicbir alarm silinmez.** Elenen her kayit, hangi kuralla ve neden elendigi
yazili olarak `NoiseEntry` halinde deftere gecer; panodaki "Gurultu Denetimi"
sekmesinde tek tek incelenebilir. Bu, senaryonun X-Factor gereksinimlerinden
biri (elenen alarmlarin neden elendigini gosteren denetim gorunumu).

Kurallar sirayla denenir; ilk eslesen kural kaydi sahiplenir.

1. `isolated_low_severity` — Plandaki asil kural. Dusuk siddetli (<=2) ve
   +/-30 dk icinde ayni sunucuda baska hicbir alarmi olmayan kayit. Bu veri
   setinde nadiren tetiklenir (her sunucu surekli alarm uretiyor) ama
   dogrulugu acisindan korunur.

2. `chronic_maintenance` — Tipi kronik bakim kumesinde (`cert_expiry`,
   `backup_warn`, `ntp_drift`, `log_rotate`, `disk_warn`) ve alarm servisinin
   bir artis penceresine dusmuyor. Bu tipler veri setinde zamanda tam duzgun
   dagilmis durumda (std ~34 dk ~= duzgun dagilimin beklenen degeri), yani
   olaylarla iliskisiz surekli bakim gurultusu.

3. `background_baseline` — Servisi ne keskin (3 dk) ne genis (9 dk) artis
   penceresindeyken gelen, siddeti 3 ve altindaki kayit. Gece boyunca akan
   normal seviye ciriltisi. Iki dedektorun birlikte calismasi kritik: yavas
   gelisen olaylar keskin tepe yapmadigi icin yalnizca dar pencereye bakmak
   onlari gurultu sanirdi.

Siddet 4-5 alarmlar **hicbir kosulda** elenmez. Kumelenemezlerse "Diger"
kartina artik olarak duserler; kritik bir alarmi gurultu ilan etmek, onu
kartsiz birakmaktan daha buyuk hatadir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src import config
from src.baseline import BaselineModel
from src.models import Alarm, NoiseEntry


@dataclass(slots=True)
class NoiseResult:
    """Filtre ciktisi: gecerli alarmlar + gurultu defteri."""

    signal: list[Alarm] = field(default_factory=list)
    ledger: list[NoiseEntry] = field(default_factory=list)

    @property
    def noise_count(self) -> int:
        return len(self.ledger)

    @property
    def total(self) -> int:
        return len(self.signal) + len(self.ledger)

    def rule_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.ledger:
            counts[entry.rule] = counts.get(entry.rule, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


# --------------------------------------------------------------------------
# Kurallar
# --------------------------------------------------------------------------


def _rule_isolated_low_severity(
    alarm: Alarm, model: BaselineModel
) -> tuple[str, str] | None:
    if alarm.severity > config.NOISE_MAX_SEVERITY:
        return None
    window = config.NOISE_LONELINESS_WINDOW_MIN
    if model.host_neighbours(alarm, window) == 0:
        return (
            "isolated_low_severity",
            f"Siddet {alarm.severity} ({alarm.severity_label}) ve {alarm.host} "
            f"sunucusunda +/-{window} dk icinde baska alarm yok — tekil, "
            "aksiyon gerektirmeyen kayit.",
        )
    return None


def _rule_maintenance_chatter(
    alarm: Alarm, model: BaselineModel
) -> tuple[str, str] | None:
    if alarm.alarm_type not in config.MAINTENANCE_CHATTER_TYPES:
        return None
    return (
        "maintenance_chatter",
        f"'{alarm.alarm_type}' tipi 2 saatlik pencerede zamana duzgun dagilmis "
        "(std ~34 dk = duzgun dagilim beklentisi) — hicbir olayla iliskisi yok. "
        f"Mesaj da aksiyon gerektirmiyor: \"{alarm.message}\".",
    )


def _rule_background_baseline(
    alarm: Alarm, model: BaselineModel
) -> tuple[str, str] | None:
    if alarm.severity > config.BACKGROUND_MAX_SEVERITY:
        return None
    if model.in_spike(alarm):
        return None
    baseline = model.baseline_of(alarm.service)
    return (
        "background_baseline",
        f"{alarm.service} servisi bu anda ne keskin (3 dk) ne genis (9 dk) "
        f"artis penceresinde; taban orani olan {baseline:.1f} alarm/dk "
        f"seviyesinde akiyor. Siddet {alarm.severity} "
        f"({alarm.severity_label}) bu esigin altinda kaldigi icin arka plan "
        "kabul edildi.",
    )


RULES = (
    _rule_maintenance_chatter,
    _rule_isolated_low_severity,
    _rule_background_baseline,
)


# --------------------------------------------------------------------------


def filter_noise(alarms: list[Alarm], model: BaselineModel) -> NoiseResult:
    """Alarm listesini sinyal ve gurultu olarak ikiye ayirir."""
    result = NoiseResult()

    for alarm in alarms:
        verdict = None
        for rule in RULES:
            verdict = rule(alarm, model)
            if verdict is not None:
                break

        if verdict is None:
            alarm.is_noise = False
            alarm.noise_reason = ""
            result.signal.append(alarm)
            continue

        rule_name, reason = verdict
        alarm.is_noise = True
        alarm.noise_reason = reason
        result.ledger.append(NoiseEntry(alarm=alarm, rule=rule_name, reason=reason))

    return result


def _main() -> None:
    """`python -m src.noise_filter` — filtre ciktisinin ozeti."""
    from src.data_loader import load_all

    data = load_all()
    model = BaselineModel(data.alarms)
    result = filter_noise(data.alarms, model)

    print()
    print("Faz 2.1 - Gurultu filtresi")
    print("-" * 64)
    print(f"  toplam alarm   : {result.total}")
    print(
        f"  sinyal         : {len(result.signal)} "
        f"({len(result.signal) / result.total:.1%})"
    )
    print(
        f"  gurultu        : {result.noise_count} "
        f"({result.noise_count / result.total:.1%})"
    )
    print()
    print("  Kural dagilimi:")
    for rule, count in result.rule_counts().items():
        print(f"    {count:>5}  {rule}")

    print()
    print("  Sinyalde kalan siddet dagilimi:")
    dist: dict[int, int] = {}
    for alarm in result.signal:
        dist[alarm.severity] = dist.get(alarm.severity, 0) + 1
    for sev in sorted(dist):
        print(f"    severity {sev}: {dist[sev]}")
    print()


if __name__ == "__main__":
    _main()
