"""
Site-specific crawl configurations
"""
from typing import Literal
from pydantic import BaseModel, HttpUrl


class SiteConfig(BaseModel):
    """Configuration for a single site"""
    
    name: str
    url: HttpUrl
    strategy: Literal["recursive_crawl", "search_focused", "sitemap", "rss"]
    max_depth: int = 4
    
    # URL patterns to follow
    url_patterns: list[str] = []
    
    # URL patterns to exclude
    exclude_patterns: list[str] = []
    
    # Content selectors (XPath or CSS)
    content_selectors: list[str] = []
    
    # Keywords for relevance filtering
    keywords: list[str] = []
    
    # Document type patterns
    document_patterns: list[str] = []
    
    # Use LLM for URL classification
    llm_filter: bool = True
    
    # Search terms (if strategy is search_focused)
    search_terms: list[str] = []
    
    # Rate limiting (requests per second)
    rate_limit: float = 2.0
    
    # Custom headers
    headers: dict[str, str] = {}
    
    # JavaScript required
    requires_js: bool = False


# Site configurations
SITE_CONFIGS: dict[str, SiteConfig] = {
    "naro": SiteConfig(
        name="NARO (National Agricultural Research Organisation)",
        url="https://naro.go.ug/",
        strategy="recursive_crawl",
        max_depth=4,
        url_patterns=[
            r".*publication.*",
            r".*research.*",
            r".*report.*",
            r".*download.*",
            r".*document.*",
            r".*\.pdf$",
        ],
        exclude_patterns=[
            r".*login.*",
            r".*admin.*",
            r".*wp-admin.*",
            r".*feed.*",
            r".*\?replytocom.*",
        ],
        keywords=[
            "post-harvest",
            "storage",
            "drying",
            "pest",
            "loss",
            "preservation",
            "handling",
            "quality",
            "contamination",
            "aflatoxin",
            "mycotoxin",
        ],
        llm_filter=True,
        rate_limit=2.0,
        requires_js=False,
    ),
    
    "agriculture": SiteConfig(
        name="Ministry of Agriculture (Uganda)",
        url="https://www.agriculture.go.ug/",
        strategy="recursive_crawl",
        max_depth=3,
        url_patterns=[
            r".*policy.*",
            r".*strategy.*",
            r".*plan.*",
            r".*report.*",
            r".*publication.*",
            r".*\.pdf$",
        ],
        exclude_patterns=[
            r".*gallery.*",
            r".*photo.*",
            r".*video.*(?<!\.pdf$)",  # Exclude video pages but not PDFs
        ],
        keywords=[
            "post-harvest",
            "agricultural policy",
            "value chain",
            "storage",
            "marketing",
            "ATAAS",
            "extension",
        ],
        llm_filter=True,
        rate_limit=2.0,
        requires_js=False,
    ),
    
    "extension": SiteConfig(
        name="Agricultural Extension Portal",
        url="https://extension.agriculture.go.ug/",
        strategy="recursive_crawl",
        max_depth=4,
        url_patterns=[
            r".*advisory.*",
            r".*extension.*",
            r".*guide.*",
            r".*manual.*",
            r".*training.*",
            r".*best.*practice.*",
            r".*\.pdf$",
        ],
        content_selectors=[
            "//article",
            "//div[contains(@class, 'content')]",
            "//div[contains(@class, 'post')]",
        ],
        keywords=[
            "post-harvest",
            "advisory",
            "extension",
            "best practice",
            "farmer",
            "storage",
            "handling",
            "quality",
        ],
        llm_filter=True,
        rate_limit=2.0,
        requires_js=True,  # May have dynamic content
    ),
    
    "ubos": SiteConfig(
        name="Uganda Bureau of Statistics",
        url="https://www.ubos.org/",
        strategy="search_focused",
        max_depth=2,
        search_terms=[
            "annual agricultural survey",
            "crop statistics",
            "agricultural production",
            "harvest assessment",
            "food security",
        ],
        document_patterns=[
            r".*Annual.*Agricultural.*Survey.*\.pdf$",
            r".*Crop.*Statistics.*\.pdf$",
            r".*Agricultural.*Production.*\.pdf$",
            r".*Census.*Agriculture.*\.pdf$",
        ],
        url_patterns=[
            r".*publication.*",
            r".*report.*",
            r".*statistical.*",
            r".*\.pdf$",
        ],
        keywords=[
            "agricultural survey",
            "crop production",
            "harvest",
            "statistics",
            "yield",
        ],
        llm_filter=True,
        rate_limit=1.5,  # Be more conservative with govt site
        requires_js=False,
    ),
}


# Topic taxonomy for classification
POST_HARVEST_TOPICS = [
    "storage",
    "drying",
    "pest_management",
    "contamination",
    "quality_control",
    "handling",
    "packaging",
    "transportation",
    "marketing",
    "value_addition",
    "preservation",
    "cold_chain",
    "warehouse_management",
]

# Document types
DOCUMENT_TYPES = [
    "research_paper",
    "extension_guide",
    "policy_document",
    "training_manual",
    "best_practice_guide",
    "report",
    "advisory",
    "video",
    "presentation",
    "case_study",
]

# Target crops (Uganda focus)
TARGET_CROPS = [
    "maize",
    "sorghum",
    "groundnut",
    # "beans",
    # "cassava",
    # "sweet_potato",
    # "rice",
    # "coffee",
    # "banana",
    # "millet",
    # "soybean",
]


def get_site_config(site_name: str) -> SiteConfig:
    """Get configuration for a specific site"""
    if site_name not in SITE_CONFIGS:
        raise ValueError(f"Unknown site: {site_name}")
    return SITE_CONFIGS[site_name]


def get_all_sites() -> list[str]:
    """Get list of all configured sites"""
    return list(SITE_CONFIGS.keys())
