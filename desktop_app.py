# desktop_app.py
# -----------------------------------------------------------------------------
# Narrative Intelligence ko ek DESKTOP APP ki tarah chalata hai.
#
# Tareeka (sabse reliable):
#   1. Flask server ko background mein localhost pe start karta hai
#   2. Chrome (ya Edge) ko "--app" mode mein kholta hai -> ek clean standalone
#      window (no tabs, no address bar) — bilkul desktop app jaisa
#   3. Jab user app-window band karta hai, python process exit ho jaata hai
#      (server bhi band) — clean.
#
# Agar Chrome/Edge na mile to: pywebview, phir default browser (fallbacks).
# Desktop icon (shortcut) isi file ko pythonw se chalata hai.
# -----------------------------------------------------------------------------

import os
import sys
import shutil
import socket
import tempfile
import threading
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)


def _free_port(preferred=5057):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferred)); s.close(); return preferred
    except OSError:
        s.close()
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.bind(("127.0.0.1", 0)); port = s2.getsockname()[1]; s2.close(); return port


PORT = _free_port(int(os.environ.get("NI_DESKTOP_PORT", "5057")))
os.environ.setdefault("PORT", str(PORT))

import app as ni  # noqa: E402  (import pe warm-up + scheduler start)

URL = f"http://127.0.0.1:{PORT}/"


def _serve():
    ni.app.run(host="127.0.0.1", port=PORT, debug=False,
               use_reloader=False, threaded=True)


def _wait_until_up(timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _find_browser():
    """Chrome ya Edge ka path dhoondo."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("chrome") or shutil.which("msedge")


def main():
    # 1) Flask server background thread mein.
    threading.Thread(target=_serve, daemon=True).start()
    _wait_until_up()

    # 2) Chrome/Edge ko app-mode mein kholo (sabse reliable desktop-window).
    browser = _find_browser()
    if browser:
        # Apna alag profile -> fresh instance, jisse window band hone par
        # process.wait() return ho jaata hai (clean shutdown).
        profile = os.path.join(tempfile.gettempdir(), "narrative_intel_app")
        try:
            proc = subprocess.Popen([
                browser,
                f"--app={URL}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1440,900",
            ])
            proc.wait()  # app-window band hone tak chalega
            return
        except Exception:
            pass

    # 3) Fallback: pywebview native window.
    try:
        import webview
        webview.create_window("Narrative Intelligence", URL,
                              width=1440, height=900)
        webview.start()
        return
    except Exception:
        pass

    # 4) Last fallback: default browser, server chalu rakho.
    import webbrowser
    webbrowser.open(URL)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
