import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil
import traceback

# Silent logging for Render
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API Keys
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# FFmpeg auto-install (Render compatible)
FFMPEG_PATH = None
def install_ffmpeg():
    global FFMPEG_PATH
    if os.path.exists("./ffmpeg"):
        FFMPEG_PATH = "./ffmpeg"
        return
    try:
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename)
        with tarfile.open(filename, "r:xz") as tar:
            tar.extractall()
        for root, _, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break
        if os.path.exists(filename):
            os.remove(filename)
        FFMPEG_PATH = "./ffmpeg"
    except:
        pass  # No FFmpeg = audio only

install_ffmpeg()

def safe_extract_info(ydl, url):
    """Safe extraction - prevents NoneType errors"""
    try:
        return ydl.extract_info(url, download=False)
    except:
        return None

def detect_platform(url):
    """Safe platform detection"""
    if not url: return 'generic'
    url_lower = url.lower()
    if any(x in url_lower for x in ['youtube.com', 'youtu.be']): return 'youtube'
    if 'instagram.com' in url_lower: return 'instagram'
    if any(x in url_lower for x in ['twitter.com', 'x.com']): return 'twitter'
    if 'tiktok.com' in url_lower: return 'tiktok'
    return 'generic'

def get_ydl_opts(url=None):
    """Render-safe yt-dlp options"""
    platform = detect_platform(url or '')
    
    opts = {
        'format': 'best[ext=mp4][height<=720]/best[height<=720]/worst[ext=mp4]',
        'merge_output_format': 'mp4',
        'outtmpl': '%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True,
        'retries': 10,
        'fragment_retries': 20,
        'socket_timeout': 30,
        'source_address': '0.0.0.0',
    }
    
    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH
        
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    
    # Platform specific
    if platform == 'youtube':
        opts['format'] = 'bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]'
    elif platform == 'instagram':
        opts['format'] = 'best[ext=mp4]'
    
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    return jsonify({
        "status": "🚀 RENDER DEPLOYED ✅",
        "speed": "FAST",
        "cookies": os.path.exists('cookies.txt'),
        "ffmpeg": bool(FFMPEG_PATH),
        "supported": ["youtube", "instagram", "twitter", "tiktok"],
        "endpoints": ["/download", "/mp3"]
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401
    
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({"error": "missing_url"}), 400

    try:
        opts = get_ydl_opts(url)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = safe_extract_info(ydl, url)
            
            if not info:
                return jsonify({"error": "Cannot extract video info"}), 400
            
            meta = {
                "platform": detect_platform(url),
                "title": info.get('title', 'Unknown') or 'Unknown',
                "duration": info.get('duration'),
            }
            
            formats = []
            if info.get('formats'):
                for f in info['formats'][:10]:
                    if f.get('vcodec') != 'none' and f.get('format_id'):
                        formats.append({
                            "id": f.get('format_id'),
                            "quality": f"{f.get('height', 0)}p",
                            "ext": f.get('ext', 'mp4')
                        })
            
            return jsonify({"meta": meta, "formats": formats})
            
    except Exception as e:
        return jsonify({"error": "format_error"}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401
    
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({"error": "missing_url"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts(url)
        opts['outtmpl'] = os.path.join(temp_dir, '%(title).50s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if not info:
                return jsonify({"error": "download_failed"}), 500
            
            filename = ydl.prepare_filename(info)
            
            # File validation
            if os.path.exists(filename) and os.path.getsize(filename) > 1024:
                return send_file(
                    filename,
                    as_attachment=True,
                    download_name=os.path.basename(filename),
                    mimetype='video/mp4'
                )
            return jsonify({"error": "empty_file"}), 500
            
    except Exception as e:
        return jsonify({"error": "download_error"}), 500

@app.route('/mp3', methods=['GET'])
def download_mp3():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid Key"}), 401
    
    url = request.args.get('url', '').strip()
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
                'preferredquality': '128',
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_file = filename.rsplit('.', 1)[0] + '.mp3'
            
        if os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 512:
            return send_file(mp3_file, as_attachment=True, mimetype='audio/mpeg')
        elif os.path.exists(filename) and os.path.getsize(filename) > 1024:
            return send_file(filename, as_attachment=True)
        return jsonify({"error": "mp3_failed"}), 500
            
    except Exception as e:
        return jsonify({"error": "mp3_error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)
