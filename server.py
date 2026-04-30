"""
로컬 웹 서버 실행
사용법: python server.py
브라우저: http://localhost:8000
"""
import http.server
import socketserver
import webbrowser
import os

PORT = 8000
DIRECTORY = "docs"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        if args and str(args[1]).startswith(('4', '5')):
            super().log_message(format, *args)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    os.makedirs("docs/data", exist_ok=True)
    if not os.path.exists("docs/data/jobs.json"):
        with open("docs/data/jobs.json", "w", encoding="utf-8") as f:
            f.write('{"updated_at": null, "total": 0, "jobs": [], "results": {}}')

    with ReusableTCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"\n🌐 서버 실행 중: {url}")
        print(f"📌 종료하려면 Ctrl+C\n")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 서버 종료")