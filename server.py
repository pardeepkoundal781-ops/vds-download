import os
import logging
import tempfile
import shutil
import urllib.request
import tarfile

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp

# ---------------- CONFIG ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium"
}

# ---------------- FFMPEG INSTALL ----------------
def install_ffmpeg():
    if os.path.exists("./ffmpeg"):
        return "./ffmpeg"

    try:
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        archive = "ffmpeg.tar.xz"

        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive, "r:xz") as tar:
            tar.extractall()

        for root, _, files in os.walk("."):
            if "ffmpeg" in files:
                shutil.move(os.path.join(root, "ffmpeg"), "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break

        os.remove(archive)
        return "./ffmpeg"
    except Exception as e:
        logger.error("FFmpeg install failed", exc_info=True)
        return None


FFMPEG_PATH = install_ffmpeg()

# ---------------- COMMON YTDLP OPTIONS ----------------
def ydl_opts_base():
    return {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "force_ipv4": True,

        # Facebook / Instagram / X FIX
        "extractor_args": {
            "youtube": {"player_client": ["ios", "web"]},
            "facebook": {"dash_manifest": False},
        },

        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1"
        ),
    }


def check_key(req):
    key = req.args.get("api_key") or req.headers.get("X-API-KEY")
    return key in API_KEYS


# ---------------- HOME ----------------
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "ffmpeg": bool(FFMPEG_PATH),
        "audio_mp3": "128 / 192 / 320 kbps",
        "platforms": ["YouTube", "Facebook", "Instagram", "X"]
    })


# ---------------- FORMATS ----------------
@app.route("/formats")
def formats():
    if not check_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get("url")
    opts = ydl_opts_base()
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = []
    for f in info.get("formats", []):
        if f.get("acodec") != "none":
            formats.append({
                "format_id": f.get("format_id"),
                "type": "audio" if f.get("vcodec") == "none" else "video",
                "ext": f.get("ext"),
                "height": f.get("height"),
                "abr": f.get("abr"),      # 128 / 160 / 192 etc
                "filesize": f.get("filesize")
            })

    return jsonify({
        "title": info.get("title"),
        "duration": info.get("duration"),
        "formats": formats
    })


# ---------------- MP3 DOWNLOAD ----------------
@app.route("/mp3")
def mp3():
    if not check_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get("url")
    quality = request.args.get("quality", "192")  # 128 / 192 / 320

    if quality not in ["128", "192", "320"]:
        quality = "192"

    temp = tempfile.mkdtemp()

    opts = ydl_opts_base()
    opts.update({
        "format": "bestaudio/best",
        "outtmpl": os.path.join(temp, "%(title).40s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
    })

    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "audio")
    mp3_file = os.path.join(temp, f"{title[:40]}.mp3")

    return send_file(
        mp3_file,
        as_attachment=True,
        download_name=os.path.basename(mp3_file)
    )


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
