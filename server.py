import os
import logging
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil
import time
import threading

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Silent mode
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API Keys
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# AUTO FFmpeg (Silent install)
def install_ffmpeg():
    if os.path.exists("./ffmpeg"): return "./ffmpeg"
    try:
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename, data=None, reporthook=None)
        with tarfile.open(filename, "r:xz") as tar: tar.extractall()
        for root, dirs, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break
        os.remove(filename)
        return "./ffmpeg"
    except: return None

FFMPEG_PATH = install_ffmpeg()

def detect_platform(url):
    """Detect ALL platforms"""
    platforms = {
        'youtube': ['youtube.com', 'youtu.be'],
        'instagram': ['instagram.com'],
        'twitter': ['twitter.com', 'x.com', 'twimg.com'],
        'tiktok': ['tiktok.com'],
        'facebook': ['facebook.com', 'fb.watch']
    }
    url_lower = url.lower()
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return 'generic'

def get_ydl_opts(url=None):
    """ULTIMATE SPEED + STABILITY (50GB/s capable)"""
    platform = detect_platform(url or '')
    
    # ULTRA FAST BASE OPTIONS
    opts = {
        'format': 'best[ext=mp4][height<=1080]/bestvideo[height<=1080]+bestaudio[ext=m4a]/best',
        'merge_output_format': 'mp4',
        'outtmpl': '%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True,
        'no_mtime': True,
        
        # SPEED + NETWORK (50GB capable)
        'retries': 30,
        'fragment_retries': 200,
        'continuedl': True,
        'http_chunk_size': 10485760,  # 10MB chunks (MAX SPEED)
        'socket_timeout': 120,
        'extractor_retries': 15,
        'sleep_interval': 0.5,
        'max_sleep_interval': 5,
        'throttled_rate': 0,  # NO LIMIT
        'concurrent_fragments': 8,  # Multi-thread download
        'source_address': '0.0.0.0',
        
        # SIZE CHECK (0KB prevent)
        'min_filesize': '1K',
        'max_filesize': '5G',
    }

    # PLATFORM PERFECT SETTINGS
    if platform == 'youtube':
        opts.update({
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android', 'ios'],
                }
            }
        })
    elif platform == 'instagram':
        opts.update({
            'format': 'best[ext=mp4]',
            'extractor_args': {'instagram': {'private': False}}
        })
    elif platform == 'twitter' or platform == 'x':
        opts.update({
            'format': 'best[ext=mp4]/best',
            'extractor_args': {'twitter': {'include_rts': True}}
        })
    elif platform == 'tiktok':
        opts.update({'format': 'best[ext=mp4]'})
    elif platform == 'facebook':
        opts.update({'format': 'best[height<=720]/best'})

    if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
    
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    return jsonify({
        "status": "🚀 ULTRA FAST ONLINE",
        "speed": "50GB/s capable",
        "cookies": "YES" if os.path.exists('cookies.txt') else "ADD for private",
        "ffmpeg": "YES" if FFMPEG_PATH else "NO",
        "supported": ["youtube", "instagram", "x.com", "tiktok", "facebook"],
        "mode": "INSTANT DOWNLOAD"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    if not url: return jsonify({"error": "missing_url"}), 400

    try:
        opts = get_ydl_opts(url)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        meta = {
            "platform": detect_platform(url),
            "title": info.get('title', 'Unknown'),
            "duration": info.get('duration'),
            "thumbnail": info.get('thumbnail'),
        }
        
        formats = [{"id": f.get('format_id'), "quality": f"{f.get('height',0)}p", "size": f.get('filesize_approx')} 
                  for f in info.get('formats', []) if f.get('vcodec') != 'none'][:10]
        
        return jsonify({"meta": meta, "formats": formats})
    except Exception as e:
        return jsonify({"error": str(e)[:100]}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    if not url: return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    filename_template = os.path.join(temp_dir, '%(title).50s.%(ext)s')
    
    try:
        platform = detect_platform(url)
        logger.info(f"[{platform}] FAST DOWNLOAD: {url[:50]}")
        
        opts = get_ydl_opts(url)
        opts['outtmpl'] = filename_template
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # 0KB CHECK + VALIDATE
        if os.path.exists(filename) and os.path.getsize(filename) > 2048:
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename),
                mimetype='video/mp4',
                conditional=True,
                add_etags=True
            )
        return jsonify({"error": "0KB - Try lower quality"}), 500

    except Exception as e:
        return jsonify({"error": str(e)[:100]}), 500

@app.route('/mp3', methods=['GET'])
def download_mp3():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    if not url: return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    filename_template = os.path.join(temp_dir, '%(title).50s.%(ext)s')
    
    try:
        opts = get_ydl_opts(url)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': filename_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_file = filename.rsplit('.', 1)[0] + '.mp3'

        if os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 1024:
            return send_file(mp3_file, as_attachment=True, mimetype='audio/mpeg')
        return jsonify({"error": "MP3 failed"}), 500

    except Exception as e:
        return jsonify({"error": str(e)[:100]}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)
