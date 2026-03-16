import os
import sys
import time
import threading
import webbrowser

# -----------------------------------------------------------------------
# FOROBS v3 launcher – PyInstaller compatible
#
# CRITICAL: Do NOT use subprocess.run(sys.executable, ...) here.
# When bundled by PyInstaller, sys.executable IS this .exe.
# Calling it with "-m streamlit run" would re-launch the exe in an
# infinite loop and open dozens of browser tabs.
#
# Instead: call Streamlit's internal CLI directly in-process.
# -----------------------------------------------------------------------


def open_browser():
    """Open the app in the default browser after a short startup delay."""
    time.sleep(4)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    # Resolve the directory containing this exe (or script during dev).
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    # With --onedir PyInstaller puts the exe and all bundled data together in
    # one folder. We chdir there so user-data files (xlsx, json) placed next
    # to the exe are found by app.py via relative paths.
    os.chdir(exe_dir)

    # Make sure modules placed next to the exe (transfer_agent, auto_transfer)
    # are importable.
    if exe_dir not in sys.path:
        sys.path.insert(0, exe_dir)

    # Open browser once – the thread is a daemon so it won't block shutdown.
    threading.Thread(target=open_browser, daemon=True).start()

    # Run Streamlit inside the current process.
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", "app.py",
        "--global.developmentMode", "false",
        "--server.port", "8501",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.address", "localhost",
    ]
    stcli.main()
