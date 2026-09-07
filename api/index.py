# MINIMAL TEST - No external imports, just stdlib
# This tests if Vercel Python runtime works at all
from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        resp = json.dumps({
            "status": "ok",
            "message": "Python runtime is working on Vercel",
            "path": self.path
        })
        self.wfile.write(resp.encode())
    
    def do_POST(self):
        self.do_GET()
