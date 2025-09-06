import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import re
import m3u8

# Get the API Key securely from Vercel Environment Variables
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

def parse_m3u8_qualities(session, playlist_url):
    """Parses an M3U8 playlist to extract different quality streams."""
    qualities = {}
    try:
        response = session.get(playlist_url, timeout=10)
        response.raise_for_status()
        playlist = m3u8.loads(response.text, uri=playlist_url)

        if playlist.is_variant:
            for p in sorted(playlist.playlists, key=lambda x: x.stream_info.resolution[1] if x.stream_info.resolution else 0, reverse=True):
                if p.stream_info and p.stream_info.resolution:
                    label = f"{p.stream_info.resolution[1]}p"
                    if label not in qualities:
                        qualities[label] = p.absolute_uri
    except Exception:
        qualities['video_stream'] = playlist_url
    return qualities

def scrape_with_scraperapi(target_url: str):
    if not SCRAPER_API_KEY:
        raise ValueError("SCRAPER_API_KEY is not set in environment variables.")

    api_url = "https://api.scraperapi.com"
    params = {"api_key": SCRAPER_API_KEY, "url": target_url, "render": "true"}
    
    response = requests.get(api_url, params=params, timeout=90)
    response.raise_for_status()
    html_content = response.text
    soup = BeautifulSoup(html_content, "lxml")

    title_tag = soup.find("meta", property="og:title") or soup.find("title")
    title = title_tag.get("content", "Untitled").strip() if title_tag else "Untitled"

    thumbnail_tag = soup.find("meta", property="og:image")
    thumbnail = thumbnail_tag.get("content", "") if thumbnail_tag else ""

    all_links = re.findall(r'https?://[^\'"]+\.(m3u8|mp4)[^\'"]*', html_content)
    unique_links = sorted(list(set(all_links)), key=lambda x: ".m3u8" not in x)

    final_qualities = {}
    session = requests.Session()

    for link in unique_links:
        if link.endswith('.m3u8'):
            parsed = parse_m3u8_qualities(session, link)
            final_qualities.update(parsed)
            if len(parsed) > 1: break 
        elif link.endswith('.mp4'):
            if not final_qualities:
                 final_qualities[f"video_{len(final_qualities)+1}"] = link

    return {"title": title, "thumbnail": thumbnail, "qualities": final_qualities}

class handler(BaseHTTPRequestHandler):
    def _send_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _handle_request(self, url):
        if not url: return self._send_response(400, {"error": "URL is required."})
        scraped_data = scrape_with_scraperapi(url)
        self._send_response(200, scraped_data)

    def do_GET(self):
        try:
            query_components = parse_qs(urlparse(self.path).query)
            page_url = query_components.get("url", [None])[0]
            self._handle_request(page_url)
        except Exception as e:
            self._send_response(500, {"error": f"{str(e)}"})

    def do_POST(self):
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            page_url = payload.get("url")
            self._handle_request(page_url)
        except Exception as e:
            self._send_response(500, {"error": f"{str(e)}"})
