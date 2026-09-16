"""Faz 0 — Iskelet ve veri dogrulamasi.

Gorev 0.1: Yarisma teslim gereksinimlerine uygun klasor/dosya yapisini kontrol eder.
Gorev 0.2: Veri paketinin eksiksiz geldigini (3000 alarm / 27 servis / 56 sunucu /
           32 bagimlilik) dogrular.

Kullanim:  python -m src.verify_setup
Cikis kodu: tum kontroller gecerse 0, aksi halde 1.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):  # dogrudan `python src/verify_setup.py` calistirilirsa
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config

OK = "[ OK ]"
FAIL = "[FAIL]"


def _line(char: str = "-", width: int = 72) -> str:
    return char * width


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------
# Gorev 0.1 — Iskelet kontrolu
# --------------------------------------------------------------------------


def check_structure() -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    for rel in config.REQUIRED_DIRS:
        path = config.ROOT / rel
        results.append((path.is_dir(), f"klasor  {rel}/"))

    for rel in config.REQUIRED_FILES:
        path = config.ROOT / rel
        exists = path.is_file()
        if exists and path.stat().st_size == 0:
            results.append((False, f"dosya   {rel}  (mevcut ama BOS)"))
        else:
            results.append((exists, f"dosya   {rel}"))

    return results


# --------------------------------------------------------------------------
# Gorev 0.2 — Veri boyutu dogrulamasi
# --------------------------------------------------------------------------


def check_data() -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    for path in (config.ALARMS_CSV, config.DEPENDENCIES_CSV, config.HOSTS_CSV):
        if not path.is_file():
            results.append((False, f"veri dosyasi bulunamadi: {path.name}"))
            return results

    alarms = _read_csv(config.ALARMS_CSV)
    deps = _read_csv(config.DEPENDENCIES_CSV)
    hosts = _read_csv(config.HOSTS_CSV)

    def expect(actual: int, expected: int, label: str) -> None:
        results.append(
            (actual == expected, f"{label:<34} beklenen={expected:<5} bulunan={actual}")
        )

    expect(len(alarms), config.EXPECTED_ALARM_COUNT, "alarms.csv satir sayisi")
    expect(len(hosts), config.EXPECTED_HOST_COUNT, "host_inventory.csv satir sayisi")
    expect(
        len(deps), config.EXPECTED_DEPENDENCY_COUNT, "service_dependencies.csv satir"
    )

    # Servis sayisi: envanter + bagimlilik grafigi birligi 27 olmali.
    services = {row["servis"] for row in hosts}
    services |= {row["kaynak_servis"] for row in deps}
    services |= {row["hedef_servis"] for row in deps}
    expect(len(services), config.EXPECTED_SERVICE_COUNT, "benzersiz servis sayisi")

    # Benzersizlik ve butunluk kontrolleri
    alarm_ids = {row["alarm_id"] for row in alarms}
    results.append(
        (
            len(alarm_ids) == len(alarms),
            f"{'alarm_id benzersizligi':<34} benzersiz={len(alarm_ids)}",
        )
    )

    host_names = {row["host"] for row in hosts}
    orphan_hosts = {row["host"] for row in alarms} - host_names
    results.append(
        (
            not orphan_hosts,
            f"{'alarm host -> envanter eslesmesi':<34} eslesmeyen={len(orphan_hosts)}",
        )
    )

    alarm_services = {row["service"] for row in alarms}
    orphan_services = alarm_services - services
    results.append(
        (
            not orphan_services,
            f"{'alarm servis -> katalog eslesmesi':<34} eslesmeyen={len(orphan_services)}",
        )
    )

    severities = {int(row["severity"]) for row in alarms}
    results.append(
        (
            severities <= {1, 2, 3, 4, 5},
            f"{'severity araligi (1-5)':<34} gorulen={sorted(severities)}",
        )
    )

    timestamps = sorted(
        datetime.fromisoformat(row["timestamp"]) for row in alarms
    )
    grace = timedelta(minutes=config.OBSERVATION_WINDOW_TOLERANCE_MIN)
    window_start = datetime.fromisoformat(config.OBSERVATION_WINDOW[0]) - grace
    window_end = datetime.fromisoformat(config.OBSERVATION_WINDOW[1]) + grace
    window_ok = timestamps[0] >= window_start and timestamps[-1] <= window_end
    results.append(
        (
            window_ok,
            f"{'gozlem penceresi':<34} "
            f"{timestamps[0].isoformat()} .. {timestamps[-1].isoformat()}",
        )
    )

    # alarms.json ile alarms.csv ayni icerikte mi?
    if config.ALARMS_JSON.is_file():
        payload = json.loads(config.ALARMS_JSON.read_text(encoding="utf-8"))
        json_ids = {row["alarm_id"] for row in payload}
        results.append(
            (
                json_ids == alarm_ids,
                f"{'alarms.json <-> alarms.csv esitligi':<34} json={len(json_ids)}",
            )
        )

    return results


# --------------------------------------------------------------------------


def _report(title: str, results: list[tuple[bool, str]]) -> bool:
    print(_line("="))
    print(title)
    print(_line("="))
    for passed, label in results:
        print(f"  {OK if passed else FAIL}  {label}")
    failed = sum(1 for passed, _ in results if not passed)
    print(f"  -> {len(results) - failed}/{len(results)} kontrol gecti")
    print()
    return failed == 0


def main() -> int:
    print()
    print("OnyxOps - Faz 0 dogrulamasi")
    print(f"Proje koku: {config.ROOT}")
    print()

    structure_ok = _report("Gorev 0.1 - Repo iskeleti", check_structure())
    data_ok = _report("Gorev 0.2 - Veri paketi boyutlari", check_data())

    if structure_ok and data_ok:
        print(f"{OK}  Faz 0 tamam: iskelet ve veri paketi dogrulandi.")
        return 0

    print(f"{FAIL}  Faz 0 eksik: yukaridaki basarisiz kontrolleri giderin.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
