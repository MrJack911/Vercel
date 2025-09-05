# api/scrape.py (Ultimate Version with Browserless.io)

import os
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

# Get API Keys securely from Vercel Environment Variables
BROWSERLESS_API_KEY = os.environ.get("BROWSERLESS_API_KEY")

def scrape_with_browserless(target_url: str):
    """
    Ultra-powerful scraper using Browserless.io to run Playwright and
    intercept network requests to find video links.
    """
    if not BROWSERLESS_API_KEY:
        raise ValueError("BROWSERLESS_API_KEY is not set in environment variables.")

    api_url = f"https://chrome.browserless.io/scrape?token={BROWSERLESS_API_KEY}"
    
    # We will send a small Playwright script to Browserless to execute
    # This script will listen for network requests ending in .m3u8 or .mp4
    playwright_code = f"""
    async (page, context) => {{
        const video_links = new Set();
        
        // Listen for all network requests
        page.on('request', request => {{
            const url = request.url();
            if (url.endsWith('.m3u8') || url.endsWith('.mp4')) {{
                video_links.add(url);
            }}
        }});

        await page.goto('{target_url}', {{ waitUntil: 'networkidle0', timeout: 90000 }});

        // Also extract metadata from the page
        const title = await page.title();
        
        let thumbnail = await page.evaluate(() => {{
            const ogImage = document.querySelector('meta[property="og:image"]');
            return ogImage ? ogImage.content : null;
        }});

        return {{
            data: {{
                title: title,
                thumbnail: thumbnail || '',
                links: Array.from(video_links)
            }},
            type: 'application/json'
        }};
    }}
    """
    
    headers = {'Content-Type': 'application/javascript'}
    
    # Make the request to Browserless.io API
    response = requests.post(api_url, headers=headers, data=playwright_code, timeout=120)
    response.raise_for_status()
    
    result = response.json()
    scraped_data = result.get('data', {})

    # Organize qualities from the found links
    final_qualities = {{}}
    for i, link in enumerate(scraped_data.get('links', []), 1):
        # Here we are not parsing m3u8 yet to keep it simple, but we can add it later
        if '.m3u8' in link:
            final_qualities[f"m3u8_stream_{i}"] = link
        elif '.mp4' in link:
            final_qualities[f"mp4_video_{i}"] = link

    return {
        "title": scraped_data.get('title', 'Untitled'),
        "thumbnail": scraped_data.get('thumbnail', ''),
        "qualities": final_qualities
    }

class handler(BaseHTTPRequestHandler):
    def _send_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _handle_request(self, url):
        if not url:
            return self._send_response(400, {"error": "URL is required."})
        scraped_data = scrape_with_browserless(url)
        self._send_response(200, scraped_data)

    def do_GET(self):
        try:
            query_components = parse_qs(urlparse(self.path).query)
            page_url = query_components.get("url", [None])[0]
            self._handle_request(page_url)
        except Exception as e:
            self._send_response(500, {"error": f"GET Error: {str(e)}"})

    def do_POST(self):
        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            page_url = payload.get("url")
            self._handle_request(page_url)
        except Exception as e:
            self._send_response(500, {"error": f"POST Error: {str(e)}"})
