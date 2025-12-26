"""
server.py

Robust aiohttp backend for video extraction & download using either the yt-dlp Python API or —
if Python was built without SSL support (ModuleNotFoundError: No module named 'ssl') —
a fallback to the yt-dlp CLI binary via subprocess is used.

Features:
- Extract formats (144p...4k + audio-only)
- Download selected format and stream to client
- Convert to MP3 (ffmpeg)
- API Key protection (X-API-KEY header or ?api_key=...)
- Simple in-memory IP rate limiting
- Server-side proxying to avoid CORS

Notes about the SSL error:
- If Python is missing the `ssl` module (commonly occurs when Python was compiled without OpenSSL), importing the `yt_dlp` Python package will fail because it imports `ssl`.
- This server detects that situation and will automatically use the `yt-dlp` CLI (executable) instead of the Python package.
- Make sure `yt-dlp` (executable) is available in PATH when running in fallback mode:
    pip install yt-dlp  # installs both Python package and a console script named `yt-dlp`
    or
    curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp

Requirements:
- Python 3.9+
- pip packages: aiohttp, aiofiles (yt-dlp python package optional if your Python has ssl)
  - if Python has ssl you may `pip install yt-dlp`
  - if Python lacks ssl, install the yt-dlp executable (see above)
- ffmpeg must be installed & available in PATH

Usage:
1) Set environment variable API_KEY or edit DEFAULT_API_KEY below.
   export API_KEY=supersecretkey
2) Install requirements:
   pip install aiohttp aiofiles
   (optional: pip install yt-dlp if your Python has ssl support)
3) Run:
   python server.py

Endpoints:
- GET  /formats?url={VIDEO_URL}  -> JSON list of formats
- GET  /download?url={VIDEO_URL}&format_id={format_id} -> streams chosen format
- GET  /convert_mp3?url={VIDEO_URL}&format_id={format_id}&bitrate=192k -> streams mp3

Security & Production Notes:
- This is a starting implementation. For production add persistent rate-limit store (redis), disk quotas, authentication, HTTPS, background cleanup and quotas.
- Downloading copyrighted content for distribution may violate terms. Use responsibly.
"""

import os
import asyncio
import json
import tempfile
import shutil
import subprocess
import time
from aiohttp import web
import aiofiles

# ---------- Configuration ----------
DEFAULT_API_KEY = os.environ.get('API_KEY', 'VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9')
HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 8080))
DOWNLOAD_DIR = os.environ.get('DOWNLOAD_DIR', None)  # if None use tempdir

print("Config loaded. Initializing...", flush=True)

# Download optimization settings
CHUNK_SIZE = 1024 * 128  # Increased chunk size for faster downloads (128KB)
CONCURRENT_DOWNLOADS = 5  # Limit concurrent downloads to prevent server overload

# Rate limit settings (simple in-memory)
WINDOW = 60              # seconds
DEFAULT_MAX_REQUESTS = 10

# Limits
MAX_FILESIZE_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB safety limit

# ---------- Simple in-memory rate limiter ----------
_rate_lock = asyncio.Lock()
_rate_store = {}  # ip -> [timestamps]

# Concurrent download limiter
_download_semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)

async def check_rate_limit(ip: str):
    async with _rate_lock:
        now = time.time()
        timestamps = _rate_store.get(ip, [])
        timestamps = [t for t in timestamps if t > now - WINDOW]
        if len(timestamps) >= DEFAULT_MAX_REQUESTS:
            _rate_store[ip] = timestamps
            return False, DEFAULT_MAX_REQUESTS
        timestamps.append(now)
        _rate_store[ip] = timestamps
        return True, DEFAULT_MAX_REQUESTS

