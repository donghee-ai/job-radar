from .base import KST, now_kst, now_utc
from .nvidia import NvidiaCrawler
from .google import GoogleCrawler
from .samsung import SamsungCrawler
from .naver import NaverCrawler
from .toss import TossCrawler
from .upstage import UpstageCrawler
from .generic_greenhouse import GreenhouseCrawler
from .generic_ashby import AshbyCrawler


def get_all_crawlers():
    return {
        "NVIDIA": NvidiaCrawler(),
        "Google": GoogleCrawler(),
        "Samsung": SamsungCrawler(),
        "Naver": NaverCrawler(),
        "Toss": TossCrawler(),
        "Anthropic": GreenhouseCrawler("Anthropic"),
        "OpenAI": AshbyCrawler("OpenAI"),
        "Upstage": UpstageCrawler(),
    }
