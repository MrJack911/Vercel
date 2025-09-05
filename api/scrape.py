# api/scrape.py

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import re

# Get the API Key securely from Vercel Environment Variables
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

def scrape_with_scraperapi(target_url: str):
    """
    Scrapes a page using ScraperAPI and extracts title, thumbnail, and m3u8 links.
    """
    if not SCRAPER_API_KEY:
        raise ValueError("ScraperAPI Key is not set in environment variables.")

    api_url = "https://api.scraperapi.com"
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": target_url,
        "render": "true"  # Enable JavaScript rendering
    }

    # Make the request to ScraperAPI
    response = requests.get(api_url, params=params, timeout=45)
    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
    html_content = response.text

    soup = BeautifulSoup(html_content, "lxml")

    # --- Data Extraction ---
    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = title_tag.get("content", "Untitled").strip() if title_tag else "Untitled"

    thumbnail_tag = soup.find("meta", property="og:image")
    thumbnail = thumbnail_tag.get("content", "") if thumbnail_tag else ""

    m3u8_links = list(set(re.findall(r'https?://[^\'"]+\.m3u8[^\'"]*', html_content)))

    # Organize qualities (simple version)
    qualities = {f"link_{i}": link for i, link in enumerate(m3u8_links, 1)}

    return {
        "title": title,
        "thumbnail": thumbnail,
        "qualities": qualities
    }

class handler(BaseHTTPRequestHandler):
    def _send_response(self, status_code, data):
        """Helper to send a JSON response."""
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        """Handles GET requests for browser testing."""
        try:
            query_components = parse_qs(urlparse(self.path).query)
            page_url = query_components.get("url", [None])[0]

            if not page_url:
                return self._send_response(400, {"error": "Query parameter 'url' is required."})

            scraped_data = scrape_with_scraperapi(page_url)
            self._send_response(200, scraped_data)

        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def do_POST(self):
        """Handles POST requests from your bot."""
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            page_url = payload.get("url")

            if not page_url:
                return self._send_response(400, {"error": "JSON payload key 'url' is required."})

            scraped_data = scrape_with_scraperapi(page_url)
            self._send_response(200, scraped_data)

        except Exception as e:
            self._send_response(500, {"error": str(e)})
