"""Uctan uca calistirici — Faz 1'den Faz 4'e tum boru hatti.

    python -m src.pipeline

Ciktilar:
    output/incidents.json     <= 15 olay karti + ozet
    output/noise_ledger.json  Elenen her alarm, gerekcesiyle
    output/topology.json      Bagimlilik grafigi ve merkezilik degerleri

Calistirmanin sonunda **veri butunlugu** acikca dogrulanir: kartlardaki alarm
sayisi + gurultu defteri = 3.000. Bu esitlik tutmazsa cikis kodu 1 olur.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from src import config
from src.baseline import BaselineModel
from src.clustering import build_clusters
from src.correlation import merge_clusters
from src.data_loader import load_all
from src.incident_cards import build_cards
from src.llm import enrich_explanations
from src.noise_filter import filter_noise
from src.root_cause import analyse_all, evidence_for


def _build_timeline(alarms, cards, noise) -> list[dict]:
    """Dakika bazli yigilmis zaman serisi — panodaki ana grafigin kaynagi.

    Her dakika icin: arka plan gurultusu + her olay kartinin o dakikadaki
    alarm sayisi. Bu sayede nobetci muhendis, alarm selinin hangi bolumunun
    hangi olaya ait oldugunu tek bakista gorur.
    """
    owner: dict[str, str] = {}
    for card in cards:
        for alarm_id in card["alarm_ids"]:
            owner[alarm_id] = card["incident_id"]
    for entry in noise.ledger:
        owner[entry.alarm.alarm_id] = "NOISE"

    buckets: dict[str, dict[str, int]] = {}
    for alarm in alarms:
        minute = alarm.timestamp.replace(second=0, microsecond=0).isoformat()
        key = owner.get(alarm.alarm_id, "NOISE")
        row = buckets.setdefault(minute, {})
        row[key] = row.get(key, 0) + 1

    return [
        {"minute": minute, "counts": buckets[minute]} for minute in sorted(buckets)
    ]


def run(verbose: bool = True) -> dict:
    """Tum boru hattini calistirir ve sonucu sozluk olarak dondurur."""
    started = datetime.now()

    def say(message: str = "") -> None:
        if verbose:
            print(message)

    # --- Faz 1: veri katmani -------------------------------------------
    data = load_all()
    say()
    say("OnyxOps korelasyon motoru")
    say("=" * 72)
    say(
        f"Faz 1  veri      : {len(data.alarms)} alarm, {len(data.hosts)} host, "
        f"{len(data.graph)} servis, {data.graph.edge_count} bagimlilik"
    )
    for warning in data.warnings:
        say(f"       [uyari] {warning}")

    # --- Faz 2.1: gurultu filtresi --------------------------------------
    model = BaselineModel(data.alarms)
    noise = filter_noise(data.alarms, model)
    rules = ", ".join(f"{k}={v}" for k, v in noise.rule_counts().items())
    say(
        f"Faz 2a gurultu   : {noise.noise_count} elendi "
        f"({noise.noise_count / len(data.alarms):.1%}), "
        f"{len(noise.signal)} sinyal kaldi  [{rules}]"
    )

    # --- Faz 2.2: cift pencereli kumeleme -------------------------------
    clustering, signal_model = build_clusters(noise.signal)
    say(
        f"Faz 2b kumeleme  : {len(clustering.clusters)} kume "
        f"{clustering.kind_counts()}, {clustering.clustered_count} alarm "
        f"kumelendi, {len(clustering.residual)} artik"
    )

    # --- Faz 3: topolojik birlestirme + kok neden ------------------------
    incidents = merge_clusters(clustering.clusters, data.graph)
    incidents = analyse_all(incidents, data.graph)
    say(
        f"Faz 3  olay      : {len(clustering.clusters)} kume -> "
        f"{len(incidents)} olay (topolojik/mekansal birlestirme)"
    )

    evidence_map = {
        inc.incident_id: evidence_for(inc, data.graph) for inc in incidents
    }
    llm_status = enrich_explanations(incidents, evidence_map)
    say(f"       aciklama  : {llm_status.reason}")

    # --- Faz 4: kartlar + 15 siniri --------------------------------------
    generated_at = datetime.now()
    run_id = generated_at.isoformat(timespec="seconds")
    cards, stats = build_cards(
        incidents, clustering.residual, data.graph, generated_at, run_id=run_id
    )
    say(
        f"Faz 4  kart      : {stats['total_cards']} kart "
        f"(sinir {stats['cap']}), {stats['incidents_rolled_up']} olay + "
        f"{stats['residual_alarms']} artik alarm toplayici karta alindi"
    )
    matched = sum(
        len((c.get("similar_patterns") or {}).get("similar_incidents", []))
        for c in cards
    )
    say(
        f"       oruntu    : {stats['pattern_matches']} kart bilinen ariza "
        f"oruntusuyle eslesti, {matched} benzer olay baglantisi kuruldu"
    )

    # --- Butunluk dogrulamasi --------------------------------------------
    card_alarms = sum(card["alarm_count"] for card in cards)
    total_accounted = card_alarms + noise.noise_count
    integrity_ok = total_accounted == len(data.alarms)

    all_ids: set[str] = set()
    for card in cards:
        all_ids.update(card["alarm_ids"])
    all_ids.update(entry.alarm.alarm_id for entry in noise.ledger)
    unique_ok = len(all_ids) == len(data.alarms)

    summary = {
        "generated_at": generated_at.isoformat(),
        "runtime_seconds": round((datetime.now() - started).total_seconds(), 2),
        "total_alarms": len(data.alarms),
        "noise_alarms": noise.noise_count,
        "signal_alarms": len(noise.signal),
        "noise_rules": noise.rule_counts(),
        "clusters": len(clustering.clusters),
        "cluster_kinds": clustering.kind_counts(),
        "incidents_detected": stats["incidents_detected"],
        "incident_cards": stats["total_cards"],
        "cards_with_own_slot": stats["cards_with_own_slot"],
        "incidents_rolled_up": stats["incidents_rolled_up"],
        "residual_alarms": stats["residual_alarms"],
        "reduction_ratio": f"{len(data.alarms)} -> {stats['total_cards']}",
        "reduction_factor": round(len(data.alarms) / max(1, stats["total_cards"]), 1),
        "cap": config.MAX_INCIDENT_CARDS,
        "explanation_engine": llm_status.to_dict(),
        "integrity": {
            "alarms_in_cards": card_alarms,
            "alarms_in_noise_ledger": noise.noise_count,
            "accounted_total": total_accounted,
            "expected_total": len(data.alarms),
            "no_data_loss": integrity_ok,
            "all_alarm_ids_unique": unique_ok,
        },
    }

    payload = {
        "summary": summary,
        "timeline": _build_timeline(data.alarms, cards, noise),
        "incidents": cards,
    }

    ledger_payload = {
        "generated_at": generated_at.isoformat(),
        "total_noise": noise.noise_count,
        "rule_counts": noise.rule_counts(),
        "entries": [entry.to_dict() for entry in noise.ledger],
    }

    # --- Yazma -----------------------------------------------------------
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.INCIDENTS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    config.NOISE_LEDGER_JSON.write_text(
        json.dumps(ledger_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (config.OUTPUT_DIR / "topology.json").write_text(
        json.dumps(data.graph.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    say()
    say("-" * 72)
    say(
        f"INDIRGEME : {len(data.alarms)} alarm -> {stats['total_cards']} kart "
        f"({summary['reduction_factor']}x)"
    )
    say(
        f"BUTUNLUK  : {card_alarms} (kart) + {noise.noise_count} (gurultu) = "
        f"{total_accounted} / {len(data.alarms)}  "
        f"{'OK' if integrity_ok and unique_ok else 'HATA'}"
    )
    say(f"CIKTI     : {config.INCIDENTS_JSON.relative_to(config.ROOT)}")
    say(f"            {config.NOISE_LEDGER_JSON.relative_to(config.ROOT)}")
    say()

    if verbose:
        say(f"  {'kart':<17}{'oncelik':>8}{'alarm':>7}{'svc':>5}  kok neden")
        for card in cards:
            root = card.get("root_cause_hypothesis") or {}
            label = (
                f"{root.get('service')}/{root.get('alarm_type')}"
                if root.get("alarm_id")
                else "-"
            )
            say(
                f"  {card['incident_id']:<17}{card['priority_score']:>8.3f}"
                f"{card['alarm_count']:>7}{len(card['affected_services']):>5}  "
                f"{label}"
            )
        say()

    payload["_ok"] = integrity_ok and unique_ok
    return payload


def main() -> int:
    payload = run(verbose=True)
    return 0 if payload.get("_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
