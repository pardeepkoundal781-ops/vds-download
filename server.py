import os
import logging
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp
import tempfile
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# API Keys storage
API_KEYS = {
    "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9": "premium_user"
}

def get_ydl_opts():
    """Returns robust yt-dlp options to bypass bot detection"""
    return {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'geo_bypass': True,
        # Fake a real browser User-Agent
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        # Use Android client for YouTube to avoid some age-gating/bot checks
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        # Bind to IPv4 if possible (helps with some blocks)
        'source_address': '0.0.0.0', 
    }

def verify_api_key(request):
    """Check if the API key is valid"""
    api_key = request.args.get('api_key') or request.headers.get('X-API-KEY')
    if not api_key or api_key not in API_KEYS:
        return False
    return True

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "Pro Video Downloader API",
        "version": "2.0.0"
    })

@app.route('/formats', methods=['GET'])
def get_formats():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid or missing API Key"}), 401

    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    try:
        ydl_opts = get_ydl_opts()
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting info for: {url}")
            info = ydl.extract_info(url, download=False)
            
            # Basic metadata
            meta = {
                "id": info.get('id'),
                "title": info.get('title'),
                "duration": info.get('duration'),
                "uploader": info.get('uploader'),
                "thumbnail": info.get('thumbnail'),
                "webpage_url": info.get('webpage_url')
            }
            
            # Process formats
            formats = []
            for f in info.get('formats', []):
                # Filter out m3u8/manifests if you want direct links only, 
                # but keep them for now as yt-dlp handles them.
                fmt = {
                    "format_id": f.get('format_id'),
                    "ext": f.get('ext'),
                    "height": f.get('height'),
                    "filesize": f.get('filesize'),
                    "vcodec": f.get('vcodec'),
                    "acodec": f.get('acodec'),
                    "tbr": f.get('tbr')
                }
                formats.append(fmt)

            return jsonify({
                "meta": meta,
                "formats": formats
            })

    except Exception as e:
        logger.error(f"Extraction error: {str(e)}")
        # Return a cleaner error message
        error_msg = str(e)
        if "Sign in" in error_msg:
            error_msg = "This video requires sign-in or is age-restricted (Server Blocked)."
        return jsonify({"error": "extract_failed", "detail": error_msg}), 500

@app.route('/download', methods=['GET'])
def download_video():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid API Key"}), 401
        
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    
    if not url or not format_id:
        return jsonify({"error": "Missing url or format_id"}), 400
        
    try:
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        ydl_opts = get_ydl_opts()
        ydl_opts.update({
            'format': format_id,
            'outtmpl': output_template,
        })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename)
            )
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/convert_mp3', methods=['GET'])
def convert_mp3():
    if not verify_api_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get('url')
    
    if not url:
        return jsonify({"error": "Missing url"}), 400
        
    try:
        temp_dir = tempfile.mkdtemp()
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        ydl_opts = get_ydl_opts()
        ydl_opts.update({
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Filename logic for converted files usually changes extension to mp3
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            mp3_filename = base + ".mp3"
            
            return send_file(
                mp3_filename,
                as_attachment=True,
                download_name=os.path.basename(mp3_filename)
            )

    except Exception as e:
        logger.error(f"MP3 error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Standard Flask runner
    app.run(host='0.0.0.0', port=8080)
