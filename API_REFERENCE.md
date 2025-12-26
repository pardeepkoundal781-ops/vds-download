# Backend API - Complete Reference & Status Check

## 🚀 Server Status

### API Server (Port 8080)
- **Status**: Running ✓
- **Technology**: Python aiohttp
- **Host**: http://0.0.0.0:8080
- **Local Access**: http://localhost:8080

### HTML Server (Port 3000)
- **Status**: Running ✓
- **Technology**: Python SimpleHTTPServer
- **Purpose**: Serves website files
- **Local Access**: http://localhost:3000

---

## 📋 API Endpoints

### 1. Root Endpoint
```
GET http://localhost:8080/
Headers: X-API-KEY: VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9
```

**Response:**
```json
{
  "ok": true,
  "mode": "python_api"  // or "cli_fallback"
}
```

### 2. Get Video Formats
```
GET http://localhost:8080/formats?url=<VIDEO_URL>&api_key=<API_KEY>
```

**Parameters:**
- `url` (required): Video URL (YouTube, Instagram, TikTok, etc.)
- `api_key` (required): API authentication key

**Response:**
```json
{
  "meta": {
    "id": "dQw4w9WgXcQ",
    "title": "Video Title",
    "uploader": "Channel Name",
    "duration": 212
  },
  "formats": [
    {
      "format_id": "22",
      "ext": "mp4",
      "height": 1080,
      "width": 1920,
      "vcodec": "h264",
      "acodec": "aac",
      "filesize": 52428800,
      "tbr": 2000
    },
    // ... more formats
  ]
}
```

### 3. Download Video
```
GET http://localhost:8080/download?url=<VIDEO_URL>&format_id=<FORMAT_ID>&api_key=<API_KEY>
```

**Parameters:**
- `url` (required): Video URL
- `format_id` (required): Format ID from /formats endpoint
- `api_key` (required): API key

**Response:**
- Binary video file with Content-Disposition header set to trigger browser download

### 4. Convert to MP3
```
GET http://localhost:8080/convert_mp3?url=<VIDEO_URL>&format_id=<FORMAT_ID>&bitrate=192k&api_key=<API_KEY>
```

**Parameters:**
- `url` (required): Video URL
- `format_id` (required): Audio format ID
- `bitrate` (optional): MP3 bitrate (default: 192k)
- `api_key` (required): API key

**Response:**
- Binary MP3 file with Content-Disposition header set to trigger browser download

---

## 🔐 Authentication

**API Key**: `VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9`

**Methods:**
1. Query parameter: `?api_key=<KEY>`
2. Header: `X-API-KEY: <KEY>`

---

## ⚙️ Configuration

### server.py
- **Port**: 8080 (from environment or default)
- **Host**: 0.0.0.0
- **Rate Limit**: 10 requests per 60 seconds per IP
- **Max File Size**: 4 GB

### serve_html.py
- **Port**: 3000
- **CORS**: Enabled for all origins
- **Directory**: Current folder (all HTML files)

---

## 🛠️ Features

### Video Download
- ✓ 1000+ platform support (YouTube, Instagram, TikTok, Facebook, etc.)
- ✓ Multiple quality options (144p to 4K)
- ✓ Audio-only extraction
- ✓ Direct download to client browser

### Audio Conversion
- ✓ Video to MP3 conversion
- ✓ Configurable bitrate (96k, 128k, 192k, 320k, etc.)
- ✓ FFmpeg integration

### Security
- ✓ API Key authentication
- ✓ Rate limiting (10 req/min per IP)
- ✓ File size limits (4 GB max)
- ✓ CORS headers properly configured

### Error Handling
- ✓ Graceful connection error handling
- ✓ Detailed error messages
- ✓ Fallback to CLI if Python module fails

---

## 📊 Dependencies

### Python Packages
- `aiohttp` - Async web framework
- `aiofiles` - Async file I/O
- `yt-dlp` - Video downloading (optional if using CLI fallback)

### System Requirements
- `ffmpeg` - Audio conversion (must be in PATH)
- `yt-dlp` CLI - Video extraction (if Python module not available)

---

## 🚀 Quick Start

### Start Servers
```powershell
# Option 1: Run batch file
f:\100\New folder\htdocs\7l\START_SERVERS.bat

# Option 2: Manual start
cd 'f:\100\New folder\htdocs\7l'
# Terminal 1:
python server.py
# Terminal 2:
python serve_html.py
```

### Access Website
```
http://localhost:3000/index.html
```

### Test API
```powershell
$headers = @{'X-API-KEY' = 'VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9'}
Invoke-WebRequest -Uri "http://localhost:8080/" -Headers $headers | Select-Object StatusCode, Content
```

---

## 🔍 Troubleshooting

### Port Already in Use
```powershell
# Find process using port 8080
netstat -ano | findstr :8080

# Kill process
taskkill /PID <PID> /F
```

### Dependencies Missing
```powershell
pip install aiohttp aiofiles yt-dlp
```

### FFmpeg Not Found
```powershell
# Install FFmpeg
winget install Gyan.FFmpeg
# Or download from: https://ffmpeg.org/download.html
```

### Server Won't Start
```powershell
# Check Python version
python --version

# Verify dependencies
python -c "import aiohttp, aiofiles; print('OK')"

# Run with verbose output
python -u server.py
```

---

## 📝 API Response Codes

| Code | Meaning | Reason |
|------|---------|--------|
| 200 | OK | Request successful |
| 400 | Bad Request | Missing parameters |
| 401 | Unauthorized | Invalid/missing API key |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Internal error |

---

## 🎯 Example Requests

### JavaScript Fetch
```javascript
const API_KEY = 'VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9';
const videoUrl = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ';

// Get formats
fetch(`http://localhost:8080/formats?url=${encodeURIComponent(videoUrl)}&api_key=${API_KEY}`)
  .then(r => r.json())
  .then(data => console.log(data));

// Download video
fetch(`http://localhost:8080/download?url=${encodeURIComponent(videoUrl)}&format_id=22&api_key=${API_KEY}`)
  .then(r => r.blob())
  .then(blob => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'video.mp4';
    a.click();
  });
```

### PowerShell
```powershell
$API_KEY = 'VDS-KEY-9f1a82c7-44b3-49d9-ae92-8d73f5c922ea-78hD92jKQpL0xF3B6vPz9'
$headers = @{'X-API-KEY' = $API_KEY}

# Get formats
Invoke-WebRequest -Uri "http://localhost:8080/formats?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ&api_key=$API_KEY" -Headers $headers | Select-Object StatusCode, Content
```

---

**Last Updated**: 2025-11-27  
**Status**: ✅ Production Ready
