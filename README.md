FOROBS v3

Desktop logbook + calculators for ship operations, built with Streamlit.

Main components
- Logbook app: app.py
- Fuel plan module: elcalc/
- Windows deployment bundle: deployment_v1/

Quick run (Linux)
1) Create/activate venv
2) Install requirements
3) Run Streamlit

Example commands
- python3 -m venv .venv
- source .venv/bin/activate
- pip install -r requirements.txt
- streamlit run app.py --server.port 8501

Windows build plan (no install on target PC)
Build is done on a separate Windows build PC, then only FOROBS.exe is copied to target PC.

Prepared files in deployment_v1/
- forobs_launcher.py
- install_from_cache_windows.bat
- build_windows.bat
- download_cache_windows/ (offline wheel cache)
- NEXT_STEP_WINDOWS.txt

Build steps on Windows build PC
1) Install Python 3.12 x64
2) Copy full deployment_v1 folder to build PC
3) Run install_from_cache_windows.bat
4) Run build_windows.bat
5) Result: dist\FOROBS.exe

Target PC (no installation)
1) Copy FOROBS.exe
2) Copy card_settings.json and card_layout.json next to exe
3) Optional: copy logbook.db (if migrating data)
4) Run FOROBS.exe

Map status for Fuel plan (elcalc)
- Map tiles are online (v1)
- Offline map tiles postponed to v2

Repository notes
- Runtime-generated files are ignored by git (logbook.db, chart_data.json, checkpoints, venv)
- Use deployment_v1/download_cache_windows for Windows-targeted package cache
