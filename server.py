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
    """Returns safe options that work WITHOUT FFmpeg"""
    return {
        # 👇 वीडियो फिक्स: सिर्फ वही फाइल लाओ जिसमें ऑडियो+वीडियो जुड़ा हुआ हो (Max 720p)
        # इससे Facebook/YouTube/Pinterest बिना FFmpeg के चल जाएंगे
        'format': 'best[height<=720][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/best',
        
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'logtostderr': False,
        'geo_bypass': True,
        
        # Fake Browser (YouTube Blocking Fix)
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'source_address': '0.0.0.0', 
    }

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    has_cookies = "YES ✅" if os.path.exists('cookies.txt') else "NO ❌ (Upload cookies.txt for YouTube)"
    return jsonify({
        "status": "online",
        "cookies": has_cookies,
        "mode": "No-FFmpeg Mode (Audio/Video fixed)"
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
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'

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
                # सिर्फ सेफ फॉर्मेट्स दिखाएं (Audio+Video वाले)
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
            
            # अगर सेफ फॉर्मेट न मिले, तो सब दिखा दो (Fallback)
            if not formats:
                 for f in info.get('formats', []):
                    if f.get('vcodec') != 'none':
                        formats.append(f)

            return jsonify({"meta": meta, "formats": formats})

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        # यूजर को साफ एरर दिखाएं
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
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'

        # फोर्स करें कि सेफ फॉर्मेट ही डाउनलोड हो
        if not format_id or format_id == 'best':
             opts['format'] = 'best[height<=720][vcodec!=none][acodec!=none]/best'
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
        if os.path.exists('cookies.txt'): opts['cookiefile'] = 'cookies.txt'

        # 👇 MP3 FIX: FFmpeg के बिना कन्वर्ट मत करो, बस बेस्ट ऑडियो डाउनलोड करो
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            # 'postprocessors' वाली लाइन हटा दी है ताकि एरर न आए
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # फाइल का एक्सटेंशन चेक करें (ज्यादातर m4a या webm होगा)
            base, ext = os.path.splitext(filename)
            
            # ब्राउज़र को .m4a भेजें (यह हर जगह बजता है)
            new_name = base + ".m4a" 
            
            return send_file(filename, as_attachment=True, download_name=os.path.basename(new_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
