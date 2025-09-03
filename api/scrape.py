# api/scrape.py

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urljoin, urlparse
import requests
import m3u8
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

# Helper function to parse M3U8 files
def parse_m3u8(session, m3u8_url):
    qualities = {}
    try:
        r = session.get(m3u8_url, timeout=10)
        r.raise_for_status()
        playlist = m3u8.loads(r.text, uri=m3u8_url)
        if not playlist.is_variant:
            return {}
        for p in sorted(
            playlist.playlists,
            key=lambda x: x.stream_info.resolution[1] if x.stream_info.resolution else 0,
            reverse=True,
        ):
            if p.stream_info.resolution:
                qualities[f"{p.stream_info.resolution[1]}p"] = p.absolute_uri
    except Exception as e:
        print(f"M3U8 parsing failed for {m3u8_url}: {e}")
    return qualities


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            page_url = payload.get("url")

            if not page_url:
                # Error if no URL provided
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "URL is required"}).encode())
                return

            session = requests.Session()
            found_qualities = {}

            # --- Use Playwright to load dynamic pages ---
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(page_url, wait_until="networkidle", timeout=60000)
                html_content = page.content()
                soup = BeautifulSoup(html_content, "lxml")
                browser.close()

            # --- Collect basic info ---
            title_tag = soup.find("meta", property="og:title") or soup.find("title")
            data = {
                "title": title_tag.get("content", "").strip()
                if title_tag
                else urlparse(page_url).path,
                "thumbnail": (soup.find("meta", property="og:image") or {}).get(
                    "content", ""
                ),
                "duration": 0,
                "category": "Uncategorized",
                "qualities": {},
            }

            if duration_tag := soup.find("meta", property="video:duration"):
                if duration_tag.get("content", "").isdigit():
                    data["duration"] = int(duration_tag["content"])

            if category_tag := soup.select_one(
                'a[class*="category"], a[rel="category tag"]'
            ):
                data["category"] = category_tag.text.strip()

            # --- Step 1: Look for JSON video data ---
            scripts = soup.find_all("script")
            json_pattern = re.compile(
                r"(?:sources|videoSources|playlist)\s*[:=]\s*(\[.*?\]|\{.*?\})",
                re.DOTALL | re.IGNORECASE,
            )
            for script in scripts:
                if script.string and not found_qualities:
                    for match in json_pattern.finditer(script.string):
                        try:
                            video_data = json.loads(
                                re.sub(r",\s*([}\]])", r"\1", match.group(1))
                            )
                            items = (
                                video_data
                                if isinstance(video_data, list)
                                else video_data.get("sources", [])
                            )
                            for item in items:
                                if (
                                    isinstance(item, dict)
                                    and "file" in item
                                    and "label" in item
                                ):
                                    found_qualities[item["label"]] = urljoin(
                                        page_url, item["file"]
                                    )
                        except:
                            continue

            # --- Step 2: Look for M3U8 links ---
            if not found_qualities:
                m3u8_links = set(
                    re.findall(
                        r'["\'](https?://[^\'"]+\.m3u8[^"\']*)["\']', html_content
                    )
                )
                for link in m3u8_links:
                    found_qualities.update(parse_m3u8(session, link))

            # --- Step 3: Look for direct MP4/video links ---
            if not found_qualities:
                for tag in soup.find_all(
                    ["video", "source", "a"], href=True
                ) + soup.find_all(["video", "source"], src=True):
                    src = tag.get("src") or tag.get("href")
                    if src and (".mp4" in src or ".m3u8" in src):
                        if any(ad in src.lower() for ad in ["ads", "promo", "advert"]):
                            continue
                        abs_url = urljoin(page_url, src)
                        if ".m3u8" in abs_url:
                            found_qualities.update(parse_m3u8(session, abs_url))
                        else:
                            match = re.search(
                                r"[-_/](\d{3,4})p?[-._/]", abs_url, re.IGNORECASE
                            )
                            label = f"{match.group(1)}p" if match else "video_mp4"
                            if label not in found_qualities:
                                found_qualities[label] = abs_url

            # --- Final cleanup: remove duplicates ---
            final_qualities = {}
            seen_urls = set()
            sorted_items = sorted(
                found_qualities.items(),
                key=lambda item: int(re.sub(r"\D", "", item[0]))
                if re.sub(r"\D", "", item[0])
                else 0,
                reverse=True,
            )
            for label, url in sorted_items:
                if url not in seen_urls:
                    final_qualities[label] = url
                    seen_urls.add(url)

            data["qualities"] = final_qualities

            # --- New feature: Skip videos shorter than 60s ---
            video_duration = data.get("duration", 0)
            if 0 < video_duration < 60:
                print(
                    f"Video '{data.get('title')}' rejected, duration {video_duration}s is less than 60s."
                )
                data["qualities"] = {}  # clear qualities

            # --- Send response ---
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            # Error handling
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": str(e), "type": type(e).__name__}).encode()
            )
