"""Gorev 5.2 — Aksiyon durumu takibi.

Senaryonun zorunlu gereksinimlerinden biri: "Her kart icin onerilen ilk
aksiyonu uretmek ve bu aksiyonu **sahip ile durum bilgisi** icerecek sekilde
kayit altina almak" — ve opsiyonel olarak bir aksiyonun acildiktan sonra
kapanana kadar **izlenebildigini** gostermek.

Bu modul durum gecislerini `output/action_log.json` dosyasinda tutar. Kalici
veritabani zorunlu olmadigi icin (kapsam disi maddesi) duz JSON yeterli; ama
bellek ici tutmak yerine diske yazmak, demoda "kapattim, sayfayi yeniledim,
hala kapali" diyebilmeyi sagliyor.

Durum makinesi:

    open  ->  in_progress  ->  resolved
      ^______________|______________|

Her gecis zaman damgasi, sahip ve opsiyonel not ile gunluge islenir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from src import config

STATUSES = ("open", "in_progress", "resolved")

STATUS_LABELS = {
    "open": "Acik",
    "in_progress": "Uzerinde calisiliyor",
    "resolved": "Cozuldu",
}

STATUS_ICONS = {
    "open": "[ ACIK ]",
    "in_progress": "[ CALISILIYOR ]",
    "resolved": "[ COZULDU ]",
}

# Bir durumdan hangi durumlara gecilebilir.
TRANSITIONS = {
    "open": ("in_progress", "resolved"),
    "in_progress": ("resolved", "open"),
    "resolved": ("open", "in_progress"),
}


@dataclass(slots=True)
class ActionRecord:
    incident_id: str
    status: str
    owner: str
    action: str
    created_at: str
    updated_at: str
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "owner": self.owner,
            "action": self.action,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActionRecord:
        return cls(
            incident_id=data["incident_id"],
            status=data.get("status", "open"),
            owner=data.get("owner", ""),
            action=data.get("action", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            history=list(data.get("history", [])),
        )


class ActionStore:
    """Olay kartlarinin aksiyon durumlarini tutan kalici depo."""

    def __init__(self, path=None):
        self.path = path or config.ACTION_LOG_JSON
        self.records: dict[str, ActionRecord] = {}
        self.load()

    # ------------------------------------------------------------ kalicilik

    def load(self) -> None:
        if not self.path.is_file():
            self.records = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.records = {}
            return
        self.records = {
            item["incident_id"]: ActionRecord.from_dict(item)
            for item in payload.get("actions", [])
            if "incident_id" in item
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "actions": [rec.to_dict() for rec in self.records.values()],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ----------------------------------------------------------- kullanim

    def sync_with_cards(self, cards: list[dict]) -> None:
        """Pipeline ciktisindaki kartlari depoya tanitir.

        Var olan kayitlarin durumu **korunur** — motor yeniden calissa bile
        operatorun kapattigi aksiyon yeniden acilmaz. Yeni kartlar `open`
        durumuyla eklenir; artik uretilmeyen kartlarin kaydi temizlenir.
        """
        seen: set[str] = set()
        for card in cards:
            incident_id = card["incident_id"]
            seen.add(incident_id)
            action = card.get("recommended_action") or {}
            if incident_id in self.records:
                # Aksiyon metni/sahibi guncellenebilir, durum korunur.
                record = self.records[incident_id]
                record.action = action.get("action", record.action)
                record.owner = action.get("owner", record.owner)
                continue

            now = action.get("created_at") or datetime.now().isoformat(
                timespec="seconds"
            )
            self.records[incident_id] = ActionRecord(
                incident_id=incident_id,
                status=action.get("status", "open"),
                owner=action.get("owner", "platform-oncall"),
                action=action.get("action", ""),
                created_at=now,
                updated_at=now,
                history=[
                    {
                        "status": "open",
                        "at": now,
                        "owner": action.get("owner", "platform-oncall"),
                        "note": "Olay karti otomatik olarak acildi.",
                    }
                ],
            )

        for stale in set(self.records) - seen:
            del self.records[stale]

        self.save()

    def get(self, incident_id: str) -> ActionRecord | None:
        return self.records.get(incident_id)

    def status_of(self, incident_id: str) -> str:
        record = self.records.get(incident_id)
        return record.status if record else "open"

    def set_status(
        self,
        incident_id: str,
        status: str,
        owner: str | None = None,
        note: str = "",
    ) -> ActionRecord:
        """Durumu degistirir ve gecisi zaman damgasiyla gunluge isler."""
        if status not in STATUSES:
            raise ValueError(f"Gecersiz durum: {status}")

        record = self.records.get(incident_id)
        if record is None:
            raise KeyError(f"Bilinmeyen olay: {incident_id}")

        now = datetime.now().isoformat(timespec="seconds")
        previous = record.status
        record.status = status
        record.updated_at = now
        if owner:
            record.owner = owner
        record.history.append(
            {
                "status": status,
                "previous_status": previous,
                "at": now,
                "owner": record.owner,
                "note": note or f"{STATUS_LABELS[previous]} -> {STATUS_LABELS[status]}",
            }
        )
        self.save()
        return record

    def counts(self) -> dict[str, int]:
        out = {status: 0 for status in STATUSES}
        for record in self.records.values():
            out[record.status] = out.get(record.status, 0) + 1
        return out

    def timeline(self) -> list[dict]:
        """Tum durum gecisleri, en yeniden eskiye."""
        rows: list[dict] = []
        for record in self.records.values():
            for entry in record.history:
                rows.append({"incident_id": record.incident_id, **entry})
        rows.sort(key=lambda r: r.get("at", ""), reverse=True)
        return rows
