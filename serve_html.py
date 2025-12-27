#!/usr/bin/env python3
"""
Simple HTTP server to serve HTML files on port 3000
while the API server runs on port 8080
"""

import http.server
import socketserver
import os
from pathlib import Path

PORT = 3000
DIRECTORY = str(Path(__file__).parent)

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-KEY')
        super().end_headers()

if __name__ == '__main__':
    os.chdir(DIRECTORY)
    handler = MyHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"✓ HTML Server running on https://my-pro-downloader.onrender.com/:{PORT}")
        print(f"✓ Serving files from: {DIRECTORY}")
        print(f"✓ API https://my-pro-downloader.onrender.com/")
        print(f"\nOpen: http://localhost:{PORT}/index.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n✗ Server stopped")
