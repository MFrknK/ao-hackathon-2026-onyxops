"""Faz 5 — OnyxOps operator panosu (Streamlit).

    streamlit run src/app.py

Sekmeler:
  1. Olay Panosu     — <= 15 olay karti, kok neden, kanit, karsi hipotez
  2. Aksiyon Takibi  — durum gecisleri (Acik -> Calisiliyor -> Cozuldu)
  3. Gurultu Denetimi— elenen her alarm, eleme gerekcesiyle (X-Factor)
  4. Topoloji        — bagimlilik grafigi ve merkezilik degerleri
  5. Boru Hatti      — indirgeme zinciri ve veri butunlugu kaniti
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

if __package__ in (None, ""):  # `streamlit run src/app.py` ile calistirilirsa
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.action_store import STATUS_ICONS, STATUS_LABELS, STATUSES, ActionStore

st.set_page_config(
    page_title="OnyxOps — Alarm Firtinasi",
    page_icon="🛰",
    layout="wide",
)

SEVERITY_COLOR = {5: "#b3261e", 4: "#e8710a", 3: "#f2b705", 2: "#4a90d9", 1: "#8a8f98"}
STATUS_COLOR = {"open": "#b3261e", "in_progress": "#e8710a", "resolved": "#1e8e3e"}


# --------------------------------------------------------------------------
# Veri yukleme
# --------------------------------------------------------------------------


def _run_pipeline() -> None:
    from src.pipeline import run

    run(verbose=False)


@st.cache_data(show_spinner=False)
def load_payload(_stamp: float) -> tuple[dict, dict]:
    incidents = json.loads(config.INCIDENTS_JSON.read_text(encoding="utf-8"))
    ledger = json.loads(config.NOISE_LEDGER_JSON.read_text(encoding="utf-8"))
    return incidents, ledger


def ensure_outputs() -> tuple[dict, dict]:
    if not config.INCIDENTS_JSON.is_file() or not config.NOISE_LEDGER_JSON.is_file():
        with st.spinner("Korelasyon motoru ilk kez calistiriliyor (3.000 alarm)..."):
            _run_pipeline()
    stamp = config.INCIDENTS_JSON.stat().st_mtime
    return load_payload(stamp)


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return iso or "-"


def severity_chip(severity: int, label: str) -> str:
    color = SEVERITY_COLOR.get(severity, "#8a8f98")
    return (
        f"<span style='background:{color};color:#fff;padding:2px 9px;"
        f"border-radius:10px;font-size:0.78rem;font-weight:600'>"
        f"sev {severity} · {label}</span>"
    )


def status_chip(status: str) -> str:
    color = STATUS_COLOR.get(status, "#8a8f98")
    return (
        f"<span style='background:{color};color:#fff;padding:2px 9px;"
        f"border-radius:10px;font-size:0.78rem;font-weight:600'>"
        f"{STATUS_LABELS.get(status, status)}</span>"
    )


# --------------------------------------------------------------------------

payload, ledger = ensure_outputs()
summary = payload["summary"]
cards = payload["incidents"]

store = ActionStore()
store.sync_with_cards(cards)

# --------------------------------------------------------------------------
# Kenar cubugu
# --------------------------------------------------------------------------

with st.sidebar:
    st.title("🛰 OnyxOps")
    st.caption("S-A1 Alarm Firtinasi · AO Hackathon 2026")

    st.metric(
        "Indirgeme",
        f"{summary['total_alarms']} → {summary['incident_cards']}",
        f"{summary['reduction_factor']}x",
    )
    st.metric("Gurultu elendi", f"{summary['noise_alarms']}")
    st.metric("Tespit edilen olay", f"{summary['incidents_detected']}")

    integrity = summary["integrity"]
    if integrity["no_data_loss"] and integrity["all_alarm_ids_unique"]:
        st.success(
            f"Veri butunlugu OK\n\n"
            f"{integrity['alarms_in_cards']} kart + "
            f"{integrity['alarms_in_noise_ledger']} gurultu = "
            f"{integrity['accounted_total']}"
        )
    else:
        st.error("Veri butunlugu dogrulanamadi!")

    counts = store.counts()
    st.markdown("**Aksiyon durumu**")
    cols = st.columns(3)
    for col, status in zip(cols, STATUSES, strict=False):
        col.metric(STATUS_LABELS[status], counts.get(status, 0))

    st.divider()
    if st.button("Motoru yeniden calistir", width="stretch"):
        with st.spinner("Calisiyor..."):
            _run_pipeline()
        st.cache_data.clear()
        st.rerun()

    engine = summary["explanation_engine"]
    st.caption(
        ("LLM aciklamasi acik" if engine["enabled"] else "Sablon aciklama motoru")
        + f" — {engine['reason']}"
    )

# --------------------------------------------------------------------------

tab_board, tab_actions, tab_noise, tab_topology, tab_pipeline = st.tabs(
    [
        f"Olay Panosu ({len(cards)})",
        "Aksiyon Takibi",
        f"Gurultu Denetimi ({ledger['total_noise']})",
        "Topoloji",
        "Boru Hatti",
    ]
)


# ==========================================================================
# 1) OLAY PANOSU
# ==========================================================================

with tab_board:
    st.subheader("Olay Panosu")
    st.caption(
        f"{summary['total_alarms']} alarm, {summary['clusters']} zamansal kume ve "
        f"{summary['incidents_detected']} olay uzerinden "
        f"{summary['incident_cards']} karta indirgendi "
        f"(ust sinir {summary['cap']})."
    )

    filter_cols = st.columns([2, 2, 3])
    status_filter = filter_cols[0].multiselect(
        "Durum", STATUSES, default=list(STATUSES),
        format_func=lambda s: STATUS_LABELS[s],
    )
    severity_filter = filter_cols[1].slider("En dusuk siddet", 1, 5, 1)
    service_options = sorted({s for c in cards for s in c["affected_services"]})
    service_filter = filter_cols[2].multiselect("Servis", service_options)

    shown = 0
    for card in cards:
        status = store.status_of(card["incident_id"])
        if status not in status_filter:
            continue
        if card["max_severity"] < severity_filter:
            continue
        if service_filter and not set(service_filter) & set(card["affected_services"]):
            continue
        shown += 1

        root = card.get("root_cause_hypothesis") or {}
        tr = card["time_range"]

        header = (
            f"{STATUS_ICONS.get(status, '')}  {card['incident_id']} — "
            f"{card['title']}   ·   {card['alarm_count']} alarm · "
            f"{fmt_time(tr['start'])}-{fmt_time(tr['end'])}"
        )

        with st.expander(header, expanded=(shown <= 2)):
            top = st.columns([3, 1, 1, 1])
            top[0].markdown(
                severity_chip(card["max_severity"], card["severity_label"])
                + "  "
                + status_chip(status),
                unsafe_allow_html=True,
            )
            top[1].metric("Alarm", card["alarm_count"])
            top[2].metric("Servis", len(card["affected_services"]))
            top[3].metric("Sure", f"{tr['duration_minutes']:.0f} dk")

            # ---- Kok neden ----
            if root.get("alarm_id"):
                st.markdown("#### Kok neden hipotezi")
                rc = st.columns([3, 1])
                rc[0].markdown(
                    f"**{root['alarm_id']}** · `{root['alarm_type']}` · "
                    f"{root['service']} / {root['host']} · "
                    f"{fmt_time(root['timestamp'])} · {root['location']}\n\n"
                    f"> {root['message']}"
                )
                rc[1].metric("Guven", f"{root['confidence']:.0%}")

                st.info(root["explanation"])

                breakdown = root.get("score_breakdown") or {}
                if breakdown:
                    parts = {k: v for k, v in breakdown.items() if k != "total"}
                    st.markdown("**Puan kirilimi** (toplam %.1f/100)" % breakdown.get("total", 0))
                    st.bar_chart(
                        pd.DataFrame(
                            {"puan": parts.values()}, index=list(parts.keys())
                        ),
                        height=170,
                    )
            else:
                st.markdown("#### Kok neden hipotezi")
                st.warning(root.get("explanation", "-"))

            # ---- Kanit ----
            if card.get("evidence"):
                st.markdown("#### Kanitlar")
                for item in card["evidence"]:
                    st.markdown(f"- {item}")

            # ---- Karsi hipotez ----
            counter = card.get("counter_hypothesis")
            if counter:
                st.markdown("#### Karsi hipotez")
                st.warning(
                    f"**{counter['alarm_id']}** · `{counter['alarm_type']}` · "
                    f"{counter['service']} / {counter['host']} "
                    f"(puan {counter['score']:.1f})\n\n{counter['reason']}"
                )

            # ---- Korelasyon gerekceleri ----
            if card.get("correlation_reasons"):
                with st.popover("Bu kumeler neden tek olay sayildi?"):
                    for reason in card["correlation_reasons"][:12]:
                        st.markdown(f"- {reason}")

            # ---- Kapsam ----
            sc = st.columns(2)
            sc[0].markdown(
                "**Etkilenen servisler**\n\n"
                + ", ".join(f"`{s}`" for s in card["affected_services"])
            )
            sc[1].markdown(
                "**Alarm tipi dagilimi**\n\n"
                + ", ".join(
                    f"`{t}` ×{n}" for t, n in card["alarm_type_histogram"].items()
                )
            )

            if card.get("rolled_up_incidents"):
                st.markdown("**Bu karta toplanan olaylar**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "olay": r["incident_id"],
                                "alarm": r["alarm_count"],
                                "servisler": ", ".join(r["services"]),
                                "baslangic": fmt_time(r["time_range"]["start"]),
                                "bitis": fmt_time(r["time_range"]["end"]),
                                "oncelik": r["priority_score"],
                            }
                            for r in card["rolled_up_incidents"]
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )

            # ---- Aksiyon ----
            st.markdown("#### Onerilen aksiyon")
            record = store.get(card["incident_id"])
            action = card.get("recommended_action") or {}
            st.markdown(f"> {record.action if record else action.get('action', '-')}")

            ac = st.columns([2, 2, 3, 2])
            ac[0].markdown(
                f"**Sahip**\n\n`{record.owner if record else action.get('owner','-')}`"
            )
            ac[1].markdown(
                "**Durum**\n\n" + status_chip(status), unsafe_allow_html=True
            )
            new_status = ac[2].selectbox(
                "Durumu degistir",
                STATUSES,
                index=STATUSES.index(status),
                format_func=lambda s: STATUS_LABELS[s],
                key=f"status-{card['incident_id']}",
            )
            ac[3].markdown("&nbsp;", unsafe_allow_html=True)
            if ac[3].button(
                "Kaydet",
                key=f"save-{card['incident_id']}",
                disabled=(new_status == status),
                width="stretch",
            ):
                store.set_status(card["incident_id"], new_status)
                st.rerun()

            if record and record.history:
                with st.popover(f"Aksiyon gecmisi ({len(record.history)})"):
                    for entry in reversed(record.history):
                        st.markdown(
                            f"- `{entry['at']}` — **{STATUS_LABELS.get(entry['status'], entry['status'])}**"
                            f" · {entry.get('owner','')} · {entry.get('note','')}"
                        )

    if shown == 0:
        st.info("Secilen filtrelere uyan kart yok.")


# ==========================================================================
# 2) AKSIYON TAKIBI
# ==========================================================================

with tab_actions:
    st.subheader("Aksiyon Takibi")
    st.caption(
        "Her kartin onerilen aksiyonu sahip ve durum bilgisiyle kayit altinda. "
        "Durum degisiklikleri zaman damgasiyla `output/action_log.json` "
        "dosyasina yazilir; sayfa yenilense de korunur."
    )

    counts = store.counts()
    mc = st.columns(4)
    mc[0].metric("Toplam aksiyon", len(store.records))
    for col, status in zip(mc[1:], STATUSES, strict=False):
        col.metric(STATUS_LABELS[status], counts.get(status, 0))

    rows = []
    for card in cards:
        record = store.get(card["incident_id"])
        if record is None:
            continue
        rows.append(
            {
                "olay": record.incident_id,
                "baslik": card["title"],
                "durum": STATUS_LABELS.get(record.status, record.status),
                "sahip": record.owner,
                "alarm": card["alarm_count"],
                "siddet": card["max_severity"],
                "acildi": record.created_at,
                "guncellendi": record.updated_at,
                "gecis": len(record.history),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.markdown("### Toplu durum degisikligi")
    bulk = st.columns([3, 2, 2, 3])
    target = bulk[0].selectbox(
        "Olay", [c["incident_id"] for c in cards], key="bulk-incident"
    )
    target_status = bulk[1].selectbox(
        "Yeni durum", STATUSES, format_func=lambda s: STATUS_LABELS[s],
        key="bulk-status",
    )
    owner = bulk[2].text_input(
        "Sahip", value=store.status_of(target) and (store.get(target).owner or ""),
        key="bulk-owner",
    )
    note = bulk[3].text_input("Not", key="bulk-note", placeholder="opsiyonel")
    if st.button("Uygula", type="primary"):
        store.set_status(target, target_status, owner=owner or None, note=note)
        st.success(
            f"{target} -> {STATUS_LABELS[target_status]} "
            f"({datetime.now():%H:%M:%S})"
        )
        st.rerun()

    st.markdown("### Durum gecis gunlugu")
    timeline = store.timeline()
    if timeline:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "zaman": row.get("at", ""),
                        "olay": row["incident_id"],
                        "durum": STATUS_LABELS.get(
                            row.get("status", ""), row.get("status", "")
                        ),
                        "onceki": STATUS_LABELS.get(
                            row.get("previous_status", ""), "-"
                        ),
                        "sahip": row.get("owner", ""),
                        "not": row.get("note", ""),
                    }
                    for row in timeline
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Henuz durum gecisi yok.")


# ==========================================================================
# 3) GURULTU DENETIMI  (X-Factor)
# ==========================================================================

with tab_noise:
    st.subheader("Gurultu Denetimi")
    st.caption(
        "Elenen hicbir alarm silinmez. Her kayit, hangi kuralla ve neden "
        "elendigi yazili olarak burada denetlenebilir."
    )

    noise_df = pd.DataFrame(ledger["entries"])
    mc = st.columns(3)
    mc[0].metric("Elenen alarm", ledger["total_noise"])
    mc[1].metric(
        "Toplam icindeki payi",
        f"{ledger['total_noise'] / summary['total_alarms']:.1%}",
    )
    mc[2].metric("Kural sayisi", len(ledger["rule_counts"]))

    st.markdown("**Kural dagilimi**")
    rule_df = pd.DataFrame(
        {"kural": list(ledger["rule_counts"]), "adet": list(ledger["rule_counts"].values())}
    )
    st.bar_chart(rule_df.set_index("kural"), height=200)

    with st.expander("Kurallarin tanimi"):
        st.markdown(
            "- **maintenance_chatter** — `cert_expiry`, `backup_warn`, "
            "`ntp_drift`, `log_rotate`, `disk_warn`. Bu bes tipin zaman "
            "eksenindeki standart sapmasi 33-36 dk; 121 dakikalik pencerede "
            "tam duzgun dagilimin beklenen degeri 34.9. Yani istatistiksel "
            "olarak olaylardan bagimsizlar.\n"
            "- **isolated_low_severity** — Siddet <= 2 ve ayni sunucuda "
            "+/-30 dk icinde baska alarm yok.\n"
            "- **background_baseline** — Servis ne keskin (3 dk) ne genis "
            "(9 dk) artis penceresinde; siddet <= 3."
        )

    fc = st.columns([2, 2, 2, 3])
    rule_sel = fc[0].multiselect(
        "Kural", sorted(noise_df["noise_rule"].unique()) if not noise_df.empty else []
    )
    sev_sel = fc[1].multiselect(
        "Siddet", sorted(noise_df["severity"].unique()) if not noise_df.empty else []
    )
    svc_sel = fc[2].multiselect(
        "Servis", sorted(noise_df["service"].unique()) if not noise_df.empty else []
    )
    query = fc[3].text_input("Metin ara", placeholder="alarm_id, mesaj, tip...")

    view = noise_df.copy()
    if rule_sel:
        view = view[view["noise_rule"].isin(rule_sel)]
    if sev_sel:
        view = view[view["severity"].isin(sev_sel)]
    if svc_sel:
        view = view[view["service"].isin(svc_sel)]
    if query:
        mask = (
            view["alarm_id"].str.contains(query, case=False, na=False)
            | view["message"].str.contains(query, case=False, na=False)
            | view["alarm_type"].str.contains(query, case=False, na=False)
        )
        view = view[mask]

    st.caption(f"{len(view)} / {len(noise_df)} kayit gosteriliyor")
    st.dataframe(
        view[
            [
                "alarm_id",
                "timestamp",
                "service",
                "host",
                "severity",
                "alarm_type",
                "message",
                "noise_rule",
                "noise_reason",
            ]
        ],
        hide_index=True,
        width="stretch",
        height=460,
    )


# ==========================================================================
# 4) TOPOLOJI
# ==========================================================================

with tab_topology:
    st.subheader("Servis Bagimlilik Topolojisi")
    st.caption(
        "Okuma yonu: kaynak servis, hedef servise bagimlidir. Hedef bozulursa "
        "kaynak etkilenir. Merkezilik, bir servisin altinda kac servisin "
        "yattigini olcer ve kok neden puanina girer."
    )

    topo_path = config.OUTPUT_DIR / "topology.json"
    if topo_path.is_file():
        topo = json.loads(topo_path.read_text(encoding="utf-8"))
        tc = st.columns(3)
        tc[0].metric("Servis", len(topo["services"]))
        tc[1].metric("Bagimlilik", len(topo["edges"]))
        tc[2].metric(
            "En merkezi",
            max(topo["centrality"], key=lambda k: topo["centrality"][k]),
        )

        st.markdown("**Merkezilik siralamasi**")
        cen = pd.DataFrame(
            {
                "servis": list(topo["centrality"]),
                "merkezilik": list(topo["centrality"].values()),
            }
        ).sort_values("merkezilik", ascending=False)
        st.bar_chart(cen.set_index("servis").head(15), height=280)

        st.markdown("**Bagimlilik kenarlari**")
        st.dataframe(
            pd.DataFrame(topo["edges"]), hide_index=True, width="stretch"
        )
    else:
        st.info("Topoloji ciktisi bulunamadi; motoru yeniden calistirin.")


# ==========================================================================
# 5) BORU HATTI
# ==========================================================================

with tab_pipeline:
    st.subheader("Indirgeme Zinciri")

    steps = [
        ("Ham alarm", summary["total_alarms"]),
        ("Gurultu filtresinden gecen sinyal", summary["signal_alarms"]),
        ("Zamansal kumeye giren alarm", summary["total_alarms"]
            - summary["noise_alarms"] - summary["residual_alarms"]),
        ("Topolojik olay", summary["incidents_detected"]),
        ("Olay karti", summary["incident_cards"]),
    ]
    cols = st.columns(len(steps))
    for col, (label, value) in zip(cols, steps, strict=False):
        col.metric(label, value)

    st.markdown("### Veri butunlugu")
    integrity = summary["integrity"]
    st.dataframe(
        pd.DataFrame(
            [
                {"olcut": "Kartlardaki alarm", "deger": integrity["alarms_in_cards"]},
                {
                    "olcut": "Gurultu defterindeki alarm",
                    "deger": integrity["alarms_in_noise_ledger"],
                },
                {"olcut": "Toplam", "deger": integrity["accounted_total"]},
                {"olcut": "Beklenen", "deger": integrity["expected_total"]},
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if integrity["no_data_loss"] and integrity["all_alarm_ids_unique"]:
        st.success(
            "Veri kaybi yok: 3.000 alarmin tamami ya bir kartta ya da gurultu "
            "defterinde; hicbir kimlik tekrarlanmiyor."
        )
    else:
        st.error("Butunluk dogrulamasi basarisiz.")

    st.markdown("### Kume tipleri")
    st.json(summary["cluster_kinds"])

    st.markdown("### Gurultu kurallari")
    st.json(summary["noise_rules"])

    st.markdown("### Calistirma ozeti")
    st.json(
        {
            k: v
            for k, v in summary.items()
            if k not in {"integrity", "noise_rules", "cluster_kinds"}
        }
    )
