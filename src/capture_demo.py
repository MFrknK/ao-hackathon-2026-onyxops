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
VIEWPORT = {"width": 1680, "height": 1150}
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
    size = path.stat().st_size // 1024
    print(f"  kaydedildi: demo/{name}  ({size} KB)")


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
        _settle(page, 7000)

        tabs = [t.strip() for t in page.get_by_role("tab").all_inner_texts()]
        print(f"Bulunan sekmeler: {tabs}")

        print("Ekran goruntuleri aliniyor...")

        # --- 1) Olay panosu, ust gorunum -------------------------------
        _shot(page, "01-olay-panosu.png")

        # --- 2) Kok neden + kanit + karsi hipotez ----------------------
        _scroll_main(page, 1150)
        _shot(page, "02-kok-neden-kanit.png")

        # --- 3) Karsi hipotez + aksiyon kontrolleri --------------------
        _scroll_main(page, 2050)
        _shot(page, "03-karsi-hipotez-aksiyon.png")

        # --- 4) Aksiyonu canli degistir (izlenebilirlik kaniti) --------
        _scroll_main(page, 0)
        select = page.locator("div[data-testid='stSelectbox']").first
        try:
            select.click()
            page.wait_for_timeout(600)
            page.get_by_role("option", name="Uzerinde calisiliyor").first.click()
            _settle(page, 1500)
            page.get_by_role("button", name="Kaydet").first.click()
            _settle(page, 2500)
            print("  aksiyon durumu degistirildi: Acik -> Uzerinde calisiliyor")
        except Exception as exc:  # noqa: BLE001
            print(f"  [uyari] durum degisikligi otomasyonu atlandi: {exc}")
        _shot(page, "04-aksiyon-durum-degisti.png")

        # --- 5) Gurultu denetimi (X-Factor) ----------------------------
        _open_tab(page, tabs[2])
        _shot(page, "05-gurultu-denetimi.png")
        _scroll_main(page, 900)
        _shot(page, "06-gurultu-defteri-tablo.png")

        # --- 6) Aksiyon takibi -----------------------------------------
        _open_tab(page, tabs[1])
        _shot(page, "07-aksiyon-takibi.png")
        _scroll_main(page, 850)
        _shot(page, "08-durum-gecis-gunlugu.png")

        # --- 7) Topoloji ------------------------------------------------
        _open_tab(page, tabs[3])
        _shot(page, "09-topoloji.png")

        # --- 8) Boru hatti / veri butunlugu -----------------------------
        _open_tab(page, tabs[4])
        _shot(page, "10-boru-hatti-butunluk.png")

        browser.close()

    print("Tamam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
