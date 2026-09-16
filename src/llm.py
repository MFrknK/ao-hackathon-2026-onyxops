"""Opsiyonel LLM zenginlestirmesi (Gorev 3.3'un dogal dil kismi).

**Kritik tasarim karari:** LLM karar vermez. Kok neden ve karsi hipotez
`src/root_cause.py` icindeki deterministik puanlama motoru tarafindan
secilmistir; buradaki model yalnizca bu karari nobetci muhendisin okuyacagi
dile cevirir. Korelasyon karari denetime acik olmak zorunda oldugu icin bir
olasilik dagilimina birakilmadi.

Anahtar yoksa, `anthropic` paketi kurulu degilse veya cagri basarisiz olursa
sablon aciklamasi oldugu gibi kalir ve uygulama eksiksiz calisir. Bu yuzden
bu modulun tamami "best effort" olarak yazildi — hicbir hata yukari sizmaz.

Prompt metni: `prompts/root_cause_explanation.md`
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.models import Incident

SYSTEM_PROMPT = """\
Sen bir telekom operasyon merkezinde calisan kidemli bir site reliability
engineer'sin. Gorevin, otomatik korelasyon motorunun urettigi kok neden
kararini nobetci muhendise aciklamaktir.

Kurallar:
- Karari DEGISTIRME. Sana verilen kok neden ve karsi hipotez kesindir.
- Yalnizca sana verilen kanitlara dayan. Veri disinda bilgi uydurma.
- Turkce yaz, ASCII karakter kullan.
- En fazla 4 cumle. Teknik ama yalin.
- "Muhtemelen", "olabilir" gibi belirsizlik ifadelerini yalnizca karsi
  hipotezden bahsederken kullan.
- Cikti yalnizca duz metin olsun; baslik, madde isareti veya JSON verme.
"""


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "evet"}


@dataclass(slots=True)
class LLMStatus:
    """Zenginlestirmenin neden calistigi / calismadigi — panoda gosterilir."""

    enabled: bool
    reason: str
    model: str = ""
    enriched: int = 0

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "reason": self.reason,
            "model": self.model,
            "enriched_incidents": self.enriched,
        }


def _build_user_prompt(incident: Incident, evidence: list[str]) -> str:
    root = incident.root_cause
    counter = incident.counter_hypothesis

    lines = [
        f"OLAY: {incident.incident_id}",
        f"Zaman araligi: {incident.start:%H:%M:%S} - {incident.end:%H:%M:%S} "
        f"({incident.duration_minutes} dakika)",
        f"Etkilenen servisler ({len(incident.services)}): "
        f"{', '.join(incident.services)}",
        f"Toplam alarm: {incident.alarm_count}",
        f"En yuksek siddet: {incident.max_severity}",
        "",
        "KOK NEDEN (motor karari, degistirilemez):",
        f"  {root.alarm_id} | {root.timestamp:%H:%M:%S} | "
        f"{root.service} / {root.host}",
        f"  Tip: {root.alarm_type} (neden egilimi {root.type_prior:.2f})",
        f"  Siddet: {root.severity} ({root.severity_label})",
        f"  Mesaj: {root.message}",
        f"  Puan kirilimi: {incident.root_cause_score}",
        "",
        "KANITLAR:",
    ]
    lines.extend(f"  - {item}" for item in evidence)

    if counter is not None:
        lines.extend(
            [
                "",
                "KARSI HIPOTEZ:",
                f"  {counter.alarm_id} | {counter.service} | "
                f"{counter.alarm_type}",
                f"  {incident.counter_reason}",
            ]
        )

    lines.extend(
        [
            "",
            "Yukaridaki kok neden kararini 4 cumleyi gecmeden acikla. Once ne "
            "oldugunu, sonra neden bu servisin tetikleyici oldugunu, son olarak "
            "karsi hipotezin neden hala masada oldugunu yaz.",
        ]
    )
    return "\n".join(lines)


def enrich_explanations(
    incidents: list[Incident], evidence_map: dict[str, list[str]]
) -> LLMStatus:
    """Aciklamalari LLM ile zenginlestirmeyi dener; basarisizsa sessizce vazgecer."""
    if not _env_flag("ONYXOPS_USE_LLM", default=False):
        return LLMStatus(
            False, "ONYXOPS_USE_LLM kapali — deterministik sablon motoru kullanildi."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return LLMStatus(
            False, "ANTHROPIC_API_KEY tanimli degil — sablon motoru kullanildi."
        )

    try:
        import anthropic  # noqa: PLC0415  (opsiyonel bagimlilik)
    except ImportError:
        return LLMStatus(
            False,
            "`anthropic` paketi kurulu degil (pip install anthropic) — "
            "sablon motoru kullanildi.",
        )

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5").strip()

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        return LLMStatus(False, f"Anthropic istemcisi kurulamadi: {exc}")

    enriched = 0
    for incident in incidents:
        if incident.root_cause is None:
            continue
        try:
            response = client.messages.create(
                model=model,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_prompt(
                            incident, evidence_map.get(incident.incident_id, [])
                        ),
                    }
                ],
            )
            text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if text:
                incident.explanation = text
                incident.explanation_source = "llm"
                enriched += 1
        except Exception:  # noqa: BLE001, S110
            # Tek bir olayin basarisizligi tum calistirmayi dusurmemeli.
            continue

    if enriched == 0:
        return LLMStatus(
            False, "LLM cagrilari sonuc vermedi — sablon motoru kullanildi.", model
        )

    return LLMStatus(
        True,
        f"{enriched} olayin aciklamasi {model} ile zenginlestirildi.",
        model,
        enriched,
    )
