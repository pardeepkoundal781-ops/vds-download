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

# 👇 1. AUTO FFmpeg INSTALLER (Audio Fix)
def install_ffmpeg():
    if os.path.exists("./ffmpeg"): return "./ffmpeg"
    try:
        logger.info("⏳ Downloading FFmpeg...")
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        filename = "ffmpeg.tar.xz"
        urllib.request.urlretrieve(url, filename)
        with tarfile.open(filename, "r:xz") as tar: tar.extractall()
        for root, dirs, files in os.walk("."):
            if "ffmpeg" in files:
                src = os.path.join(root, "ffmpeg")
                shutil.move(src, "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break
        if os.path.exists(filename): os.remove(filename)
        return "./ffmpeg"
    except: return None

FFMPEG_PATH = install_ffmpeg()

def get_ydl_opts():
    """Returns options with ALL FIXES applied"""
    return {
        # 👇 2. FORMAT FIX: अगर FFmpeg है तो Best Quality, नहीं तो Safe Mode
        'format': 'bestvideo+bestaudio/best' if FFMPEG_PATH else 'best[height<=720][vcodec!=none][acodec!=none]',
        'merge_output_format': 'mp4',
        
        # 👇 3. ERROR 36 FIX: फाइल का नाम 50 अक्षरों से ज्यादा नहीं होगा
        'trim_file_name': 50,
        
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True, # Network Fix
        
        # 👇 4. YOUTUBE FIX: 'android' की जगह 'ios' (iPhone) क्लाइंट
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web'] 
            }
        },
        
        # Fake iPhone User Agent
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        
        'source_address': '0.0.0.0',
    }

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
        "mode": "Final Fix Mode (iOS + FFmpeg + Trim)"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request): return jsonify({"error": "Invalid API Key"}), 401
    url = request.args.get('url')
    
    try:
        opts = get_ydl_opts()
        if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            meta = {
                "id": info.get('id'),
                "title": info.get('title'),
                "duration": info.get('duration'),
                "thumbnail": info.get('thumbnail'),
            }
            
            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none':
                    formats.append({
                        "format_id": f.get('format_id'),
                        "ext": f.get('ext'),
                        "height": f.get('height'),
                        "filesize": f.get('filesize'),
                    })

            return jsonify({"meta": meta, "formats": formats})
    except Exception as e:
        return jsonify({"error": "extract_failed", "detail": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
        
        if format_id and format_id != 'best':
             opts['format'] = format_id

        # डाउनलोड के वक्त नाम छोटा करें
        opts.update({'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s')})
        
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
        if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
        
        # MP3 लॉजिक: अगर FFmpeg है तो Convert, नहीं तो Direct
        if FFMPEG_PATH:
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}],
            })
        else:
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            base, _ = os.path.splitext(filename)
            mp3_name = base + ".mp3"
            
            # अगर फाइल कनवर्ट नहीं हुई तो रिनेम कर दो
            if not os.path.exists(mp3_name) and os.path.exists(filename):
                os.rename(filename, mp3_name)
                
            return send_file(mp3_name, as_attachment=True, download_name=os.path.basename(mp3_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists("./ffmpeg"): install_ffmpeg()
    app.run(host='0.0.0.0', port=8080)
