from .base import KST, now_kst, now_utc
from .nvidia import NvidiaCrawler
from .google import GoogleCrawler
from .samsung import SamsungCrawler
from .naver import NaverCrawler
from .toss import TossCrawler
from .upstage import UpstageCrawler
from .generic_greenhouse import GreenhouseCrawler
from .generic_ashby import AshbyCrawler
from .generic_workday import WorkdayCrawler
from .qualcomm import QualcommCrawler
from .amd import AmdCrawler
from .mediatek import MediatekCrawler
from .lg import LgCrawler
from .sk import SkCrawler

PHYSICAL = "피지컬 AI"
ON_DEVICE = "온디바이스 AI"
AI_LAB = "AI 연구소"

# 대시보드 '분야' 필터에 쓰는 회사별 분야 (회사 하나가 여러 분야일 수 있음)
SECTORS = {
    "NVIDIA": [PHYSICAL, ON_DEVICE],
    "Google": [AI_LAB],
    "Samsung": [ON_DEVICE],
    "Anthropic": [AI_LAB],
    "OpenAI": [AI_LAB],
    "Upstage": [AI_LAB],
    "LG AI연구원": [AI_LAB, ON_DEVICE],
    "LG전자": [PHYSICAL, ON_DEVICE],
    "SK하이닉스": [ON_DEVICE],
    "42dot": [PHYSICAL],
    "Boston Dynamics": [PHYSICAL],
    "Figure AI": [PHYSICAL],
    "1X": [PHYSICAL],
    "Physical Intelligence": [PHYSICAL],
    "Skild AI": [PHYSICAL],
    "Agility Robotics": [PHYSICAL],
    "Waymo": [PHYSICAL],
    "Wayve": [PHYSICAL],
    "Motional": [PHYSICAL],
    "Qualcomm": [ON_DEVICE],
    "Intel": [ON_DEVICE],
    "AMD": [ON_DEVICE],
    "MediaTek": [ON_DEVICE],
}


def get_all_crawlers():
    crawlers = {
        "NVIDIA": NvidiaCrawler(),
        "Google": GoogleCrawler(),
        "Samsung": SamsungCrawler(),
        "Naver": NaverCrawler(),
        "Toss": TossCrawler(),
        "Anthropic": GreenhouseCrawler("Anthropic"),
        "OpenAI": AshbyCrawler("OpenAI"),
        "Upstage": UpstageCrawler(),
        # ── 대기업: 피지컬 · 온디바이스 AI ──
        "LG AI연구원": GreenhouseCrawler("LG AI연구원"),
        "LG전자": LgCrawler(),
        "SK하이닉스": SkCrawler(),
        "42dot": AshbyCrawler("42dot"),
        # ── 외국계: 피지컬 AI (전체 공고) ──
        "Boston Dynamics": WorkdayCrawler("Boston Dynamics"),
        "Figure AI": GreenhouseCrawler("Figure AI"),
        "1X": AshbyCrawler("1X"),
        "Physical Intelligence": AshbyCrawler("Physical Intelligence"),
        "Skild AI": GreenhouseCrawler("Skild AI"),
        "Agility Robotics": GreenhouseCrawler("Agility Robotics"),
        "Waymo": GreenhouseCrawler("Waymo"),
        "Wayve": AshbyCrawler("Wayve"),
        "Motional": GreenhouseCrawler("Motional"),
        # ── 외국계: 온디바이스 AI 반도체 (한국 근무지만) ──
        "Qualcomm": QualcommCrawler(),
        "Intel": WorkdayCrawler("Intel"),
        "AMD": AmdCrawler(),
        "MediaTek": MediatekCrawler(),
    }
    for name, c in crawlers.items():
        c.sectors = SECTORS.get(name, [])
    return crawlers
