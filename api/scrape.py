# api/scrape.py

import json
from http.server import BaseHTTPRequestHandler
import requests
from bs4 import BeautifulSoup
import re

SCRAPER_API_KEY = "YOUR_API_KEY"  # put your ScraperAPI key here

def scrape_with_scraperapi(target_url):
    """Scrape a page using ScraperAPI and extract title, thumbnail, and video qualities"""
    api_url = "https://api.scraperapi.com"
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": target_url,
        "render": "true"  # enable JavaScript rendering
    }

    r = requests.get(api_url, params=params, timeout=30)
    r.raise_for_status()
    html_content = r.text

    soup = BeautifulSoup(html_content, "lxml")

    # Extract title
    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = title_tag.get("content", "Untitled").strip() if title_tag else "Untitled"

    # Extract thumbnail
    thumbnail_tag = soup.find("meta", property="og:image")
    thumbnail = thumbnail_tag.get("content", "") if thumbnail_tag else ""

    # Extract m3u8 links
    m3u8_links = re.findall(r'https?://[^\'"]+\.m3u8[^\'"]*', html_content)

    # Organize qualities (basic version: just return all m3u8 links)
    qualities = {}
    for i, link in enumerate(m3u8_links, 1):
        qualities[f"link_{i}"] = link

    return {
        "title": title,
        "thumbnail": thumbnail,
        "qualities": qualities
    }


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

            data = scrape_with_scraperapi(page_url)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
