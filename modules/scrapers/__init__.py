"""爬虫模块管理 - 负责注册和管理所有爬虫模块"""
import logging
from typing import Dict, Type
from modules.scrapers.base import BaseScraper

logger = logging.getLogger("bidscrap")

# 存储所有已注册的爬虫模块
_scrapers = {}

def register_scraper(scraper_class):
    """注册爬虫模块"""
    _scrapers[scraper_class.name] = scraper_class
    logger.info(f"已注册爬虫模块: {scraper_class.name} ({scraper_class.display_name})")
    return scraper_class

def load_scrapers() -> Dict[str, Type[BaseScraper]]:
    """加载所有爬虫模块"""
    # 导入所有爬虫模块
    from modules.scrapers import ccgp
    # 导入其他爬虫模块
    # from modules.scrapers import bidding
    
    # 返回已注册的爬虫
    return _scrapers 