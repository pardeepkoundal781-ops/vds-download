import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# API Keys
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

# 👇 AUTO FFmpeg INSTALLER FUNCTION
def install_ffmpeg():
    """Download and install FFmpeg automatically if not present"""
    if os.path.exists("./ffmpeg"):
        return "./ffmpeg"
    
    logger.info("⏳ FFmpeg not found. Downloading static build... (This may take 30s)")
    try:
        # Download Linux 64-bit Static Build
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename)
        
        # Extract
        logger.info("📦 Extracting FFmpeg...")
        with tarfile.open(filename, "r:xz") as tar:
            tar.extractall()
            
        # Find and move ffmpeg binary to current folder
        for root, dirs, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                # permission fix
                os.chmod("./ffmpeg", 0o755)
                logger.info("✅ FFmpeg installed successfully!")
                break
                
        # Cleanup
        if os.path.exists(filename):
            os.remove(filename)
            
        return "./ffmpeg"
    except Exception as e:
        logger.error(f"❌ FFmpeg install failed: {e}")
        return None

# Install FFmpeg on startup
FFMPEG_PATH = install_ffmpeg()

def get_ydl_opts():
    """Returns robust yt-dlp options with FFmpeg & Cookies support"""
    opts = {
        # 👇 FIX 1: अब हम 'best' यूज़ कर सकते हैं क्योंकि FFmpeg है (Merge काम करेगा)
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4', # वीडियो को हमेशा mp4 में मर्ज करें
        
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'logtostderr': False,
        'geo_bypass': True,
        
        # 👇 FIX 2: Facebook Error 36 के लिए Force IPv4
        'force_ipv4': True,
        
        # 👇 FIX 3: Fake Browser (YouTube Fix)
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'source_address': '0.0.0.0',
    }
    
    # FFmpeg Path Set करें
    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH

    # Cookies check
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
        
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    has_cookies = "YES ✅" if os.path.exists('cookies.txt') else "NO ❌ (YouTube needs cookies.txt)"
    has_ffmpeg = "YES ✅" if os.path.exists('./ffmpeg') else "NO ❌"
    
    return jsonify({
        "status": "online",
        "cookies": has_cookies,
        "ffmpeg": has_ffmpeg,
        "mode": "Ultimate Mode (FFmpeg Installed)"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    try:
        ydl_opts = get_ydl_opts()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting: {url}")
            info = ydl.extract_info(url, download=False)
            
            meta = {
                "id": info.get('id'),
                "title": info.get('title'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "thumbnail": info.get('thumbnail'),
            }
            
            formats = []
            for f in info.get('formats', []):
                # अब हम सारे फॉर्मेट दिखा सकते हैं क्योंकि FFmpeg मर्ज कर देगा
                formats.append({
                    "format_id": f.get('format_id'),
                    "ext": f.get('ext'),
                    "height": f.get('height'),
                    "filesize": f.get('filesize'),
                    "vcodec": f.get('vcodec'),
                    "acodec": f.get('acodec'),
                    "tbr": f.get('tbr')
                })

            return jsonify({"meta": meta, "formats": formats})

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        err_msg = str(e)
        if "Sign in" in err_msg:
            err_msg = "YouTube blocked IP. Please update cookies.txt."
        return jsonify({"error": "extract_failed", "detail": err_msg}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        
        # अगर फॉर्मेट नहीं दिया, तो बेस्ट क्वालिटी (Merge)
        if not format_id or format_id == 'best':
             opts['format'] = 'bestvideo+bestaudio/best'
        else:
             opts['format'] = format_id

        opts.update({'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s')})
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return send_file(filename, as_attachment=True, download_name=os.path.basename(filename))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/convert_mp3', methods=['GET'])
def convert_mp3():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        
        # 👇 अब MP3 कन्वर्ज़न सही से काम करेगा (FFmpeg के साथ)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # .mp3 फाइल ढूंढें
            base, _ = os.path.splitext(filename)
            mp3_name = base + ".mp3"
            
            return send_file(mp3_name, as_attachment=True, download_name=os.path.basename(mp3_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Ensure FFmpeg is checked on startup
    if not os.path.exists("./ffmpeg"):
        install_ffmpeg()
    app.run(host='0.0.0.0', port=8080)
