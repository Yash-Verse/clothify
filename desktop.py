# desktop.py
import threading
import webview
import os
from app import app

def start_flask():
    # When running inside a thread, disable the reloader and debug reloader signals.
    # Use host and port that webview will open.
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Start flask in a background thread
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    # Open the desktop window to the local Flask app
    webview.create_window('Cloth Store (Desktop)', 'http://127.0.0.1:5000', width=1100, height=700)
    webview.start()