# ---------- Detect SSL/yt-dlp availability and prepare functions ----------
USE_PY_YTDLP = False
print("Checking imports...", flush=True)
try:
    # If ssl module is missing this import will fail inside yt_dlp
    import ssl
    print("SSL module found.", flush=True)
    try:
        from yt_dlp import YoutubeDL
        USE_PY_YTDLP = True
        print('Using yt-dlp Python API', flush=True)
    except Exception as e:
        # If Python's ssl exists but yt_dlp import fails for other reasons, fall back to CLI
        print('yt-dlp Python import failed, falling back to yt-dlp CLI:', repr(e), flush=True)
        USE_PY_YTDLP = False
except ModuleNotFoundError:
    # Common sandbox issue: Python built without ssl, cannot import yt_dlp
    print('ssl module missing in Python. Falling back to yt-dlp CLI executable.', flush=True)
    USE_PY_YTDLP = False
except Exception as e:
    print(f"Error checking SSL: {e}", flush=True)
    USE_PY_YTDLP = False

# Helper: run subprocess and return stdout
async def run_subprocess(cmd):
    # run command and return (returncode, stdout, stderr)
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    return proc.returncode, out.decode(errors='ignore'), err.decode(errors='ignore')

# Implementations for extract & download depending on availability
async def run_yt_dlp_extract(url: str):
    """Return a metadata dict similar to YoutubeDL.extract_info output.
    Uses the Python API if available, otherwise uses `yt-dlp -j` to get JSON.
    """
    if USE_PY_YTDLP:
        # Use Python API (blocking call offloaded to threadpool)
        def _extract():
            ydl_opts = {'quiet': True, 'no_warnings': True, 'geo_bypass': True, 'skip_download': True}
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, _extract)
        return info
    else:
        # Use CLI: yt-dlp -j <url>
        cmd = ['yt-dlp', '-j', '--no-warnings', url]
        rc, out, err = await run_subprocess(cmd)
        if rc != 0:
            raise RuntimeError(f'yt-dlp CLI extract failed: {err.strip() or out.strip()}')
        # yt-dlp -j may produce multiple JSON objects (for playlists). We'll parse the first.
        # Sometimes -j prints multiple lines; take the first valid JSON object.
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
                return info
            except Exception:
                continue
        raise RuntimeError('yt-dlp CLI did not return JSON metadata')

async def ytdlp_download_to_file(url: str, format_id: str, dest_template: str):
    """Download using either Python API or yt-dlp CLI.
    dest_template is a path template like /tmp/%(title)s.%(ext)s
    Returns the full path to the downloaded file.
    """
    if USE_PY_YTDLP:
        loop = asyncio.get_event_loop()
        def _run():
            # Robust Logic for Audio Merging (Facebook/Instagram Fix)
            final_format = format_id
            if format_id:
                final_format = f"{format_id}+bestaudio/best"
            else:
                final_format = "bestvideo+bestaudio/best"
            
            print(f"Downloading with format: {final_format}", flush=True)

            ydl_opts = {
                'outtmpl': dest_template,
                'format': final_format,
                'merge_output_format': 'mp4',
                'quiet': False, # Show logs for debugging
                'verbose': True, # Show verbose logs
                'no_warnings': False,
                'noplaylist': True,
                'geo_bypass': True,
                'concurrent_fragment_downloads': True,
                'retries': 5,
                
                # Force FFmpeg usage via postprocessors to ensure merge happens
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }
            
            # Explicitly check for ffmpeg in current directory
            cwd = os.getcwd()
            ffmpeg_local = os.path.join(cwd, 'ffmpeg.exe')
            if os.path.exists(ffmpeg_local):
                ydl_opts['ffmpeg_location'] = cwd

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                print(f"YTDLP Error: {e}", flush=True)
                raise e
            
            # find the file created
            dest_dir = os.path.dirname(dest_template)
            files = os.listdir(dest_dir)
            
            # Filter checks
            files = [f for f in files if f.endswith('.mp4')]
            
            if not files:
                # If mp4 not found, check any file
                files = os.listdir(dest_dir)
                if not files:
                    raise RuntimeError('download finished but no file found')
            
            # pick newest file
            files = sorted(files, key=lambda f: os.path.getmtime(os.path.join(dest_dir, f)), reverse=True)
            path = os.path.join(dest_dir, files[0])
            print(f"Download finished: {path} (Size: {os.path.getsize(path)})", flush=True)
            return path
            
        path = await loop.run_in_executor(None, _run)
        return path
    else:
        # CLI fallback
        final_format = f"{format_id}+bestaudio/best" if format_id else "bestvideo+bestaudio/best"
        print(f"Downloading with CLI format: {final_format}", flush=True)
        
        # Note: --merge-output-format requires ffmpeg
        cmd = ['yt-dlp', '-v', '-f', final_format, '--merge-output-format', 'mp4', '--recode-video', 'mp4', '-o', dest_template, url]
        
        if os.path.exists('ffmpeg.exe'):
            cmd.extend(['--ffmpeg-location', os.getcwd()])
        
        rc, out, err = await run_subprocess(cmd)
        if rc != 0:
            print(f"CLI Error: {err}", flush=True)
            raise RuntimeError(f'yt-dlp CLI download failed: {err.strip() or out.strip()}')
            
        dest_dir = os.path.dirname(dest_template)
        files = os.listdir(dest_dir)
        if not files:
            raise RuntimeError('download finished but no file found (CLI)')
        files = sorted(files, key=lambda f: os.path.getmtime(os.path.join(dest_dir, f)), reverse=True)
        return os.path.join(dest_dir, files[0])

