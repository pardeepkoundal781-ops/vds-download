import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= FLASK =================
app = Flask(__name__)
CORS(app)

# ================= API KEYS =================
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium"
}

# ================= YT-DLP OPTIONS =================
def get_ydl_opts():
    opts = {
        # SAFE FORMAT (Shorts + Long)
        "format": (
            "bv*[ext=mp4][height<=1080]/"
            "best[ext=mp4][height<=1080]/"
            "best"
        ),
        "merge_output_format": "mp4",
        "trim_file_name": 50,

        # Stability
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "retries": 10,
        "fragment_retries": 10,
        "http_chunk_size": 10485760,  # 10MB
        "force_ipv4": True,

        # YouTube client fix
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "android"]
            }
        },

        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    if os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"

    return opts

# ================= AUTH =================
def verify_api_key(req):
    key = req.args.get("api_key") or req.headers.get("X-API-KEY")
    return key in API_KEYS

# ================= ROUTES =================
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "env": "Render / Railway Ready",
        "cookies": os.path.exists("cookies.txt")
    })

# ---------- FORMATS ----------
@app.route("/formats")
def formats():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_api_key"}), 401

    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)

        out = []
        for f in info.get("formats", []):
            if not f.get("format_id"):
                continue
            out.append({
                "id": f["format_id"],
                "ext": f.get("ext"),
                "resolution": f.get("resolution"),
                "filesize": f.get("filesize") or f.get("filesize_approx")
            })

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "formats": out[:20]
        })

    except Exception as e:
        logger.error(e)
        return jsonify({"error": "format_fetch_failed"}), 500

# ---------- DOWNLOAD ----------
@app.route("/download")
def download():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_api_key"}), 401

    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        temp_dir = "/tmp"
        opts = get_ydl_opts()
        opts["outtmpl"] = os.path.join(temp_dir, "%(title).50s.%(ext)s")

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        file_path = None
        if "requested_downloads" in info and info["requested_downloads"]:
            file_path = info["requested_downloads"][0].get("filepath")

        if not file_path:
            file_path = ydl.prepare_filename(info)

        if not os.path.exists(file_path):
            return jsonify({"error": "file_not_found"}), 500

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        logger.error(e)
        return jsonify({"error": "download_failed"}), 500

# ---------- MP3 ----------
@app.route("/mp3")
def mp3():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_api_key"}), 401

    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        temp_dir = "/tmp"
        opts = get_ydl_opts()
        opts.update({
            "format": "bestaudio/best",
            "outtmpl": os.path.join(temp_dir, "%(title).50s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        base = info["requested_downloads"][0]["filepath"]
        mp3_file = os.path.splitext(base)[0] + ".mp3"

        return send_file(mp3_file, as_attachment=True)

    except Exception as e:
        logger.error(e)
        return jsonify({"error": "mp3_failed"}), 500

# ================= START =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
