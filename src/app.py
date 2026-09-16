"""Faz 5 — OnyxOps operator panosu (Streamlit).

    streamlit run src/app.py

Ana giris sayfasi (NOC gorunumu):
  1. Ozet serit    — islenen alarm, filtrelenen gurultu, kok nedene baglanan
                     alarm, uretilen kart, gurultu orani, siniflandirilamayan
  2. Zaman serisi  — dakika bazli yigilmis grafik; her olay kendi renginde,
                     arka plan gurultusu gri. Alarm selinin hangi bolumunun
                     hangi olaya ait oldugu tek bakista gorulur.
  3. Sekmeler      — Olaylar & AI Hipotezleri · Denetim Gorunumu (Audit Log)
                     · Siniflandirilamayanlar · Topoloji · Boru Hatti
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

if __package__ in (None, ""):  # `streamlit run src/app.py` ile calistirilirsa
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.action_store import STATUS_LABELS, STATUSES, ActionStore

st.set_page_config(
    page_title="OnyxOps — Alarm Firtinasi",
    page_icon="🛰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Olay kartlarina sirayla atanan renk paleti (gurultu her zaman gri).
INCIDENT_COLORS = [
    "#ef4a5b",  # kirmizi
    "#f2b705",  # sari
    "#2ecc71",  # yesil
    "#a970ff",  # mor
    "#f7a35c",  # turuncu
    "#4aa3ef",  # mavi
    "#ff6fb5",  # pembe
    "#39d0c3",  # turkuaz
]
NOISE_COLOR = "#3a4a63"

PRIORITY_COLORS = {
    "P1": "#ef4a5b",
    "P2": "#f2b705",
    "P3": "#2ecc71",
    "P4": "#6b7a90",
}

STATUS_COLORS = {"open": "#ef4a5b", "in_progress": "#f2b705", "resolved": "#2ecc71"}


# --------------------------------------------------------------------------
# Stil
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 100%; }

      /* Ozet serit */
      .kpi-strip {
        display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
        gap: 0; background: #101a2b; border: 1px solid #1f2d45;
        border-radius: 10px; padding: 14px 6px; margin-bottom: 14px;
      }
      .kpi { text-align: center; padding: 2px 10px; border-right: 1px solid #1c2941; }
      .kpi:last-child { border-right: none; }
      .kpi .v { font-size: 1.95rem; font-weight: 700; color: #f2b705; line-height: 1.15; }
      .kpi .v.ok { color: #2ecc71; }
      .kpi .v.warn { color: #ef4a5b; }
      .kpi .l {
        font-size: 0.66rem; letter-spacing: .08em; text-transform: uppercase;
        color: #8ea0bb; margin-top: 4px;
      }

      /* Olay karti */
      .icard {
        background: #101a2b; border: 1px solid #1f2d45; border-radius: 10px;
        padding: 14px 15px; height: 100%;
      }
      .icard h4 {
        margin: 0 0 8px 0; font-size: 1.02rem; color: #e6ecf5; line-height: 1.3;
      }
      .icard h4 .cnt { color: #4aa3ef; font-weight: 600; font-size: .92rem; }
      .badge {
        float: right; font-size: .68rem; font-weight: 700; padding: 3px 9px;
        border-radius: 20px; color: #0b1220;
      }
      .pattern {
        display: inline-block; background: #17263d; border: 1px solid #273category;
        border: 1px solid #27384f; color: #9fd0ff; font-size: .68rem;
        padding: 3px 8px; border-radius: 5px; margin-bottom: 10px;
      }
      .meta { font-size: .8rem; color: #b9c7db; margin: 3px 0; }
      .meta b { color: #e6ecf5; }
      .svc { color: #f2b705; font-weight: 600; }

      .hypo {
        background: #131f33; border: 1px solid #263консольb;
        border: 1px solid #26374f; border-left: 3px solid #f2b705;
        border-radius: 6px; padding: 10px 11px; margin: 10px 0;
      }
      .hypo .t {
        color: #f2b705; font-weight: 700; font-size: .74rem; font-style: italic;
        margin-bottom: 5px;
      }
      .hypo .q { color: #dbe5f2; font-size: .79rem; line-height: 1.45; }
      .hypo .c {
        color: #8fa3bd; font-size: .73rem; font-style: italic; margin-top: 7px;
        line-height: 1.4;
      }
      .act {
        background: #131f33; border: 1px solid #26374f; border-left: 3px solid #2ecc71;
        border-radius: 6px; padding: 10px 11px; margin-top: 8px;
      }
      .act .t { color: #e6ecf5; font-weight: 700; font-size: .76rem; }
      .act .b { color: #c6d3e5; font-size: .79rem; line-height: 1.45; }
      .act .o { color: #9fb3cd; font-size: .74rem; margin-top: 5px; }
      .act .o b { color: #e6ecf5; }

      div[data-testid="stSelectbox"] label { font-size: .74rem; color: #8ea0bb; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Veri
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
    return load_payload(config.INCIDENTS_JSON.stat().st_mtime)


def fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except (TypeError, ValueError):
        return iso or "-"


payload, ledger = ensure_outputs()
summary = payload["summary"]
cards = payload["incidents"]
timeline = payload.get("timeline", [])

store = ActionStore()
store.sync_with_cards(cards)

event_cards = [c for c in cards if c["incident_id"] != "INC-UNCLUSTERED"]
bucket_card = next(
    (c for c in cards if c["incident_id"] == "INC-UNCLUSTERED"), None
)
color_of = {
    c["incident_id"]: INCIDENT_COLORS[i % len(INCIDENT_COLORS)]
    for i, c in enumerate(event_cards)
}


# ==========================================================================
# 1) OZET SERIT
# ==========================================================================

root_linked = sum(c["alarm_count"] for c in event_cards)
unclassified = bucket_card["alarm_count"] if bucket_card else 0
noise_ratio = summary["noise_alarms"] / max(1, summary["total_alarms"])
unclassified_ratio = unclassified / max(1, summary["total_alarms"])


def kpi(value: str, label: str, tone: str = "") -> str:
    return (
        f"<div class='kpi'><div class='v {tone}'>{value}</div>"
        f"<div class='l'>{label}</div></div>"
    )


st.markdown(
    "<div class='kpi-strip'>"
    + kpi(f"{summary['total_alarms']:,}".replace(",", "."), "Islenen toplam alarm")
    + kpi(f"{summary['noise_alarms']:,}".replace(",", "."), "Filtrelenen gurultu")
    + kpi(f"{root_linked:,}".replace(",", "."), "Kok nedene baglanan alarm")
    + kpi(str(len(event_cards)), "Uretilen olay karti")
    + kpi(f"%{noise_ratio * 100:.1f}", "Gurultu orani")
    + kpi(
        f"%{unclassified_ratio * 100:.1f}",
        "Siniflandirilamayan alarm",
        "ok" if unclassified_ratio == 0 else "warn",
    )
    + "</div>",
    unsafe_allow_html=True,
)


# ==========================================================================
# 2) ZAMAN SERISI
# ==========================================================================

if timeline:
    label_of = {c["incident_id"]: c["display_title"] for c in cards}
    label_of["NOISE"] = "Gurultu (Arka Plan)"

    rows = []
    for bucket in timeline:
        moment = datetime.fromisoformat(bucket["minute"])
        for key, count in bucket["counts"].items():
            rows.append(
                {
                    "Dakika": moment,
                    "Seri": label_of.get(key, key),
                    "key": key,
                    "Alarm": count,
                }
            )
    df = pd.DataFrame(rows)

    order = ["NOISE"] + [c["incident_id"] for c in event_cards]
    if bucket_card:
        order.append("INC-UNCLUSTERED")
    domain = [label_of.get(k, k) for k in order if label_of.get(k) in set(df["Seri"])]
    palette = {label_of["NOISE"]: NOISE_COLOR}
    for c in event_cards:
        palette[c["display_title"]] = color_of[c["incident_id"]]
    if bucket_card:
        palette[bucket_card["display_title"]] = "#5b6b84"
    colors = [palette.get(name, "#6b7a90") for name in domain]

    chart = (
        alt.Chart(df)
        .mark_bar(size=9)
        .encode(
            x=alt.X(
                "Dakika:T",
                title=None,
                axis=alt.Axis(format="%H:%M", tickCount=20, labelColor="#8ea0bb",
                              grid=False, domainColor="#26374f"),
            ),
            y=alt.Y(
                "Alarm:Q",
                title=None,
                axis=alt.Axis(labelColor="#8ea0bb", gridColor="#1b2740"),
            ),
            color=alt.Color(
                "Seri:N",
                scale=alt.Scale(domain=domain, range=colors),
                legend=alt.Legend(
                    orient="top", title=None, labelColor="#c6d3e5",
                    symbolType="square", columns=len(domain),
                ),
                sort=domain,
            ),
            order=alt.Order("Seri:N", sort="descending"),
            tooltip=["Dakika:T", "Seri:N", "Alarm:Q"],
        )
        .properties(height=300)
        .configure_view(strokeWidth=0)
        .configure(background="#101a2b")
    )
    st.altair_chart(chart, use_container_width=True)


# ==========================================================================
# SEKMELER
# ==========================================================================

tab_events, tab_audit, tab_unclassified, tab_topology, tab_pipeline = st.tabs(
    [
        "Olaylar & AI Hipotezleri",
        f"Denetim Gorunumu (Audit Log) · {ledger['total_noise']}",
        f"Siniflandirilamayanlar · {unclassified}",
        "Topoloji",
        "Boru Hatti",
    ]
)


# --------------------------------------------------------------------------
# Olay kartlari
# --------------------------------------------------------------------------


def render_card(card: dict, accent: str) -> None:
    incident_id = card["incident_id"]
    root = card.get("root_cause_hypothesis") or {}
    counter = card.get("counter_hypothesis") or {}
    action = card.get("recommended_action") or {}
    record = store.get(incident_id)
    status = store.status_of(incident_id)
    tr = card["time_range"]

    badge_color = PRIORITY_COLORS.get(card.get("priority", "P3"), "#6b7a90")

    patterns = (card.get("similar_patterns") or {}).get("known_patterns") or []
    pattern_chip = ""
    if patterns:
        top = patterns[0]
        pattern_chip = (
            f"<div class='pattern'>⚡ Gecmis Oruntu: {top['name']} "
            f"(%{top['confidence'] * 100:.0f} Benzerlik)</div>"
        )

    services = card["affected_services"]
    svc_text = ", ".join(services[:3]) + ("..." if len(services) > 3 else "")

    html = [
        f"<div class='icard' style='border-top:3px solid {accent}'>",
        f"<h4><span class='badge' style='background:{badge_color}'>"
        f"{card.get('priority_label', '')}</span>{card['display_title']} "
        f"<span class='cnt'>({card['alarm_count']} Alarm)</span></h4>",
        pattern_chip,
        f"<div class='meta'><b>Zaman Araligi:</b> {fmt_time(tr['start'])} - "
        f"{fmt_time(tr['end'])}</div>",
        f"<div class='meta'><b>Etkilenen Servisler:</b> "
        f"<span class='svc'>{svc_text}</span></div>",
    ]

    if root.get("alarm_id"):
        html.append(
            "<div class='hypo'><div class='t'>AI Kok Neden Hipotezi:</div>"
            f"<div class='q'>\"{root['explanation']}\"</div>"
        )
        if counter:
            html.append(
                f"<div class='c'>Karsi Olasilik: {counter['reason']}</div>"
            )
        html.append("</div>")
    else:
        html.append(
            "<div class='hypo'><div class='t'>Kok neden atanmadi</div>"
            f"<div class='q'>{root.get('explanation', '')}</div></div>"
        )

    html.append(
        "<div class='act'><div class='t'>Ilk Aksiyon:</div>"
        f"<div class='b'>{record.action if record else action.get('action', '-')}</div>"
        f"<div class='o'><b>Sorumlu:</b> "
        f"{record.owner if record else action.get('owner', '-')} &nbsp;·&nbsp; "
        f"<b>Durum:</b> <span style='color:{STATUS_COLORS.get(status, '#fff')}'>"
        f"{STATUS_LABELS.get(status, status).upper()}</span></div></div>"
    )
    html.append("</div>")

    st.markdown("".join(html), unsafe_allow_html=True)

    new_status = st.selectbox(
        "Durum",
        STATUSES,
        index=STATUSES.index(status),
        format_func=lambda s: f"Durum: {STATUS_LABELS[s].upper()}",
        key=f"status-{incident_id}",
        label_visibility="collapsed",
    )
    if new_status != status:
        store.set_status(incident_id, new_status)
        st.rerun()

    with st.expander("Kanitlar · puan kirilimi · benzer olaylar"):
        if card.get("evidence"):
            st.markdown("**Kanitlar**")
            for item in card["evidence"]:
                st.markdown(f"- {item}")

        breakdown = root.get("score_breakdown") or {}
        if breakdown:
            parts = {k: v for k, v in breakdown.items() if k != "total"}
            st.markdown(
                f"**Puan kirilimi** — toplam {breakdown.get('total', 0):.1f}/100 "
                f"(guven %{root.get('confidence', 0) * 100:.0f})"
            )
            st.bar_chart(
                pd.DataFrame({"puan": parts.values()}, index=list(parts.keys())),
                height=160,
            )

        for pattern in patterns:
            st.markdown(
                f"**Bilinen ariza oruntusu: {pattern['name']}** "
                f"(%{pattern['confidence'] * 100:.0f})"
            )
            st.caption(pattern["description"])
            st.markdown("**Ilk mudahale playbook'u**")
            for step, text in enumerate(pattern["playbook"], start=1):
                st.markdown(f"{step}. {text}")
            st.caption(f"Tipik cozum suresi: {pattern['typical_resolution']}")

        neighbours = (card.get("similar_patterns") or {}).get(
            "similar_incidents"
        ) or []
        if neighbours:
            st.markdown("**Benzer olaylar**")
            for match in neighbours:
                origin = (
                    "bu calistirma"
                    if match["source"] == "ayni_calistirma"
                    else f"gecmis · {match['run_id'][:16]}"
                )
                st.markdown(
                    f"- {match['incident_id']} (%{match['similarity'] * 100:.0f}, "
                    f"{origin}) — `{match['root_cause']}`"
                    + (
                        " · " + "; ".join(match["why"])
                        if match.get("why")
                        else ""
                    )
                )

        if card.get("correlation_reasons"):
            st.markdown("**Bu kumeler neden tek olay sayildi?**")
            for reason in card["correlation_reasons"][:8]:
                st.markdown(f"- {reason}")

        if record and record.history:
            st.markdown("**Aksiyon gecmisi**")
            for entry in reversed(record.history):
                st.markdown(
                    f"- `{entry['at']}` — "
                    f"**{STATUS_LABELS.get(entry['status'], entry['status'])}** · "
                    f"{entry.get('owner', '')} · {entry.get('note', '')}"
                )


with tab_events:
    st.caption(
        f"{summary['total_alarms']} alarm, {summary['clusters']} zamansal kume ve "
        f"{summary['incidents_detected']} olay uzerinden {len(event_cards)} olay "
        f"kartina indirgendi (ust sinir {summary['cap']}). Kartlar oncelige gore "
        "sirali."
    )

    if event_cards:
        columns = st.columns(len(event_cards), gap="small")
        for column, card in zip(columns, event_cards, strict=False):
            with column:
                render_card(card, color_of[card["incident_id"]])
    else:
        st.info("Olay karti uretilmedi.")


# --------------------------------------------------------------------------
# Denetim gorunumu
# --------------------------------------------------------------------------

with tab_audit:
    st.subheader("Denetim Gorunumu — Gurultu Defteri")
    st.caption(
        "Elenen hicbir alarm silinmez. Her kayit, hangi kuralla ve neden "
        "elendigi yazili olarak burada denetlenebilir."
    )

    noise_df = pd.DataFrame(ledger["entries"])
    mc = st.columns(4)
    mc[0].metric("Elenen alarm", ledger["total_noise"])
    mc[1].metric("Toplam icindeki payi", f"%{noise_ratio * 100:.1f}")
    mc[2].metric("Kural sayisi", len(ledger["rule_counts"]))
    mc[3].metric("Denetlenebilir kayit", f"{len(noise_df)} / {ledger['total_noise']}")

    with st.expander("Kurallarin tanimi ve olcum gerekcesi"):
        st.markdown(
            "- **maintenance_chatter** — `cert_expiry`, `backup_warn`, "
            "`ntp_drift`, `log_rotate`, `disk_warn`. Bu bes tipin zaman "
            "eksenindeki standart sapmasi 33-36 dk; 121 dakikalik pencerede "
            "tam duzgun dagilimin beklenen degeri 121/sqrt(12) = 34.9. Yani "
            "istatistiksel olarak olaylardan bagimsizlar.\n"
            "- **isolated_low_severity** — Siddet <= 2 ve ayni sunucuda "
            "+/-30 dk icinde baska alarm yok.\n"
            "- **background_baseline** — Servis ne keskin (3 dk) ne genis "
            "(9 dk) artis penceresinde; siddet <= 3.\n\n"
            "Siddet 4-5 alarmlar **asla** gurultu sayilmaz."
        )

    st.bar_chart(
        pd.DataFrame(
            {"adet": list(ledger["rule_counts"].values())},
            index=list(ledger["rule_counts"]),
        ),
        height=190,
    )

    fc = st.columns([2, 2, 2, 3])
    rule_sel = fc[0].multiselect("Kural", sorted(noise_df["noise_rule"].unique()))
    sev_sel = fc[1].multiselect("Siddet", sorted(noise_df["severity"].unique()))
    svc_sel = fc[2].multiselect("Servis", sorted(noise_df["service"].unique()))
    query = fc[3].text_input("Metin ara", placeholder="alarm_id, mesaj, tip...")

    view = noise_df
    if rule_sel:
        view = view[view["noise_rule"].isin(rule_sel)]
    if sev_sel:
        view = view[view["severity"].isin(sev_sel)]
    if svc_sel:
        view = view[view["service"].isin(svc_sel)]
    if query:
        view = view[
            view["alarm_id"].str.contains(query, case=False, na=False)
            | view["message"].str.contains(query, case=False, na=False)
            | view["alarm_type"].str.contains(query, case=False, na=False)
        ]

    st.caption(f"{len(view)} / {len(noise_df)} kayit gosteriliyor")
    st.dataframe(
        view[
            [
                "alarm_id", "timestamp", "service", "host", "severity",
                "alarm_type", "message", "noise_rule", "noise_reason",
            ]
        ],
        hide_index=True,
        width="stretch",
        height=430,
    )


# --------------------------------------------------------------------------
# Siniflandirilamayanlar
# --------------------------------------------------------------------------

with tab_unclassified:
    st.subheader("Siniflandirilamayanlar")
    if bucket_card is None:
        st.success(
            "Siniflandirilamayan alarm yok — her alarm ya bir olay kartinda "
            "ya da gurultu defterinde."
        )
    else:
        st.caption(
            "Gurultu esigini gecen ama kendi kartini hak edecek kanita "
            "ulasamayan kayitlar. Silinmezler; burada tam listeyle dururlar."
        )
        mc = st.columns(4)
        mc[0].metric("Alarm", bucket_card["alarm_count"])
        mc[1].metric("Servis", len(bucket_card["affected_services"]))
        mc[2].metric("En yuksek siddet", bucket_card["max_severity"])
        mc[3].metric(
            "Toplu alinan olay", len(bucket_card.get("rolled_up_incidents", []))
        )

        for reason in bucket_card.get("evidence", []):
            st.markdown(f"- {reason}")

        if bucket_card.get("rolled_up_incidents"):
            st.markdown("**Bu karta toplanan olaylar**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "olay": r["incident_id"],
                            "kok neden": r["root_cause"],
                            "alarm": r["alarm_count"],
                            "servisler": ", ".join(r["services"]),
                            "baslangic": fmt_time(r["time_range"]["start"]),
                            "bitis": fmt_time(r["time_range"]["end"]),
                            "oncelik": r["priority_score"],
                        }
                        for r in bucket_card["rolled_up_incidents"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

        st.markdown("**Alarm tipi dagilimi**")
        st.dataframe(
            pd.DataFrame(
                {
                    "alarm_tipi": list(bucket_card["alarm_type_histogram"]),
                    "adet": list(bucket_card["alarm_type_histogram"].values()),
                }
            ),
            hide_index=True,
            width="stretch",
            height=280,
        )


# --------------------------------------------------------------------------
# Topoloji
# --------------------------------------------------------------------------

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
            "En merkezi", max(topo["centrality"], key=lambda k: topo["centrality"][k])
        )
        cen = pd.DataFrame(
            {
                "servis": list(topo["centrality"]),
                "merkezilik": list(topo["centrality"].values()),
            }
        ).sort_values("merkezilik", ascending=False)
        st.bar_chart(cen.set_index("servis").head(15), height=280)
        st.dataframe(pd.DataFrame(topo["edges"]), hide_index=True, width="stretch")
    else:
        st.info("Topoloji ciktisi bulunamadi; motoru yeniden calistirin.")


# --------------------------------------------------------------------------
# Boru hatti
# --------------------------------------------------------------------------

with tab_pipeline:
    st.subheader("Indirgeme Zinciri ve Veri Butunlugu")

    steps = [
        ("Ham alarm", summary["total_alarms"]),
        ("Gurultu filtresinden gecen", summary["signal_alarms"]),
        ("Zamansal kume", summary["clusters"]),
        ("Topolojik olay", summary["incidents_detected"]),
        ("Olay karti", len(event_cards)),
    ]
    cols = st.columns(len(steps))
    for col, (label, value) in zip(cols, steps, strict=False):
        col.metric(label, value)

    integrity = summary["integrity"]
    if integrity["no_data_loss"] and integrity["all_alarm_ids_unique"]:
        st.success(
            f"**Veri kaybi yok.** {integrity['alarms_in_cards']} (kart) + "
            f"{integrity['alarms_in_noise_ledger']} (gurultu defteri) = "
            f"{integrity['accounted_total']} / {integrity['expected_total']}. "
            "Hicbir alarm kimligi tekrarlanmiyor."
        )
    else:
        st.error("Butunluk dogrulamasi basarisiz.")

    engine = summary["explanation_engine"]
    st.caption(
        ("LLM aciklamasi acik — " if engine["enabled"] else "Sablon aciklama motoru — ")
        + engine["reason"]
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Gurultu kurallari**")
        st.json(summary["noise_rules"])
        st.markdown("**Kume tipleri**")
        st.json(summary["cluster_kinds"])
    with c2:
        st.markdown("**Calistirma ozeti**")
        st.json(
            {
                k: v
                for k, v in summary.items()
                if k
                not in {"integrity", "noise_rules", "cluster_kinds", "explanation_engine"}
            }
        )

    if st.button("Motoru yeniden calistir", type="primary"):
        with st.spinner("Calisiyor..."):
            _run_pipeline()
        st.cache_data.clear()
        st.rerun()
