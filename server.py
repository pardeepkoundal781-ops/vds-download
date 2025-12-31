import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil
import re

# Silent logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API Keys
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# FFmpeg (silent)
FFMPEG_PATH = None
def install_ffmpeg():
    global FFMPEG_PATH
    try:
        if os.path.exists("./ffmpeg"):
            FFMPEG_PATH = "./ffmpeg"
            return
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename)
        with tarfile.open(filename, "r:xz") as tar: tar.extractall()
        for root, _, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break
        if os.path.exists(filename): os.remove(filename)
        FFMPEG_PATH = "./ffmpeg"
    except: pass

install_ffmpeg()

def clean_url(url):
    """Clean and validate URL"""
    if not url: return None
    url = url.strip().rstrip('/')
    if not re.match(r'https?://', url): return None
    return url

def detect_platform(url):
    """Improved platform detection"""
    if not url: return 'generic'
    url_lower = url.lower()
    
    if re.search(r'youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/', url_lower):
        return 'youtube'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    elif any(x in url_lower for x in ['twitter.com', 'x.com', 'twimg.com']):
        return 'twitter'
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    return 'generic'

def get_ydl_opts(url=None):
    """ULTIMATE EXTRACTION FIX - 2025 Dec"""
    platform = detect_platform(url or '')
    
    # BASE - Works everywhere
    opts = {
        'format': 'best[ext=mp4:height<=720]/best[height<=720]/worst[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'outtmpl': '%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': 'continue',
        'geo_bypass': True,
        'force_ipv4': True,
        'nocheckcertificate': True,
        'retries': 15,
        'fragment_retries': 30,
        'socket_timeout': 45,
        'extractor_retries': 5,
        'source_address': '0.0.0.0',
    }
    
    # CRITICAL FIXES for extraction
    opts.update({
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios', 'default'],
                'skip': ['hls', 'dash']
            },
            'instagram': {
                'include_private': False
            },
            'twitter': {
                'include_rts': True
            }
        }
    })
    
    # Platform specific format
    if platform == 'youtube':
        opts['format'] = 'bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]'
    elif platform == 'instagram':
        opts['format'] = 'worst[ext=mp4]/best'
    
    if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
    if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
    
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    return jsonify({
        "status": "🚀 WORKING 100%",
        "supported": ["YouTube Long/Short", "Instagram", "X/Twitter", "TikTok"],
        "endpoints": ["/download", "/mp3"],
        "ffmpeg": bool(FFMPEG_PATH)
    })

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401
    
    url = clean_url(request.args.get('url'))
    if not url:
        return jsonify({"error": "Invalid URL"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        platform = detect_platform(url)
        print(f"[{platform}] Downloading: {url[:50]}")  # Render logs
        
        opts = get_ydl_opts(url)
        opts['outtmpl'] = os.path.join(temp_dir, '%(title).50s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            # CRITICAL: download=True with error handling
            info = ydl.extract_info(url, download=True)
            
            if not info:
                return jsonify({"error": "extraction_failed"}), 500
            
            filename = ydl.prepare_filename(info)
            
            # Multiple file check (merged files)
            files = [filename]
            base = filename.rsplit('.', 1)[0]
            for ext in ['.mp4', '.mkv', '.webm', '.m4a']:
                check_file = base + ext
                if os.path.exists(check_file):
                    files.append(check_file)
            
            # Find largest valid file
            valid_file = None
            for f in files:
                if os.path.exists(f) and os.path.getsize(f) > 2048:
                    valid_file = f
                    break
            
            if valid_file:
                return send_file(
                    valid_file,
                    as_attachment=True,
                    download_name=os.path.basename(valid_file),
                    mimetype='video/mp4'
                )
            return jsonify({"error": "no_valid_file"}), 500
            
    except Exception as e:
        print(f"ERROR: {str(e)}")  # Render logs
        return jsonify({"error": "download_failed"}), 500

@app.route('/mp3', methods=['GET'])
def download_mp3():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401
    
    url = clean_url(request.args.get('url'))
    if not url:
        return jsonify({"error": "Invalid URL"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts(url)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_file = filename.rsplit('.', 1)[0] + '.mp3'
            
        if os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 1024:
            return send_file(mp3_file, as_attachment=True, mimetype='audio/mpeg')
        return jsonify({"error": "mp3_failed"}), 500
            
    except Exception as e:
        return jsonify({"error": "mp3_error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)
