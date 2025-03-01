"""爬虫基础类 - 定义所有爬虫模块必须实现的接口"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseScraper(ABC):
    """爬虫抽象基类"""
    
    @classmethod
    @abstractmethod
    async def scrape(cls, company: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        抓取公司的招投标信息
        :param company: 公司名称
        :param start_date: 开始日期 (格式: YYYY:MM:DD)
        :param end_date: 结束日期 (格式: YYYY:MM:DD)
        :return: 招投标信息列表
        """
        pass
    
    @classmethod
    @property
    @abstractmethod
    def name(cls) -> str:
        """爬虫名称"""
        pass
    
    @classmethod
    @property
    @abstractmethod
    def display_name(cls) -> str:
        """显示名称"""
        pass 