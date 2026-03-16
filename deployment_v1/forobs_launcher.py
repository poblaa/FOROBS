import os
import sys
import time
import threading
import webbrowser
import subprocess


def open_browser():
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(base_dir)
    threading.Thread(target=open_browser, daemon=True).start()
    subprocess.run([
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        "8501",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.address",
        "0.0.0.0",
    ])
