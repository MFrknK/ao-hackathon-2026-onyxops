"""Faz 1 — Veri katmani.

Gorev 1.1  host_inventory.csv -> host haritasi
Gorev 1.2  service_dependencies.csv -> yonlu bagimlilik grafigi
Gorev 1.3  alarms.csv -> zaman damgasi cozulmus, envanterle zenginlestirilmis
           3.000 Alarm nesnesi

Kural: veri setinin tamami okunur, ornekleme yapilmaz.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src import config
from src.models import Alarm, Dependency, HostInfo
from src.topology import DependencyGraph


@dataclass(slots=True)
class LoadedData:
    """Faz 1 ciktisinin tamami."""

    alarms: list[Alarm]
    hosts: dict[str, HostInfo]
    graph: DependencyGraph
    warnings: list[str]

    @property
    def services(self) -> set[str]:
        return set(self.graph.services)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# Gorev 1.1 — Host envanteri
# --------------------------------------------------------------------------


def load_hosts(path: Path | None = None) -> dict[str, HostInfo]:
    """host -> {servis, veri_merkezi, kabin, ortam, is_kritikligi} haritasi."""
    rows = _read_csv(path or config.HOSTS_CSV)
    hosts: dict[str, HostInfo] = {}
    for row in rows:
        info = HostInfo(
            host=row["host"].strip(),
            service=row["servis"].strip(),
            datacenter=row["veri_merkezi"].strip(),
            rack=row["kabin"].strip(),
            environment=row["ortam"].strip(),
            criticality=row["is_kritikligi"].strip(),
        )
        hosts[info.host] = info
    return hosts


# --------------------------------------------------------------------------
# Gorev 1.2 — Bagimlilik grafigi
# --------------------------------------------------------------------------


def load_dependencies(path: Path | None = None) -> list[Dependency]:
    rows = _read_csv(path or config.DEPENDENCIES_CSV)
    return [
        Dependency(
            source=row["kaynak_servis"].strip(),
            target=row["hedef_servis"].strip(),
            kind=row["bagimlilik_tipi"].strip(),
            criticality=row["kritiklik"].strip(),
        )
        for row in rows
    ]


def build_graph(
    dependencies: list[Dependency], hosts: dict[str, HostInfo]
) -> DependencyGraph:
    """Yonlu grafigi kurar; envanterdeki yalniz servisler de dugum olur.

    Bagimlilik tablosunda gecmeyen ama uzerinde sunucu kosan servisler
    (izole servisler) grafikten dusmesin diye ayrica eklenir.
    """
    inventory_services = {h.service for h in hosts.values()}
    return DependencyGraph(dependencies, services=inventory_services)


# --------------------------------------------------------------------------
# Gorev 1.3 — Alarmlar + zenginlestirme
# --------------------------------------------------------------------------


def load_alarms(
    hosts: dict[str, HostInfo], path: Path | None = None
) -> tuple[list[Alarm], list[str]]:
    """Tum alarmlari okur, `timestamp`'i datetime'a cevirir ve zenginlestirir.

    Zenginlestirme kaynagi host envanteridir. alarms.csv zaten
    `veri_merkezi`/`kabin`/`ortam` tasiyor; envanterle celisirse envanter
    dogru kabul edilir ve durum `warnings` listesine yazilir.
    """
    rows = _read_csv(path or config.ALARMS_CSV)
    alarms: list[Alarm] = []
    warnings: list[str] = []

    unknown_hosts: set[str] = set()
    tag_conflicts = 0
    service_conflicts: set[str] = set()

    for row in rows:
        host = row["host"].strip()
        info = hosts.get(host)

        alarm = Alarm(
            alarm_id=row["alarm_id"].strip(),
            timestamp=datetime.fromisoformat(row["timestamp"].strip()),
            source_system=row["source_system"].strip(),
            host=host,
            service=row["service"].strip(),
            severity=int(row["severity"]),
            alarm_type=row["alarm_type"].strip(),
            message=row["message"].strip(),
        )

        if info is None:
            unknown_hosts.add(host)
            # Envanterde yoksa alarmin kendi etiketlerine duseriz — veri kaybi yok.
            alarm.datacenter = row.get("veri_merkezi", "").strip()
            alarm.rack = row.get("kabin", "").strip()
            alarm.environment = row.get("ortam", "").strip()
            alarm.criticality = "bilinmiyor"
            alarm.host_service = alarm.service
        else:
            alarm.datacenter = info.datacenter
            alarm.rack = info.rack
            alarm.environment = info.environment
            alarm.criticality = info.criticality
            alarm.host_service = info.service

            if (
                row.get("veri_merkezi", "").strip() != info.datacenter
                or row.get("kabin", "").strip() != info.rack
            ):
                tag_conflicts += 1
            if info.service != alarm.service:
                service_conflicts.add(f"{host}: {alarm.service} != {info.service}")

        alarms.append(alarm)

    # Kronolojik sira: tum asagi akis (kumeleme, puanlama) buna dayaniyor.
    alarms.sort(key=lambda a: (a.timestamp, a.alarm_id))

    if unknown_hosts:
        warnings.append(
            f"{len(unknown_hosts)} host envanterde bulunamadi: "
            f"{', '.join(sorted(unknown_hosts)[:5])}"
        )
    if tag_conflicts:
        warnings.append(
            f"{tag_conflicts} alarmin dc/rack etiketi envanterle celisti; "
            "envanter esas alindi"
        )
    if service_conflicts:
        warnings.append(
            f"{len(service_conflicts)} host icin alarm servisi envanter servisinden "
            f"farkli: {', '.join(sorted(service_conflicts)[:3])}"
        )

    return alarms, warnings


# --------------------------------------------------------------------------


def load_all() -> LoadedData:
    """Faz 1'in tamamini calistirir."""
    hosts = load_hosts()
    dependencies = load_dependencies()
    graph = build_graph(dependencies, hosts)
    alarms, warnings = load_alarms(hosts)
    return LoadedData(alarms=alarms, hosts=hosts, graph=graph, warnings=warnings)


def _main() -> None:
    """`python -m src.data_loader` — Faz 1 ciktisinin ozeti."""
    data = load_all()
    print()
    print("Faz 1 - Veri katmani")
    print("-" * 60)
    print(f"  alarm            : {len(data.alarms)}")
    print(f"  host             : {len(data.hosts)}")
    print(f"  servis (dugum)   : {len(data.graph)}")
    print(f"  bagimlilik (kenar): {data.graph.edge_count}")
    print(
        f"  zaman araligi    : {data.alarms[0].timestamp} .. "
        f"{data.alarms[-1].timestamp}"
    )
    for warning in data.warnings:
        print(f"  [uyari] {warning}")

    print()
    print("  En merkezi 8 servis (kok neden adayligi yuksek):")
    ranked = sorted(
        data.graph.services, key=lambda s: (-data.graph.centrality(s), s)
    )[:8]
    for svc in ranked:
        print(f"    {data.graph.centrality(svc):.3f}  {data.graph.describe(svc)}")

    print()
    sample = data.alarms[0]
    print("  Zenginlestirilmis ornek alarm:")
    for key, value in sample.to_dict().items():
        print(f"    {key:<16}{value}")
    print()


if __name__ == "__main__":
    _main()
