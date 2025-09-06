import os, json, re, requests, m3u8
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

def parse_m3u8_recursive(session, url, visited=None):
    """Recursively parse M3U8 to extract all quality streams."""
    if visited is None:
        visited = set()
    if url in visited:
        return {}
    visited.add(url)

    qualities = {}
    try:
        res = session.get(url, timeout=15)
        res.raise_for_status()
        playlist = m3u8.loads(res.text, uri=url)

        if playlist.is_variant:
            for p in playlist.playlists:
                if p.stream_info and p.stream_info.resolution:
                    width, height = p.stream_info.resolution
                    label = f"{height}p"
                    qualities[label] = p.absolute_uri
                    # Recursively dive into sub-playlists
                    sub_q = parse_m3u8_recursive(session, p.absolute_uri, visited)
                    qualities.update(sub_q)
        else:
            # Not a variant, just return as "auto"
            qualities["auto"] = url
    except Exception as e:
        qualities["fallback"] = url
    return qualities

def extract_links_and_scripts(html):
    """Extract all potential media URLs from HTML and inline scripts."""
    urls = set()

    # 1. Generic video links
    url_matches = re.findall(r'https?://[^\s"\']+\.(m3u8|mp4|mpd|webm)[^\s"\']*', html, re.IGNORECASE)
    urls.update(url_matches)

    # 2. From <script> JSON blobs
    try:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            if not script.string:
                continue
            # extract URLs inside JSON
            found = re.findall(r'https?://[^\s"\']+\.(m3u8|mp4|mpd|webm)[^\s"\']*', script.string, re.IGNORECASE)
            urls.update(found)
    except Exception:
        pass

    return list(urls)

def scrape_with_scraperapi(target_url: str):
    if not SCRAPER_API_KEY:
        raise ValueError("Missing SCRAPER_API_KEY")

    api_url = "https://api.scraperapi.com"
    params = {"api_key": SCRAPER_API_KEY, "url": target_url, "render": "true"}

    r = requests.get(api_url, params=params, timeout=90)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "lxml")

    # Metadata
    def meta(prop, attr="content"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get(attr, "").strip() if tag and tag.has_attr(attr) else ""

    title = meta("og:title") or (soup.title.string.strip() if soup.title else "Untitled")
    desc = meta("og:description") or meta("description")
    thumb = meta("og:image")

    # Collect all media URLs
    media_urls = extract_links_and_scripts(html)

    final_qualities = {}
    session = requests.Session()

    for link in media_urls:
        if link.endswith(".m3u8"):
            q = parse_m3u8_recursive(session, link)
            final_qualities.update(q)
        elif link.endswith(".mp4"):
            label = f"mp4_{len(final_qualities)+1}"
            final_qualities[label] = link
        elif link.endswith(".mpd"):
            final_qualities["dash"] = link
        elif link.endswith(".webm"):
            final_qualities[f"webm_{len(final_qualities)+1}"] = link

    return {
        "title": title,
        "description": desc,
        "thumbnail": thumb,
        "qualities": final_qualities,
        "raw_links": media_urls
    }

class handler(BaseHTTPRequestHandler):
    def _send_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _handle(self, url):
        if not url:
            return self._send_response(400, {"error": "URL is required"})
        try:
            data = scrape_with_scraperapi(url)
            self._send_response(200, data)
        except Exception as e:
            self._send_response(500, {"error": str(e)})

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        self._handle(query.get("url", [None])[0])

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        self._handle(body.get("url"))

# ഈ പുതിയ ഭാഗം താഴെ ചേർക്കുക
if __name__ == "__main__":
    from http.server import HTTPServer
    # Koyeb നൽകുന്ന പോർട്ട് എടുക്കുന്നു, ഇല്ലെങ്കിൽ 8080 ഉപയോഗിക്കുന്നു
    port = int(os.environ.get("PORT", 8080))
    server_address = ("", port)
    httpd = HTTPServer(server_address, handler)
    print(f"Starting server on port {port}...")
    httpd.serve_forever()
