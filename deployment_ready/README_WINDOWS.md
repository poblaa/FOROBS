# FOROBS v3 – Windows deployment

## Co jest w tym folderze

| Plik/Folder | Opis |
|---|---|
| `app.py` | Główna aplikacja Streamlit |
| `transfer_agent.py` | Agent transferu danych |
| `auto_transfer.py` | Auto-transfer |
| `launcher.py` | Launcher Linux (nie używać na Windows) |
| `forobs_launcher.py` | **Launcher dla PyInstaller** – buduje exe |
| `card_layout.json` | Konfiguracja kart |
| `card_settings.json` | Ustawienia kart |
| `requirements.txt` | Lista pakietów Python |
| `elcalc/` | Moduł Fuel Plan (HTML/JS) |
| `install_windows.bat` | Krok 1 – instalacja przez internet |
| `build_windows.bat` | Krok 2 – budowa FOROBS.exe |

---

## Krok po kroku (na komputerze z Windows)

### 1. Zainstaluj Python 3.12 x64
- Pobierz z https://python.org/downloads
- Podczas instalacji zaznacz **"Add python.exe to PATH"**

### 2. Uruchom install_windows.bat
Tworzy środowisko wirtualne i instaluje potrzebne pakiety przez internet.

### 3. Uruchom build_windows.bat
Buduje `dist\FOROBS\FOROBS.exe`.

### 4. Gotowe do dystrybucji
Cały folder `dist\FOROBS\` skopiuj na docelowy komputer.
Użytkownik klieka dwukrotnie `FOROBS.exe` – przeglądarki otwiera się automatycznie.

---

## Dlaczego --onedir, nie --onefile?

Z `--onefile` plik `sys.executable` w launcher.py wskazuje na sam `.exe`.
Wywołanie `subprocess.run(sys.executable, "-m", "streamlit", ...)` ponownie uruchamia exe
→ nieskończona pętla → 10 otwartych kart.

Rozwiązanie: launcher wywołuje Streamlit **bezpośrednio w tym samym procesie**
(`stcli.main()`) – żadnych podprocesów, żadnych pętli.

---

## Struktura dist\FOROBS\ po zbudowaniu

```
dist\FOROBS\
  FOROBS.exe          ← uruchamiaj to
  app.py              ← aplikacja Streamlit
  card_layout.json
  card_settings.json
  transfer_agent.py
  auto_transfer.py
  elcalc\             ← Fuel Plan
  _internal\          ← Python + biblioteki (nie ruszaj)
```

Pliki danych użytkownika (`.xlsx`) umieszczaj w tym samym folderze co `FOROBS.exe`.