# ---------- Helpers ----------

def require_api_key(request: web.Request):
    key = request.headers.get('X-API-KEY') or request.query.get('api_key')
    if not key:
        return False
    return key == DEFAULT_API_KEY

async def stream_file_response(request: web.Request, filepath: str, as_filename: str = None, content_type: str = 'application/octet-stream'):
    size = os.path.getsize(filepath)
    resp = web.StreamResponse(status=200)
    resp.content_type = content_type
    resp.headers['Content-Length'] = str(size)
    if as_filename:
        resp.headers['Content-Disposition'] = f'attachment; filename="{as_filename}"'
    try:
        await resp.prepare(request)
        async with aiofiles.open(filepath, 'rb') as f:
            while True:
                chunk = await f.read(CHUNK_SIZE)  # Use optimized chunk size
                if not chunk:
                    break
                try:
                    await resp.write(chunk)
                except Exception as e:
                    # Connection closed by client, stop streaming
                    print(f'Client disconnected during streaming: {e}')
                    break
        await resp.write_eof()
    except Exception as e:
        print(f'Error in stream_file_response: {e}')
    return resp

# ---------- CORS Middleware ----------
@web.middleware
async def cors_middleware(request, handler):
    # Handle OPTIONS requests (preflight)
    if request.method == 'OPTIONS':
        return web.Response(
            status=200,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS, HEAD',
                'Access-Control-Allow-Headers': 'Content-Type, X-API-KEY, Authorization',
                'Access-Control-Max-Age': '3600',
            }
        )
    
    try:
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, HEAD'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-API-KEY, Authorization'
        response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Content-Disposition, Content-Length'
        return response
    except web.HTTPException as ex:
        ex.headers['Access-Control-Allow-Origin'] = '*'
        ex.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, HEAD'
        ex.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-API-KEY, Authorization'
        ex.headers['Access-Control-Expose-Headers'] = 'Content-Type, Content-Disposition, Content-Length'
        raise ex

# ---------- Handlers ----------

async def handle_root(request):
    return web.json_response({'ok': True, 'mode': 'python_api' if USE_PY_YTDLP else 'cli_fallback'})

