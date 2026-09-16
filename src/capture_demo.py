"""Gorev 6.2 — Panonun ekran goruntulerini `demo/` altina kaydeder.

    python -m src.capture_demo

Calisan bir Streamlit sunucusu bekler (varsayilan http://localhost:8501).
Sekmeler arasinda gezinir, bir aksiyonun durumunu **canli olarak** degistirir
ve her adimi PNG olarak yazar. Ekran goruntuleri elle degil, tekrar
uretilebilir bicimde olusur.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config

URL = "http://localhost:8501"
VIEWPORT = {"width": 1920, "height": 1080}
MAIN = "section[data-testid='stMain']"


def _settle(page, ms: int = 2200) -> None:
    """Streamlit'in yeniden calismasini bekle."""
    page.wait_for_timeout(ms)
    try:
        page.wait_for_selector(
            "[data-testid='stStatusWidget']", state="detached", timeout=10_000
        )
    except Exception:  # noqa: BLE001 — gosterge hic cikmamis olabilir
        pass


def _scroll_main(page, top: int) -> None:
    """Streamlit ana bolumu kendi icinde kayar; pencere kaydirmasi ise yaramaz."""
    page.evaluate(
        "([sel, top]) => { const el = document.querySelector(sel);"
        " if (el) el.scrollTop = top; }",
        [MAIN, top],
    )
    page.wait_for_timeout(700)


def _shot(page, name: str, full: bool = False) -> None:
    path = config.DEMO_DIR / name
    page.screenshot(path=str(path), full_page=full)
    print(f"  kaydedildi: demo/{name}  ({path.stat().st_size // 1024} KB)")


def _open_tab(page, name: str) -> None:
    page.get_by_role("tab", name=name).click()
    _settle(page, 1800)
    _scroll_main(page, 0)


def main() -> int:
    from playwright.sync_api import sync_playwright

    config.DEMO_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle", timeout=90_000)
        _settle(page, 8000)

        tabs = [t.strip() for t in page.get_by_role("tab").all_inner_texts()]
        # Sekme etiketleri emoji iceriyor; Windows konsolu (cp1252) basamaz.
        safe = [t.encode("ascii", "ignore").decode().strip() for t in tabs]
        print(f"Bulunan sekmeler: {safe}")
        print("Ekran goruntuleri aliniyor...")

        # --- 1) Ana giris sayfasi: ozet serit + zaman serisi + kartlar ----
        _shot(page, "01-ana-pano.png")
        _shot(page, "02-ana-pano-tam.png", full=True)

        # --- 2) Olay kartlari serisi --------------------------------------
        _scroll_main(page, 520)
        _shot(page, "03-olay-kartlari.png")

        # --- 2b) "(N Alarm)" -> ham alarm akisi (terminal gorunumu) -------
        try:
            page.get_by_role("button", name="Alarm)").first.click()
            _settle(page, 1800)
            print("  ham alarm akisi penceresi acildi")
            _shot(page, "03b-ham-alarm-akisi.png")
            page.keyboard.press("Escape")
            _settle(page, 900)
        except Exception as exc:  # noqa: BLE001
            print(f"  [uyari] log penceresi acilamadi: {exc}")

        # --- 3) Kart ayrintisi: kanit, puan, oruntu -----------------------
        try:
            page.get_by_text(
                "Kanitlar · puan kirilimi · benzer olaylar"
            ).first.click()
            _settle(page, 1500)
            _scroll_main(page, 900)
            print("  kart ayrinti paneli acildi")
        except Exception as exc:  # noqa: BLE001
            print(f"  [uyari] ayrinti paneli acilamadi: {exc}")
        _shot(page, "04-kart-ayrinti-kanit-oruntu.png")

        # --- 4) Aksiyonu canli degistir (izlenebilirlik kaniti) -----------
        _scroll_main(page, 520)
        try:
            page.locator(".st-key-status-INC-001").scroll_into_view_if_needed()
            page.locator(".st-key-status-INC-001").click()
            page.wait_for_timeout(800)
            page.get_by_text("Durum: UZERINDE CALISILIYOR", exact=True).last.click()
            _settle(page, 2500)
            print("  aksiyon durumu degistirildi: ACIK -> UZERINDE CALISILIYOR")
        except Exception as exc:  # noqa: BLE001
            print(f"  [uyari] durum degisikligi otomasyonu atlandi: {exc}")
        _shot(page, "05-aksiyon-durum-degisti.png")

        # --- 5) Denetim gorunumu (X-Factor) -------------------------------
        _open_tab(page, tabs[1])
        _shot(page, "06-denetim-gorunumu.png")
        _scroll_main(page, 900)
        _shot(page, "07-gurultu-defteri-tablo.png")

        # --- 6) Siniflandirilamayanlar ------------------------------------
        _open_tab(page, tabs[2])
        _shot(page, "08-siniflandirilamayanlar.png")

        # --- 7) Topoloji ---------------------------------------------------
        _open_tab(page, tabs[3])
        _shot(page, "09-topoloji.png")

        # --- 8) Boru hatti / veri butunlugu --------------------------------
        _open_tab(page, tabs[4])
        _shot(page, "10-boru-hatti-butunluk.png")

        browser.close()

    print("Tamam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
