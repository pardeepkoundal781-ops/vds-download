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

# 👇 1. AUTO FFmpeg INSTALLER
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
    except Exception as e:
        logger.error(f"FFmpeg install error: {e}")
        return None

FFMPEG_PATH = install_ffmpeg()

def get_ydl_opts():
    """Returns robust options for all platforms"""
    return {
        'format': 'bestvideo+bestaudio/best', 
        'merge_output_format': 'mp4',
        'trim_file_name': 50,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'force_ipv4': True,
        
        # 👇 YOUTUBE FIX: Use 'TV' Client (No Blocks)
        'extractor_args': {
            'youtube': {
                'player_client': ['tv'] 
            }
        },
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
        "mode": "Smart TV Mode (YouTube Fixed)"
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
            seen_formats = set()
            
            for f in info.get('formats', []):
                format_id = f.get('format_id')
                if format_id in seen_formats: continue
                
                is_video = f.get('vcodec') != 'none'
                is_audio = f.get('acodec') != 'none'
                
                if is_video or is_audio:
                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    
                    if is_video:
                        quality = f"{f.get('height')}p" if f.get('height') else "Video"
                        type_label = "video"
                    else:
                        quality = f"{int(f.get('abr') or 0)}kbps"
                        type_label = "audio"

                    formats.append({
                        "format_id": format_id,
                        "ext": f.get('ext'),
                        "quality": quality,
                        "filesize": filesize,
                        "type": type_label,
                        "note": f.get('format_note')
                    })
                    seen_formats.add(format_id)

            formats.sort(key=lambda x: (x['type'] == 'video', x['filesize']), reverse=True)

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
            
            if not os.path.exists(mp3_name) and os.path.exists(filename):
                os.rename(filename, mp3_name)
                
            return send_file(mp3_name, as_attachment=True, download_name=os.path.basename(mp3_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not os.path.exists("./ffmpeg"): install_ffmpeg()
    app.run(host='0.0.0.0', port=8080)
