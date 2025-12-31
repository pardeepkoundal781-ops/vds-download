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

def get_ydl_opts(url=None):
    """
    ULTIMATE FIX: YouTube Long + Instagram (Dec 2025)
    """
    # Detect platform
    is_instagram = 'instagram.com' in (url or '')
    is_youtube = 'youtube.com' in (url or '') or 'youtu.be' in (url or '')

    opts = {
        # Format + merge
        'format': 'best[height<=1080]/bestvideo[height<=1080]+bestaudio/best',
        'merge_output_format': 'mp4',
        'trim_file_name': 50,
        
        # Basic stability
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True,

        # NETWORK CRITICAL (LONG VIDEOS + INSTAGRAM)
        'retries': 20,
        'fragment_retries': 100,
        'continuedl': True,
        'http_chunk_size': 3 * 1024 * 1024,  # 3MB chunks
        'socket_timeout': 45,
        'extractor_retries': 8,
        'sleep_interval': 2,
        'max_sleep_interval': 15,
        'throttled_rate': 50000,

        # PLATFORM SPECIFIC
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'default', 'web_safari'],
                'skip': ['hls', 'dash'],
            },
            'instagram': {
                'private': False,
                'login': None,  # cookies.txt use karega
            }
        },
        'source_address': '0.0.0.0',
    }

    # Instagram specific
    if is_instagram:
        opts.update({
            'format': 'best[height<=1080]/worst',  # Instagram safe format
            'extractor_retries': 15,
            'sleep_interval': 3,
        })

    # YouTube long video specific
    if is_youtube:
        opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'

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
        "mode": "YT LONG + INSTAGRAM FIXED",
        "supported": ["youtube.com", "youtu.be", "instagram.com"]
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        opts = get_ydl_opts(url)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

            meta = {
                "id": info.get('id'),
                "title": info.get('title', 'Unknown'),
                "duration": info.get('duration'),
                "thumbnail": info.get('thumbnail'),
                "uploader": info.get('uploader'),
                "platform": info.get('extractor_key', 'unknown'),
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

            return jsonify({"meta": meta, "formats": formats[:15]})
    except Exception as e:
        logger.exception("Format extract failed")
        return jsonify({"error": "extract_failed", "detail": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401

    url = request.args.get('url')
    format_id = request.args.get('format_id', None)

    if not url:
        return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        logger.info(f"Starting: {url[:50]}...")
        opts = get_ydl_opts(url)

        # Format override
        if format_id:
            opts['format'] = format_id
        else:
            opts['format'] = 'best[height<=1080]/best'

        opts.update({
            'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            'restrictfilenames': True
        })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # Verify file
        if os.path.exists(filename) and os.path.getsize(filename) > 1024:
            platform = info.get('extractor_key', 'video')
            mimetype = 'video/mp4' if platform == 'youtube' else 'video/mp4'
            
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename),
                mimetype=mimetype
            )
        else:
            return jsonify({"error": "empty_file"}), 500

    except Exception as e:
        logger.exception("Download failed")
        return jsonify({"error": "download_failed", "detail": str(e)}), 500

@app.route('/convert_mp3', methods=['GET'])
def convert_mp3():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts(url)
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

        if os.path.exists(mp3_name) and os.path.getsize(mp3_name) > 1024:
            return send_file(
                mp3_name,
                as_attachment=True,
                download_name=os.path.basename(mp3_name),
                mimetype='audio/mpeg'
            )
        elif os.path.exists(filename):
            return send_file(filename, as_attachment=True)
        else:
            return jsonify({"error": "mp3_failed"}), 500

    except Exception as e:
        logger.exception("MP3 failed")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists("./ffmpeg"):
        install_ffmpeg()
    app.run(host='0.0.0.0', port=8080, threaded=True)
