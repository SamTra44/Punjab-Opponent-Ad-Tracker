# desktop_app.py
# -----------------------------------------------------------------------------
# Narrative Intelligence ko ek DESKTOP APP ki tarah chalata hai.
# - Flask server ko background mein localhost pe start karta hai
# - Phir ek native app-window (pywebview) mein dashboard kholta hai
#   (browser jaisa nahi — proper desktop app jaisa)
# - Agar pywebview/WebView2 na ho to default browser mein khol deta hai (fallback)
#
# Desktop icon (shortcut) isi file ko pythonw se chalata hai.
# -----------------------------------------------------------------------------

import os
import sys
import threading
import time
import socket

# Working directory project folder pe set karo (taaki .env, templates mil jayein).
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)


def _free_port(preferred=5057):
    """Preferred port free ho to wahi, warna koi bhi free port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferred))
        s.close()
        return preferred
    except OSError:
        s.close()
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.bind(("127.0.0.1", 0))
        port = s2.getsockname()[1]
        s2.close()
        return port


PORT = _free_port(int(os.environ.get("NI_DESKTOP_PORT", "5057")))
os.environ.setdefault("PORT", str(PORT))

# Flask app import (import pe hi warm-up fetch + scheduler start ho jaata hai).
import app as ni  # noqa: E402

URL = f"http://127.0.0.1:{PORT}/"


def _serve():
    ni.app.run(host="127.0.0.1", port=PORT, debug=False,
               use_reloader=False, threaded=True)


def _wait_until_up(timeout=20):
    """Server up hone tak ruko (taaki window pe blank na aaye)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main():
    # 1) Flask server background thread mein.
    threading.Thread(target=_serve, daemon=True).start()
    _wait_until_up()

    # 2) Native app window (pywebview). Na chale to browser fallback.
    try:
        import webview
        icon = os.path.join(HERE, "static", "app.ico")
        kwargs = {}
        if os.path.exists(icon):
            # icon param sirf kuch backends pe — safe try.
            try:
                webview.create_window(
                    "Narrative Intelligence", URL,
                    width=1440, height=900, min_size=(1000, 650),
                )
            except Exception:
                webview.create_window("Narrative Intelligence", URL,
                                      width=1440, height=900)
        else:
            webview.create_window("Narrative Intelligence", URL,
                                  width=1440, height=900)
        webview.start()
    except Exception:
        # Fallback: default browser mein kholo, server chalu rakho.
        import webbrowser
        webbrowser.open(URL)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