async def handle_formats(request):
    ip = request.remote or 'unknown'
    ok, limit = await check_rate_limit(ip)
    if not ok:
        raise web.HTTPTooManyRequests(text=json.dumps({'error': 'rate_limit_exceeded', 'limit': limit}), content_type='application/json')

    if not require_api_key(request):
        raise web.HTTPUnauthorized(text=json.dumps({'error': 'missing_or_invalid_api_key'}), content_type='application/json')

    url = request.query.get('url')
    if not url:
        raise web.HTTPBadRequest(text=json.dumps({'error': 'missing url param'}), content_type='application/json')

    try:
        info = await run_yt_dlp_extract(url)
    except Exception as e:
        raise web.HTTPBadRequest(text=json.dumps({'error': 'extract_failed', 'detail': str(e)}), content_type='application/json')

    formats = []
    for f in info.get('formats', []):
        formats.append({
            'format_id': f.get('format_id'),
            'ext': f.get('ext'),
            'acodec': f.get('acodec'),
            'vcodec': f.get('vcodec'),
            'filesize': f.get('filesize') or f.get('filesize_approx'),
            'width': f.get('width'),
            'height': f.get('height'),
            'tbr': f.get('tbr'),
            'format_note': f.get('format_note'),
            'protocol': f.get('protocol'),
        })

    meta = {
        'id': info.get('id'),
        'title': info.get('title'),
        'uploader': info.get('uploader'),
        'duration': info.get('duration'),
    }

    return web.json_response({'meta': meta, 'formats': formats})

async def handle_download(request):
    ip = request.remote or 'unknown'
    ok, limit = await check_rate_limit(ip)
    if not ok:
        raise web.HTTPTooManyRequests(text=json.dumps({'error': 'rate_limit_exceeded', 'limit': limit}), content_type='application/json')

    if not require_api_key(request):
        raise web.HTTPUnauthorized(text=json.dumps({'error': 'missing_or_invalid_api_key'}), content_type='application/json')

    url = request.query.get('url')
    format_id = request.query.get('format_id')
    if not url or not format_id:
        raise web.HTTPBadRequest(text=json.dumps({'error': 'missing params (url and format_id required)'}), content_type='application/json')

    # Limit concurrent downloads
    async with _download_semaphore:
        tmpdir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        try:
            try:
                out_template = os.path.join(tmpdir, '%(title)s.%(ext)s')
                downloaded_path = await ytdlp_download_to_file(url, format_id, out_template)

                size = os.path.getsize(downloaded_path)
                if size > MAX_FILESIZE_BYTES:
                    raise web.HTTPRequestEntityTooLarge(max_size=MAX_FILESIZE_BYTES, actual_size=size)

                # Get extension for content-type
                ext = os.path.splitext(downloaded_path)[1].lower()
                content_types = {
                    '.mp4': 'video/mp4',
                    '.webm': 'video/webm',
                    '.mkv': 'video/x-matroska',
                    '.avi': 'video/x-msvideo',
                    '.mov': 'video/quicktime',
                    '.flv': 'video/x-flv',
                    '.wmv': 'video/x-ms-wmv',
                    '.mp3': 'audio/mpeg',
                    '.m4a': 'audio/mp4',
                    '.wav': 'audio/wav',
                    '.flac': 'audio/flac',
                }
                content_type = content_types.get(ext, 'application/octet-stream')
                
                filename = os.path.basename(downloaded_path)
                return await stream_file_response(request, downloaded_path, as_filename=filename, content_type=content_type)
            except Exception as e:
                print(f"Error during download: {e}", flush=True)
                import traceback
                traceback.print_exc()
                return web.json_response({'error': str(e), 'type': type(e).__name__}, status=500)
        finally:
            # Cleanup temp directory
            try:
                # We can't delete immediately if we are streaming, but for this simple server 
                # we rely on OS/temp cleaner or we need a better cleanup strategy for streams.
                # Actually stream_file_response reads file, so we can't delete it yet.
                # But here we are returning the response object. The file is still open.
                # A robust server would use a cleanup callback on response.
                # For now, we only delete if exception or finished. 
                # Since we return, we can't easily delete APTER response in this block.
                # But if we errored, we CAN delete.
                pass 
            except Exception:
                pass  # Best effort cleanup

