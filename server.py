import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== FLASK ==================
app = Flask(__name__)
CORS(app)

# ================== API KEYS ==================
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# ================== FFMPEG AUTO INSTALL ==================
def install_ffmpeg():
    if os.path.exists("./ffmpeg"):
        return "./ffmpeg"
    try:
        logger.info("⏳ Downloading FFmpeg...")
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        archive = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, archive)

        with tarfile.open(archive, "r:xz") as tar:
            tar.extractall()

        for root, dirs, files in os.walk("."):
            if "ffmpeg" in files:
                shutil.move(os.path.join(root, "ffmpeg"), "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break

        os.remove(archive)
        return "./ffmpeg"
    except Exception as e:
        logger.error(f"FFmpeg install error: {e}")
        return None

FFMPEG_PATH = install_ffmpeg()

# ================== YT-DLP OPTIONS ==================
def get_ydl_opts():
    opts = {
        # SAFE FORMAT (Short + Long)
        'format': (
            'bv*[ext=mp4][height<=1080]/'
            'best[ext=mp4][height<=1080]/'
            'best'
        ),
        'merge_output_format': 'mp4',
        'trim_file_name': 50,

        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'geo_bypass': True,
        'force_ipv4': True,

        'retries': 10,
        'fragment_retries': 10,
        'http_chunk_size': 10485760,  # 10MB

        # YOUTUBE FIX
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android']
            }
        },

        'user_agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36',

        'source_address': '0.0.0.0',
    }

    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH
    if os.path.exists("cookies.txt"):
        opts['cookiefile'] = "cookies.txt"

    return opts

# ================== AUTH ==================
def verify_api_key(req):
    key = req.args.get("api_key") or req.headers.get("X-API-KEY")
    return key in API_KEYS

# ================== ROUTES ==================
@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "ffmpeg": os.path.exists("./ffmpeg"),
        "cookies": os.path.exists("cookies.txt"),
        "mode": "Render / Railway Ready"
    })

@app.route("/formats")
def formats():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_key"}), 401

    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    data = []
    for f in info.get("formats", []):
        if not f.get("format_id"):
            continue
        data.append({
            "id": f["format_id"],
            "ext": f.get("ext"),
            "resolution": f.get("resolution"),
            "filesize": f.get("filesize") or f.get("filesize_approx")
        })

    return jsonify({
        "title": info.get("title"),
        "duration": info.get("duration"),
        "formats": data[:20]
    })

@app.route("/download")
def download():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_key"}), 401

    url = request.args.get("url")
    if not url:
        return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    opts = get_ydl_opts()
    opts["outtmpl"] = os.path.join(temp_dir, "%(title).50s.%(ext)s")

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if "requested_downloads" in info:
        file_path = info["requested_downloads"][0]["filepath"]
    else:
        file_path = ydl.prepare_filename(info)

    return send_file(file_path, as_attachment=True)

@app.route("/mp3")
def mp3():
    if not verify_api_key(request):
        return jsonify({"error": "invalid_key"}), 401

    url = request.args.get("url")
    temp_dir = tempfile.mkdtemp()

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

    base = os.path.splitext(
        info["requested_downloads"][0]["filepath"]
    )[0]

    return send_file(base + ".mp3", as_attachment=True)

# ================== START ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
