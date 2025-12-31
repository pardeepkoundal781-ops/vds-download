import os
import logging
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import yt_dlp
import tempfile
import urllib.request
import tarfile
import shutil
import re

app = Flask(__name__)
CORS(app)

# API Key (Render Environment Variable me set karo)
API_KEY = os.environ.get('API_KEY', "VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9")

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
                shutil.move(os.path.join(root, "ffmpeg"), "./ffmpeg")
                os.chmod("./ffmpeg", 0o755)
                break
        if os.path.exists(filename): os.remove(filename)
        FFMPEG_PATH = "./ffmpeg"
    except: pass

install_ffmpeg()

def clean_url(url): return re.sub(r'^\s+|\s+$', '', url) if url else None
def detect_platform(url): 
    if not url: return 'generic'
    url_lower = url.lower()
    if re.search(r'youtube\.com|youtu\.be', url_lower): return 'youtube'
    if 'instagram.com' in url_lower: return 'instagram'
    if 'x.com' in url_lower or 'twitter.com' in url_lower: return 'twitter'
    return 'generic'

def get_ydl_opts(url=None):
    opts = {
        'format': 'best[ext=mp4:height<=720]/best[height<=720]',
        'outtmpl': '%(title).50s.%(ext)s',
        'restrictfilenames': True,
        'quiet': True,
        'ignoreerrors': True,
        'retries': 10,
        'fragment_retries': 20,
    }
    if FFMPEG_PATH: opts['ffmpeg_location'] = FFMPEG_PATH
    return opts

@app.route('/', methods=['GET'])
def home():
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Downloader</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width">
    <style>
        body { font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px; }
        input[type="url"] { width: 100%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 8px; box-sizing: border-box; }
        button { background: #ff4444; color: white; padding: 12px 24px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; width: 100%; margin: 10px 0; }
        button:hover { background: #cc0000; }
        .status { padding: 15px; margin: 10px 0; border-radius: 8px; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .loading { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
    </style>
</head>
<body>
    <h1>🎥 Video Downloader</h1>
    <p>Paste YouTube/Instagram/X video link:</p>
    <input type="url" id="url" placeholder="https://youtube.com/watch?v=..." />
    <br>
    <button onclick="downloadVideo()">📥 Download Video</button>
    <button onclick="downloadMp3()">🎵 Download MP3</button>
    
    <div id="status"></div>
    
    <script>
        function showStatus(msg, type) {
            const status = document.getElementById('status');
            status.innerHTML = msg;
            status.className = 'status ' + type;
        }
        
        async function downloadVideo() {
            const url = document.getElementById('url').value;
            if (!url) return showStatus('Enter URL first!', 'error');
            
            showStatus('Downloading...', 'loading');
            
            try {
                const response = await fetch(`/download?api_key=${API_KEY}&url=${encodeURIComponent(url)}`);
                if (response.ok) {
                    const blob = await response.blob();
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'video.mp4';
                    a.click();
                    showStatus('✅ Downloaded successfully!', 'success');
                } else {
                    const data = await response.json();
                    showStatus('❌ ' + (data.error || 'Download failed'), 'error');
                }
            } catch(e) {
                showStatus('❌ Network error', 'error');
            }
        }
        
        async function downloadMp3() {
            const url = document.getElementById('url').value;
            if (!url) return showStatus('Enter URL first!', 'error');
            
            showStatus('Converting to MP3...', 'loading');
            
            try {
                const response = await fetch(`/mp3?api_key=${API_KEY}&url=${encodeURIComponent(url)}`);
                if (response.ok) {
                    const blob = await response.blob();
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'audio.mp3';
                    a.click();
                    showStatus('✅ MP3 ready!', 'success');
                } else {
                    const data = await response.json();
                    showStatus('❌ ' + (data.error || 'MP3 failed'), 'error');
                }
            } catch(e) {
                showStatus('❌ Network error', 'error');
            }
        }
    </script>
</body>
</html>
    """
    return render_template_string(html)

@app.route('/download', methods=['GET'])
def download_video():
    if request.args.get('api_key') != API_KEY:
        return jsonify({"error": "Invalid Key"}), 401
    
    url = request.args.get('url', '').strip()
    if not url or not re.match(r'https?://', url):
        return jsonify({"error": "Invalid URL"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts(url)
        opts['outtmpl'] = os.path.join(temp_dir, '%(title).50s.%(ext)s')
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if os.path.exists(filename) and os.path.getsize(filename) > 1024:
            return send_file(filename, as_attachment=True, download_name="video.mp4")
        return jsonify({"error": "empty_file"}), 500
            
    except Exception as e:
        return jsonify({"error": "download_failed"}), 500

@app.route('/mp3', methods=['GET'])
def download_mp3():
    if request.args.get('api_key') != API_KEY:
        return jsonify({"error": "Invalid Key"}), 401
    
    url = request.args.get('url', '').strip()
    if not url or not re.match(r'https?://', url):
        return jsonify({"error": "Invalid URL"}), 400

    temp_dir = tempfile.mkdtemp()
    try:
        opts = get_ydl_opts(url)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title).50s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            mp3_file = filename.rsplit('.', 1)[0] + '.mp3'

        if os.path.exists(mp3_file) and os.path.getsize(mp3_file) > 512:
            return send_file(mp3_file, as_attachment=True, download_name="audio.mp3")
        return jsonify({"error": "mp3_failed"}), 500
            
    except Exception:
        return jsonify({"error": "mp3_error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