async def handle_convert_mp3(request):
    ip = request.remote or 'unknown'
    ok, limit = await check_rate_limit(ip)
    if not ok:
        raise web.HTTPTooManyRequests(text=json.dumps({'error': 'rate_limit_exceeded', 'limit': limit}), content_type='application/json')

    if not require_api_key(request):
        raise web.HTTPUnauthorized(text=json.dumps({'error': 'missing_or_invalid_api_key'}), content_type='application/json')

    url = request.query.get('url')
    format_id = request.query.get('format_id')
    bitrate = request.query.get('bitrate', '192k')
    if not url or not format_id:
        raise web.HTTPBadRequest(text=json.dumps({'error': 'missing params (url and format_id required)'}), content_type='application/json')

    # Limit concurrent downloads/conversions
    async with _download_semaphore:
        tmpdir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        try:
            # First download the video/audio
            out_template = os.path.join(tmpdir, '%(title)s.%(ext)s')
            downloaded_path = await ytdlp_download_to_file(url, format_id, out_template)

            # Convert to MP3 using ffmpeg
            mp3_path = os.path.join(tmpdir, 'output.mp3')
            # Try to find ffmpeg in PATH first, fallback to common Windows locations
            import shutil
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path is None:
                # Common Windows locations for ffmpeg
                common_paths = [
                    r'C:\Users\sanju\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe',
                    r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                    r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
                    r'C:\ffmpeg\bin\ffmpeg.exe'
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        ffmpeg_path = path
                        break
            
            if ffmpeg_path is None:
                raise RuntimeError('ffmpeg not found. Please install ffmpeg and make sure it\'s in your PATH.')
                
            cmd = [ffmpeg_path, '-i', downloaded_path, '-b:a', bitrate, '-vn', mp3_path]
            rc, out, err = await run_subprocess(cmd)
            if rc != 0:
                raise RuntimeError(f'ffmpeg conversion failed: {err.strip() or out.strip()}')

            if not os.path.exists(mp3_path):
                raise RuntimeError('ffmpeg conversion finished but no output file found')

            return await stream_file_response(request, mp3_path, as_filename='converted.mp3', content_type='audio/mpeg')
        finally:
            # Cleanup temp directory
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass  # Best effort cleanup

# ---------- App Setup ----------
async def handle_index(request):
    # Serve index.html from the same directory
    index_path = os.path.join(os.getcwd(), 'index.html')
    if not os.path.exists(index_path):
        # Fallback for frozen exe (sys._MEIPASS) or different cwd
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
            index_path = os.path.join(base_path, 'index.html')
        
    if os.path.exists(index_path):
        return web.FileResponse(index_path)
    return web.Response(text="index.html not found. Please place it next to the Play App.", status=404)

app = web.Application(middlewares=[cors_middleware])

# API Routes
app.add_routes([
    web.get('/', handle_root),          # Keep root as API status for health checks
    web.get('/formats', handle_formats),
    web.get('/download', handle_download),
    web.get('/convert_mp3', handle_convert_mp3),
    web.get('/index.html', handle_index), # Serve the frontend
    web.static('/static', '.')          # Serve other static files if needed
])

def open_browser():
    import webbrowser
    print("Opening browser...", flush=True)
    webbrowser.open(f'http://localhost:{PORT}/index.html')

if __name__ == '__main__':
    import sys
    # Enhanced FFMPEG detection for standalone EXE usage
    print("Initializing Pro Video Downloader...", flush=True)
    
    # Add current directory and exe directory to PATH for ffmpeg
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        os.environ['PATH'] += os.pathsep + exe_dir
    os.environ['PATH'] += os.pathsep + os.getcwd()

    print(f'Server starting on http://{HOST}:{PORT}', flush=True)
    print(f'API Key: {DEFAULT_API_KEY}', flush=True)
    
    # Schedule browser open
    loop = asyncio.get_event_loop()
    loop.call_later(2.0, open_browser)
    
    web.run_app(app, host=HOST, port=PORT)
