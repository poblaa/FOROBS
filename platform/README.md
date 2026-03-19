# Platform build hub

Ten folder jest miejscem docelowym pod gotowy build Windows.

## Docelowy output

Po zbudowaniu na Windows:

- `platform/windows_release/FOROBS/FOROBS.exe`

## Jak uruchamiać na Windows

1. Otwórz `cmd` lub PowerShell w folderze `platform`.
2. Uruchom:
   - `install_windows_dependencies.bat`
   - `build_windows_to_platform.bat`

## Uwagi

- Build EXE musi być wykonany na Windows (PyInstaller build jest platform-specific).
- Źródło builda: `deployment_v1.2`.
- Output jest kopiowany automatycznie do `platform/windows_release/FOROBS`.
