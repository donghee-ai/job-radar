from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict
import requests


class BaseCrawler(ABC):
    def __init__(self, company: str, category: str):
        self.company = company
        self.category = category
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        }

    @abstractmethod
    def fetch_jobs(self) -> List[Dict]:
        pass

    def format_job(self, title: str, url: str, location: str = "",
                   department: str = "", posted_date: str = "") -> Dict:
        return {
            "company": self.company,
            "category": self.category,
            "title": title,
            "url": url,
            "location": location,
            "department": department,
            "posted_date": posted_date,
            "crawled_at": datetime.now().isoformat()
        }

    def safe_request(self, url: str, **kwargs):
        try:
            resp = requests.get(url, headers=self.headers, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  [{self.company}] Request error: {e}")
            return None

    def safe_post(self, url: str, **kwargs):
        try:
            merged_headers = {**self.headers, **kwargs.pop('headers', {})}
            resp = requests.post(url, headers=merged_headers, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  [{self.company}] Request error: {e}")
            return None

    def playwright_fetch(self, url: str, wait_selector: str = "body", timeout: int = 20000) -> str:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout)
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=timeout)
                content = page.content()
                browser.close()
                return content
        except Exception as e:
            print(f"  ⚠️  [{self.company}] Playwright error: {e}")
            return ""