#!/usr/bin/env bash
# Sahne oncesi tek komutluk hazirlik.
#
#   ./demo_baslat.sh
#
# 1) Motoru calistirir ve veri butunlugunu dogrular (tutmazsa DURUR),
# 2) Aksiyon gunlugunu temizler ki tum kartlar "ACIK" baslasin,
# 3) Panoyu acar.
#
# Kura beklerken calistirin; sahnede yalnizca tarayiciyi tam ekran yapin.

set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/3  Veri paketi dogrulamasi =================================="
python -m src.verify_setup || {
  echo
  echo "!! Veri dogrulamasi BASARISIZ. Demoya cikmadan once bakin."
  exit 1
}

echo "== 2/3  Korelasyon motoru ======================================="
python -m src.pipeline || {
  echo
  echo "!! Boru hatti BASARISIZ (butunluk tutmadi). Demoya cikmadan once bakin."
  exit 1
}

# Kartlar temiz baslasin: onceki demo'nun durum degisiklikleri silinir.
rm -f output/action_log.json
echo
echo "   Aksiyon gunlugu temizlendi — tum kartlar 'ACIK' baslayacak."

echo
echo "== 3/3  Pano ===================================================="
echo "   http://localhost:8501"
echo "   Sahne notlari: docs/sunum.md"
echo "   Tarayicida F11 (tam ekran) + %80 yakinlastirma yapin."
echo
exec python -m streamlit run src/app.py --server.port 8501
