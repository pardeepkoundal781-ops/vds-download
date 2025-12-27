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
    """Returns robust yt-dlp options with Cookies support"""
    opts = {
        # 👇 सबसे महत्वपूर्ण बदलाव (Most Important Change):
        # यह लाइन yt-dlp को बोलती है: "वही वीडियो लाओ जिसमें Video और Audio दोनों हों"
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
    
    # ✅ Check if cookies.txt exists and use it
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
        
    return opts

def verify_api_key(request):
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    return api_key in API_KEYS

@app.route('/')
def home():
    # Debugging helper to check status
    cookie_exists = os.path.exists('cookies.txt')
    return jsonify({
        "status": "online",
        "cookies_detected": "YES ✅" if cookie_exists else "NO ❌",
        "message": "Server is running with AUDIO FIX applied."
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
                # सिर्फ वही फॉर्मेट दिखाएं जो वीडियो हैं (vcodec != none)
                if f.get('vcodec') != 'none':
                    formats.append({
                        "format_id": f.get('format_id'),
                        "ext": f.get('ext'),
                        "height": f.get('height'),
                        "filesize": f.get('filesize'),
                        "vcodec": f.get('vcodec'),
                        "acodec": f.get('acodec'), # Audio codec info
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
        
        # डाउनलोड के वक्त भी Audio+Video वाला रूल लगाएं
        # अगर यूजर ने स्पेसिफिक फॉर्मेट नहीं चुना, तो बेस्ट कंबाइंड फाइल डाउनलोड करें
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
            mp3_name = os.path.splitext(filename)[0] + ".mp3"
            return send_file(mp3_name, as_attachment=True, download_name=os.path.basename(mp3_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
