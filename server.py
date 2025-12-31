import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API Keys
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# 1. AUTO FFmpeg INSTALLER
def install_ffmpeg():
    if os.path.exists("./ffmpeg"):
        return "./ffmpeg"
    try:
        logger.info("⏳ Downloading FFmpeg...")
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename)

        with tarfile.open(filename, "r:xz") as tar:
            tar.extractall()

        for root, dirs, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break

        if os.path.exists(filename):
            os.remove(filename)

        return "./ffmpeg"
    except Exception as e:
        logger.error(f"FFmpeg install error: {e}")
        return None

FFMPEG_PATH = install_ffmpeg()

def get_ydl_opts():
    """
    ULTIMATE LONG+SHORT YouTube fix (2025 Dec)
    """
    opts = {
        # Format + merge
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'trim_file_name': 50,
        
        # Basic stability
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True,

        # NETWORK CRITICAL (LONG VIDEOS)
        'retries': 20,
        'fragment_retries': 100,        # DASH fragments retry
        'continuedl': True,
        'http_chunk_size': 5 * 1024 * 1024,  # 5MB chunks (smaller = stable)
        'socket_timeout': 30,           # connection timeout
        'extractor_retries': 5,
        'sleep_interval': 1,            # delay between requests
        'max_sleep_interval': 10,

        # YouTube CLIENT FIX (No TV/DRM)
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'default', 'web_safari', 'web_embedded'],
                'skip': ['hls', 'dash']  # avoid problematic streams
            }
        },
        
        # Rate limiting bypass
        'source_address': '0.0.0.0',
        'throttled_rate': 100000,      # slow down if throttled
    }

    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'

    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    has_cookies = "YES ✅" if os.path.exists('cookies.txt') else "NO ❌"
    has_ffmpeg = "YES ✅" if os.path.exists('./ffmpeg') else "NO ❌"
    return jsonify({
        "status": "online",
        "cookies": has_cookies,
        "ffmpeg": has_ffmpeg,
        "mode": "LONG VIDEO FIXED (Dec 2025)"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        opts = get_ydl_opts()
        opts['quiet'] = False  # show formats
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

            meta = {
                "id": info.get('id'),
                "title": info.get('title', 'Unknown'),
                "duration": info.get('duration'),
                "thumbnail": info.get('thumbnail'),
                "filesize_approx": info.get('filesize_approx'),
            }

            formats = []
            seen_formats = set()

            for f in info.get('formats', []):
                format_id = f.get('format_id')
                if not format_id or format_id in seen_formats:
                    continue

                is_video = f.get('vcodec') != 'none'
                is_audio = f.get('acodec') != 'none'

                if not (is_video or is_audio):
                    continue

                filesize = f.get('filesize') or f.get('filesize_approx') or 0

                if is_video:
                    quality = f"{f.get('height', 0)}p" if f.get('height') else "Video"
                    type_label = "video"
                else:
                    quality = f"{int(f.get('abr') or 0)}kbps"
                    type_label = "audio"

                formats.append({
                    "format_id": format_id,
                    "ext": f.get('ext', 'mp4'),
                    "quality": quality,
                    "filesize": filesize,
                    "type": type_label,
                    "note": f.get('format_note', '')
                })
                seen_formats.add(format_id)

            formats.sort(key=lambda x: (x['type'] == 'video', x['filesize'] or 0), reverse=True)

            return jsonify({"meta": meta, "formats": formats[:20]})  # limit to 20
    except Exception as e:
        logger.exception("Format extract failed")
        return jsonify({"error": "extract_failed", "detail": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401

    url = request.args.get('url')
    format_id = request.args.get('format_id', 'best')

    if not url:
        return jsonify({"error": "missing_url"}), 400

    # Anti-timeout: increase request timeout
    temp_dir = tempfile.mkdtemp()
    
    try:
        logger.info(f"Starting download: {url[:50]}...")
        opts = get_ydl_opts()

        # Specific format override
        if format_id and format_id != 'best':
            opts['format'] = format_id
        else:
            # Safer format for long videos
            opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'

        opts.update({
            'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            'restrictfilenames': True  # safe filenames
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # Verify file exists
        if os.path.exists(filename) and os.path.getsize(filename) > 1024:
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename),
                mimetype='video/mp4'
            )
        else:
            return jsonify({"error": "download_failed_empty"}), 500

    except Exception as e:
        logger.exception("Download failed")
        return jsonify({"error": "download_failed", "detail": str(e)}), 500
    finally:
        # Cleanup after 5 min (async would be better)
        pass

@app.route('/convert_mp3', methods=['GET'])
def convert_mp3():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts()
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            mp3_name = base + ".mp3"

        if os.path.exists(mp3_name):
            return send_file(
                mp3_name,
                as_attachment=True,
                download_name=os.path.basename(mp3_name),
                mimetype='audio/mpeg'
            )
        elif os.path.exists(filename):
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename)
            )
        else:
            return jsonify({"error": "mp3_failed"}), 500

    except Exception as e:
        logger.exception("MP3 convert failed")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists("./ffmpeg"):
        install_ffmpeg()
    app.run(host='0.0.0.0', port=8080, threaded=True)
