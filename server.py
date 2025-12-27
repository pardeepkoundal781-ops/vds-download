import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
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

def get_ydl_opts():
    """Returns Anti-Block options for YouTube"""
    # रैंडम यूज़र एजेंट ताकि YouTube को शक न हो
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
    ]
    
    return {
        # 👇 720p लिमिट (ऑडियो फिक्स के लिए)
        'format': 'best[height<=720][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/best',
        
        # 👇 Anti-Block सेटिंग्स
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'geo_bypass': True,
        'source_address': '0.0.0.0',
        'user_agent': random.choice(user_agents),
        
        # Headers भेजें ताकि Request असली लगे
        'http_headers': {
            'Referer': 'https://www.google.com/',
            'Origin': 'https://www.google.com/',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        
        # YouTube Android Client का नाटक करें (यह कम ब्लॉक होता है)
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    cookie_status = "YES ✅" if os.path.exists('cookies.txt') else "NO ❌ (Missing cookies.txt)"
    return jsonify({
        "status": "online",
        "cookies_status": cookie_status,
        "mode": "Anti-Block + Audio Fix (720p)"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request): return jsonify({"error": "Invalid API Key"}), 401
    url = request.args.get('url')
    
    try:
        opts = get_ydl_opts()
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Metadata response
            meta = {
                "id": info.get('id'),
                "title": info.get('title'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "thumbnail": info.get('thumbnail'),
            }
            
            # सिर्फ काम के फॉर्मेट (Audio+Video)
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        formats.append({
                            "format_id": f['format_id'],
                            "ext": f['ext'],
                            "height": f.get('height', 0),
                            "note": "Has Audio ✅"
                        })
            
            # अगर खाली है तो बैकअप
            if not formats:
                formats.append({"format_id": "best", "ext": "mp4", "note": "Best Available"})

            return jsonify({"meta": meta, "formats": formats})

    except Exception as e:
        logger.error(f"Error: {e}")
        # एरर को साफ़ शब्दों में बताएं
        err = str(e)
        if "Sign in" in err: err = "YouTube blocked IP. New cookies.txt required."
        return jsonify({"error": "extract_failed", "detail": err}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
        
        # जबरदस्ती 720p+Audio वाला रूल लगाएं
        if not format_id or format_id == 'best':
             opts['format'] = 'best[height<=720][vcodec!=none][acodec!=none]/best'
        else:
             opts['format'] = format_id

        opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return send_file(filename, as_attachment=True, download_name=os.path.basename(filename))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/convert_mp3', methods=['GET'])
def convert_mp3():
    # ... (Keep MP3 logic same as before or copy from previous working version)
    # Shortened for brevity, ensuring main download fix is prioritized
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        })
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fn = ydl.prepare_filename(info)
            mp3 = os.path.splitext(fn)[0] + ".mp3"
            if not os.path.exists(mp3): mp3 = fn
            return send_file(mp3, as_attachment=True, download_name=os.path.basename(mp3))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
