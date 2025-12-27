import os
import logging
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile

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
    """Returns robust yt-dlp options"""
    opts = {
        # 👇 सबसे जरूरी लाइन: यह सिर्फ ऑडियो+वीडियो वाली फाइल ढूंढेगा
        'format': 'best[vcodec!=none][acodec!=none]/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'geo_bypass': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'source_address': '0.0.0.0', 
    }
    
    # Check for cookies
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
        
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    cookie_status = "YES ✅" if os.path.exists('cookies.txt') else "NO ❌"
    return jsonify({
        "status": "online",
        "cookies_found": cookie_status,
        "message": "Server with AUDIO FIX is running!"
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
                # 👇 फिल्टर: सिर्फ वही फॉर्मेट दिखाएं जिसमें Audio (acodec) मौजूद हो
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    formats.append({
                        "format_id": f.get('format_id'),
                        "ext": f.get('ext'),
                        "height": f.get('height'),
                        "filesize": f.get('filesize'),
                        "vcodec": f.get('vcodec'),
                        "acodec": f.get('acodec'),
                        "tbr": f.get('tbr')
                    })

            # अगर कोई कंबाइंड फॉर्मेट न मिले (कभी-कभी होता है), तो बेस्ट वीडियो दिखा दें
            if not formats:
                 for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
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
        return jsonify({"error": "extract_failed", "detail": str(e)}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request): return jsonify({"error": "Invalid Key"}), 401
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    try:
        temp_dir = tempfile.mkdtemp()
        opts = get_ydl_opts()
        
        # अगर फॉर्मेट बेस्ट है तो भी Audio+Video वाला ही उठाएं
        if not format_id or format_id == 'best':
             opts['format'] = 'best[vcodec!=none][acodec!=none]'
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
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Find the actual file created (mp3)
            base, _ = os.path.splitext(filename)
            mp3_name = base + ".mp3"
            
            # Sometimes yt-dlp doesn't rename automatically in code, checking existence
            if not os.path.exists(mp3_name):
                 mp3_name = filename # Fallback

            return send_file(mp3_name, as_attachment=True, download_name=os.path.basename(mp3_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
