# api/scrape.py

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urljoin, urlparse
import requests
import m3u8
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

def parse_m3u8(session, m3u8_url, base_url):
    """Parses M3U8 files and returns quality links."""
    qualities = {}
    try:
        r = session.get(m3u8_url, timeout=5)
        r.raise_for_status()
        playlist = m3u8.loads(r.text, uri=m3u8_url)
        if playlist.is_variant:
            for p in playlist.playlists:
                if p.stream_info and p.stream_info.resolution:
                    label = f"{p.stream_info.resolution[1]}p"
                    qualities[label] = p.absolute_uri
    except Exception:
        pass
    return qualities

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            page_url = payload.get("url")

            if not page_url:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "URL is required"}).encode())
                return

            with sync_playwright() as p:
                # Optimized launch arguments for serverless environments
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page()
                # Reduced timeout to fit within Vercel's limits
                page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                html_content = page.content()
                browser.close()

            soup = BeautifulSoup(html_content, "lxml")
            
            title_tag = soup.find("meta", property="og:title") or soup.find("title")
            title = title_tag.get("content", "Untitled").strip() if title_tag else "Untitled"
            
            thumbnail_tag = soup.find("meta", property="og:image")
            thumbnail = thumbnail_tag.get("content", "") if thumbnail_tag else ""

            # Simplified and faster M3U8 search
            m3u8_links = set(re.findall(r'["\'](https?://[^\'"]+\.m3u8[^"\']*)["\']', html_content))
            
            found_qualities = {}
            session = requests.Session()
            for link in m3u8_links:
                found_qualities.update(parse_m3u8(session, link, page_url))
            
            data = {
                "title": title,
                "thumbnail": thumbnail,
                "qualities": found_qualities
            }

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
