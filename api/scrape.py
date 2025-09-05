import os
import json
from http.server import BaseHTTPRequestHandler

# Vercel-ൽ നിന്ന് Environment Variable എടുക്കാൻ ശ്രമിക്കുന്നു
API_KEY_FROM_VERCEL = os.environ.get("BROWSERLESS_API_KEY")

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        
        # കീ കിട്ടിയോ ഇല്ലയോ എന്ന വിവരം തിരികെ നൽകുന്നു
        response_data = {
            "message": "This is a test to check the environment variable.",
            "is_key_found": bool(API_KEY_FROM_VERCEL),
            "key_length": len(API_KEY_FROM_VERCEL) if API_KEY_FROM_VERCEL else 0,
            "first_5_chars_of_key": API_KEY_FROM_VERCEL[:5] if API_KEY_FROM_VERCEL else None
        }
        
        self.wfile.write(json.dumps(response_data).encode("utf-8"))
    
    # POST request-നും ഇതേ മറുപടി നൽകാൻ
    def do_POST(self):
        self.do_GET()
