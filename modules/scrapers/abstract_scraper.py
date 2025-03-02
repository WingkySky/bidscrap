"""通用爬虫框架 - 提供基于配置的爬虫实现"""
import logging
import asyncio
import random
from typing import Dict, List, Any, Optional, Callable, Type
from lxml import etree
from abc import ABC, abstractmethod
import requests

from modules.scrapers.base import BaseScraper

logger = logging.getLogger("bidscrap")

class AbstractScraper(BaseScraper, ABC):
    """基于配置的通用爬虫实现"""
    
    # 站点配置
    site_config = {
        "base_url": "",          # 网站基础URL
        "search_url": "",        # 搜索API
        "result_selector": "",   # 结果列表选择器
        "page_param": "",        # 页码参数名
        "max_pages": 5,          # 最大页数
        "rate_limit": 1.0,       # 频率限制
        "use_proxy": False,      # 是否使用代理
    }
    
    # 字段提取配置
    field_extractors = {
        "title": {"selector": "", "attribute": "text"},
        "url": {"selector": "", "attribute": "href"},
        "date": {"selector": "", "attribute": "text"},
        "content": {"selector": "", "attribute": "text"},
    }
    
    # 详情页配置
    detail_config = {
        "enabled": False,              # 是否抓取详情
        "fields": {                    # 字段提取配置
            "项目编号": {"selectors": []},
            "采购人": {"selectors": []},
            "金额": {"selectors": [], "processor": "extract_amount"},
        }
    }
    
    @classmethod
    async def scrape(cls, company: str, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """基于配置执行爬取"""
        logger.info(f"开始从{cls.display_name}抓取 {company} 的招投标信息")
        logger.info(f"准备搜索的公司名称: '{company}'")
        
        # 准备搜索参数
        search_params = cls.prepare_search_params(company, start_date, end_date, **kwargs)
        results = []
        seen_urls = set()
        
        try:
            # 创建会话但不使用异步上下文管理器
            session = cls.create_session()
            
            try:
                # 分页爬取
                for page in range(1, cls.site_config.get("max_pages", 5) + 1):
                    # 更新页码
                    if cls.site_config["page_param"]:
                        search_params[cls.site_config["page_param"]] = str(page)
                    
                    # 发送请求
                    status, html_text = await cls.make_request(
                        cls.site_config["search_url"],
                        session=session,
                        params=search_params,
                        headers=cls.prepare_headers()
                    )
                    
                    if status != 200 or not html_text:
                        logger.warning(f"请求第 {page} 页失败，状态码: {status}")
                        continue
                    
                    # 解析结果
                    new_results = await cls.parse_search_results(
                        html_text, company, seen_urls, session, **kwargs
                    )
                    
                    if not new_results:
                        break
                        
                    results.extend(new_results)
                    
                    # 频率控制
                    await cls.rate_limit_sleep()
            finally:
                # 确保关闭会话
                session.close()
        
        except Exception as e:
            logger.error(f"爬取过程出错: {str(e)}")
            
        logger.info(f"从{cls.display_name}共抓取到 {len(results)} 条信息")
        return results
    
    @classmethod
    def prepare_search_params(cls, company: str, start_date: str, end_date: str, **kwargs) -> Dict:
        """准备搜索参数，子类需实现"""
        raise NotImplementedError("子类必须实现prepare_search_params方法")
    
    @classmethod
    def prepare_headers(cls) -> Dict:
        """准备请求头"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'User-Agent': random.choice(cls.USER_AGENT_LIST)
        }
    
    @classmethod
    async def parse_search_results(cls, html_text: str, company: str, 
                                seen_urls: set, session, **kwargs) -> List[Dict[str, Any]]:
        """解析搜索结果"""
        results = []
        html = etree.HTML(html_text)
        
        # 获取结果列表
        items = html.xpath(cls.site_config["result_selector"])
        
        for item in items:
            try:
                # 提取基础字段
                data = {}
                for field_name, config in cls.field_extractors.items():
                    selector = config["selector"]
                    attribute = config.get("attribute", "text")
                    
                    if attribute == "text":
                        value = "".join(item.xpath(f"{selector}/text()")).strip()
                    else:
                        value = "".join(item.xpath(f"{selector}/@{attribute}")).strip()
                    
                    data[field_name] = value
                
                # URL处理
                if "url" in data and data["url"]:
                    if not data["url"].startswith(('http://', 'https://')):
                        data["url"] = cls.normalize_url(data["url"])
                    
                    # 去重
                    if data["url"] in seen_urls:
                        continue
                    seen_urls.add(data["url"])
                
                # 匹配检查
                if cls.should_include_result(data, company, **kwargs):
                    result = cls.build_result_item(data, company)
                    
                    # 获取详情（可选）
                    if cls.detail_config.get("enabled", False) and kwargs.get("fetch_details", True):
                        details = await cls.fetch_details(data["url"], session)
                        if details:
                            result.update(details)
                    
                    results.append(result)
            
            except Exception as e:
                logger.error(f"解析项目时出错: {str(e)}")
        
        return results
    
    @classmethod
    def should_include_result(cls, data: Dict[str, Any], company: str, **kwargs) -> bool:
        """判断结果是否应该被包含"""
        full_text = f"{data.get('title', '')} {data.get('content', '')}"
        
        # 排除关键词
        excluded_keywords = kwargs.get("excluded_keywords", [])
        for kw in excluded_keywords:
            if kw in full_text:
                return False
        
        # 公司匹配
        match_threshold = kwargs.get("match_threshold", 0.8)
        match_result = cls.is_company_match(
            company, 
            full_text,
            threshold=match_threshold
        )
        
        return match_result["match"]
    
    @classmethod
    def build_result_item(cls, data: Dict[str, Any], company: str) -> Dict[str, Any]:
        """构建结果项"""
        # 提取实体信息
        full_text = f"{data.get('title', '')} {data.get('content', '')}"
        entities = cls.extract_entities(full_text)
        
        return {
            '公司名称': company,
            '标题': data.get('title', ''),
            '发布日期': data.get('date', ''),
            '内容摘要': data.get('content', ''),
            '链接': data.get('url', ''),
            '数据来源': cls.display_name,
            '地区': entities.get("locations", []),
            '金额': entities.get("amounts", []),
            '公告类型': entities.get("bid_type")
        }
    
    @classmethod
    async def fetch_details(cls, url: str, session) -> Dict[str, Any]:
        """获取详情页信息"""
        if not cls.detail_config.get("enabled", False):
            return {}
        
        details = {}
        
        try:
            status, html_text = await cls.make_request(url, session=session)
            
            if status != 200 or not html_text:
                return details
                
            html = etree.HTML(html_text)
            
            # 根据配置提取字段
            for field_name, config in cls.detail_config["fields"].items():
                selectors = config.get("selectors", [])
                for selector in selectors:
                    value = "".join(html.xpath(selector)).strip()
                    if value:
                        # 应用处理器（如果有）
                        processor = config.get("processor")
                        if processor and hasattr(cls, processor):
                            value = getattr(cls, processor)(value)
                        
                        details[field_name] = value
                        break
                        
        except Exception as e:
            logger.error(f"获取详情页出错: {str(e)}")
            
        return details
    
    @classmethod
    def normalize_url(cls, url: str) -> str:
        """标准化URL"""
        if cls.site_config.get("base_url"):
            return f"{cls.site_config['base_url'].rstrip('/')}/{url.lstrip('/')}"
        return url 

    @classmethod
    @abstractmethod
    def create_session(cls) -> requests.Session:
        """
        创建并配置一个新的请求会话
        
        Returns:
            requests.Session: 配置好的请求会话对象
        """
        pass 