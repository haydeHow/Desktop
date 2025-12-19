from flask import Flask, render_template_string, send_from_directory
import os
import threading
import webbrowser
import socket
import sys

app = Flask(__name__)


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

AUDIO_FOLDER = resource_path("audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@300;400;500&display=swap" rel="stylesheet">
    <title>Hayden Says</title>
    <style>
        :root {
            --bg: #0f1115;
            --panel: #171a21;
            --text: #e6e6e6;
            --muted: #9aa0a6;
            --accent: #4cc9f0;
        }
        body {
            font-family: "Ubuntu", system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 40px;
        }
        h1 {
            font-weight: 400;
            margin-bottom: 30px;
        }
        .sound {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--panel);
            padding: 12px 16px;
            margin-bottom: 10px;
            border-radius: 6px;
        }
        .sound-name {
            color: var(--muted);
            font-size: 15px;
        }
        button {
            background: transparent;
            color: var(--accent);
            border: 1px solid var(--accent);
            padding: 4px 14px;
            border-radius: 999px;
            cursor: pointer;
            font-size: 14px;
            font-family: inherit;
        }
        button:hover {
            background: var(--accent);
            color: #000;
        }
    </style>
</head>
<body>

<h1>Hayden Says for Brooks 💜</h1>

{% for wav in wav_files %}
<div class="sound">
    <div class="sound-name">
        {{ wav.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title() }}
    </div>
    <button onclick="playSound('{{ wav }}')">Play</button>
</div>
{% endfor %}

<script>
let audio = null;
function playSound(filename) {
    if (audio) {
        audio.pause();
        audio.currentTime = 0;
    }
    audio = new Audio("/audio/" + filename);
    audio.play();
}
</script>

</body>
</html>
"""

def get_wav_files():
    return sorted(
        f for f in os.listdir(AUDIO_FOLDER)
        if f.lower().endswith(".wav")
    )

@app.route("/")
def index():
    return render_template_string(HTML, wav_files=get_wav_files())

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

# ---------- helpers ----------
def free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")

# ---------- entry ----------
if __name__ == "__main__":
    port = free_port()

    threading.Timer(0.5, open_browser, args=(port,)).start()
    app.run(host="127.0.0.1", port=port, debug=False)
