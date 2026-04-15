#!/usr/bin/env python3
"""
Simple HTTP server for the two-team Enhanced Form viewer.
"""

import http.server
import os
import socketserver
import webbrowser
from pathlib import Path

PORT = 8081
HOST = "localhost"

os.chdir(Path(__file__).parent)


class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()


def start_server():
    with socketserver.TCPServer((HOST, PORT), CustomHTTPRequestHandler) as httpd:
        url = f"http://{HOST}:{PORT}/form_viewer.html"
        print(f"Server running at: {url}")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()


if __name__ == "__main__":
    start_server()

