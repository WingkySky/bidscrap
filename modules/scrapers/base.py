"""爬虫基础类 - 定义所有爬虫模块必须实现的接口"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import re
from difflib import SequenceMatcher

class BaseScraper(ABC):
    """爬虫抽象基类"""
    
    @classmethod
    def get_similarity(cls, str1: str, str2: str) -> float:
        """计算两个字符串的相似度"""
        return SequenceMatcher(None, str1, str2).ratio()
    
    @classmethod
    def is_company_match(cls, company: str, text: str, threshold: float = 0.8) -> bool:
        """判断公司名称是否匹配文本，支持模糊匹配
        
        Args:
            company: 待匹配的公司名称
            text: 待检查的文本
            threshold: 相似度阈值，默认0.8
            
        Returns:
            是否匹配
        """
        # 1. 精确匹配检查
        if company in text:
            return True
            
        # 2. 处理可能的公司简称（三个字及以上的公司名）
        if len(company) >= 3:
            # 提取公司行业/类型部分（如"科技"、"有限公司"等）
            suffix_patterns = ["有限公司", "有限责任公司", "股份公司", "集团", "企业"]
            company_name = company
            for pattern in suffix_patterns:
                if pattern in company:
                    company_name = company.replace(pattern, "").strip()
                    # 如果简称在文本中，视为匹配
                    if company_name and len(company_name) >= 2 and company_name in text:
                        return True
        
        # 3. 对文本进行分词，查找可能的部分匹配
        words = re.findall(r'[\w]+', text)
        for word in words:
            if len(word) >= 2 and cls.get_similarity(company, word) > threshold:
                return True
                
        return False
    
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