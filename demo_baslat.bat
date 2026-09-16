@echo off
REM Sahne oncesi tek komutluk hazirlik (Windows).
REM Kura beklerken calistirin; sahnede yalnizca tarayiciyi tam ekran yapin.
cd /d "%~dp0"

echo == 1/3  Veri paketi dogrulamasi ==================================
python -m src.verify_setup || goto :hata

echo == 2/3  Korelasyon motoru =======================================
python -m src.pipeline || goto :hata

del /q output\action_log.json 2>nul
echo    Aksiyon gunlugu temizlendi - tum kartlar "ACIK" baslayacak.

echo.
echo == 3/3  Pano ====================================================
echo    http://localhost:8501
echo    Sahne notlari: docs\sunum.md
echo    Tarayicida F11 (tam ekran) + %%80 yakinlastirma yapin.
echo.
python -m streamlit run src/app.py --server.port 8501
goto :eof

:hata
echo.
echo !! BASARISIZ. Demoya cikmadan once bakin.
exit /b 1
