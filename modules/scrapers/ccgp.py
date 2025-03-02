"""中国政府采购网爬虫"""
from modules.scrapers.abstract_scraper import AbstractScraper
from modules.scrapers import register_scraper
import requests
from fake_useragent import UserAgent

@register_scraper
class CCGPScraper(AbstractScraper):
    """中国政府采购网爬虫实现"""
    
    # 站点配置
    site_config = {
        "base_url": "http://www.ccgp.gov.cn/",
        "search_url": "http://search.ccgp.gov.cn/bxsearch",
        "result_selector": "//div[@class='vT-srch-result-list-bid']//li",
        "page_param": "page_index",
        "max_pages": 5,
        "rate_limit": 0.5,
    }
    
    # 字段提取配置
    field_extractors = {
        "title": {"selector": ".//a", "attribute": "text"},
        "url": {"selector": ".//a", "attribute": "href"},
        "date": {"selector": ".//span", "attribute": "text"},
        "content": {"selector": ".//p", "attribute": "text"},
    }
    
    # 详情页配置
    detail_config = {
        "enabled": True,
        "fields": {
            "项目编号": {"selectors": [
                "//div[contains(text(), '项目编号')]/following-sibling::div[1]/text()",
                "//td[contains(text(), '项目编号')]/following-sibling::td[1]/text()"
            ]},
            "采购人": {"selectors": [
                "//div[contains(text(), '采购人')]/following-sibling::div[1]//text()",
                "//td[contains(text(), '采购人')]/following-sibling::td[1]//text()"
            ]},
            "项目金额": {"selectors": [
                "//div[contains(text(), '金额')]/following-sibling::div[1]//text()",
                "//td[contains(text(), '金额')]/following-sibling::td[1]//text()"
            ], "processor": "extract_amount"}
        }
    }
    
    @classmethod
    @property
    def name(cls) -> str:
        return "ccgp"
    
    @classmethod
    @property
    def display_name(cls) -> str:
        return "中国政府采购网"
    
    @classmethod
    @property
    def source_url(cls) -> str:
        return "http://www.ccgp.gov.cn/"
    
    @classmethod
    def prepare_search_params(cls, company: str, start_date: str, end_date: str, **kwargs):
        """准备搜索参数"""
        # 处理日期格式
        formatted_start_date = start_date.replace("-", ":")
        formatted_end_date = end_date.replace("-", ":")
        
        # 处理招标类型
        bid_types = kwargs.get("bid_types", ["0"])
        bid_types_param = ",".join(bid_types)
        
        return {
            "searchtype": "1",  # 1表示按照关键词搜索
            "page_index": "1",
            "bidSort": "0",
            "pinMu": "0",
            "bidType": bid_types_param,
            "dbselect": "bidx",
            "kw": company,  # 搜索关键词
            "start_time": formatted_start_date,
            "end_time": formatted_end_date,
            "timeType": "6",  # 时间类型：6表示发布日期
            "displayZone": kwargs.get("location", ""),
        } 
    
    @classmethod
    def create_session(cls) -> requests.Session:
        """
        创建并配置中国政府采购网专用的请求会话
        
        Returns:
            requests.Session: 配置好的请求会话对象
        """
        session = requests.Session()
        # 设置随机User-Agent
        ua = UserAgent()
        session.headers.update({
            'User-Agent': ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'Connection': 'keep-alive',
        })
        return session 