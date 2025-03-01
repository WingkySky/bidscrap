"""爬虫基础架构 - 提供高级爬虫功能与反爬策略"""
from abc import ABC, abstractmethod
import random
import time
import logging
import asyncio
import aiohttp
import json
import re
from typing import List, Dict, Any, Optional, Union, Tuple
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from fake_useragent import UserAgent

logger = logging.getLogger("bidscrap")

class ProxyManager:
    """代理管理器 - 管理和轮换IP代理"""
    
    def __init__(self, proxy_list: List[str] = None, proxy_api_url: str = None, api_key: str = None):
        self.proxies = proxy_list or []
        self.proxy_api_url = proxy_api_url
        self.api_key = api_key
        self.current_index = 0
        self.last_refresh = datetime.now()
        self.banned_proxies = set()
        
    async def get_proxy(self) -> Optional[str]:
        """获取下一个可用代理"""
        # 如果代理列表为空或已经很久没刷新，则刷新代理列表
        if (not self.proxies or 
            (datetime.now() - self.last_refresh > timedelta(hours=1))):
            await self.refresh_proxies()
            
        # 如果代理列表仍为空，返回None
        if not self.proxies:
            return None
            
        # 轮询获取下一个未被封禁的代理
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            if proxy not in self.banned_proxies:
                return proxy
                
        # 如果所有代理都被禁用，返回None
        return None
        
    async def refresh_proxies(self):
        """刷新代理列表"""
        if not self.proxy_api_url:
            logger.warning("未配置代理API，无法刷新代理列表")
            return
            
        try:
            async with aiohttp.ClientSession() as session:
                params = {"apikey": self.api_key} if self.api_key else {}
                async with session.get(self.proxy_api_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            self.proxies = data
                        elif isinstance(data, dict) and "proxies" in data:
                            self.proxies = data["proxies"]
                        else:
                            logger.error(f"代理API返回格式异常: {data}")
                            
                        self.last_refresh = datetime.now()
                        self.banned_proxies.clear()
                        logger.info(f"成功刷新代理列表，获取到 {len(self.proxies)} 个代理")
                    else:
                        logger.error(f"刷新代理失败，状态码: {response.status}")
        except Exception as e:
            logger.error(f"刷新代理出错: {str(e)}")
            
    def mark_proxy_banned(self, proxy: str):
        """标记代理为已封禁"""
        if proxy in self.proxies and proxy not in self.banned_proxies:
            self.banned_proxies.add(proxy)
            logger.warning(f"代理 {proxy} 已被标记为封禁")

class RetryStrategy:
    """重试策略 - 处理请求失败的重试逻辑"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0, 
                 backoff_factor: float = 1.5, jitter: bool = True):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        
    def get_delay(self, retry_count: int) -> float:
        """计算重试延迟时间"""
        delay = self.retry_delay * (self.backoff_factor ** retry_count)
        
        # 添加随机抖动以避免同步请求
        if self.jitter:
            delay = delay * (0.5 + random.random())
            
        return delay
        
    async def sleep(self, retry_count: int):
        """等待指定的重试延迟时间"""
        delay = self.get_delay(retry_count)
        logger.debug(f"重试等待 {delay:.2f} 秒...")
        await asyncio.sleep(delay)

class BaseScraper(ABC):
    """爬虫抽象基类 - 提供通用爬虫功能"""
    
    # 默认设置
    USER_AGENT_LIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    ]
    
    # 静态代理管理器实例
    proxy_manager = ProxyManager()
    
    # 静态重试策略实例
    retry_strategy = RetryStrategy()
    
    # 请求计数和限速
    request_count = 0
    last_request_time = datetime.now()
    
    # 常见的招投标关键词
    BID_KEYWORDS = [
        "招标", "投标", "采购", "中标", "谈判", "询价", "单一来源",
        "竞争性磋商", "竞争性谈判", "竞价", "邀请招标", "公开招标", 
        "资格预审", "项目", "政府采购", "标书"
    ]
    
    @classmethod
    def get_similarity(cls, str1: str, str2: str) -> float:
        """计算两个字符串的相似度"""
        return SequenceMatcher(None, str1, str2).ratio()
    
    @classmethod
    def is_company_match(cls, company: str, text: str, threshold: float = 0.8, 
                         context_match: bool = True) -> Dict[str, Any]:
        """判断公司名称是否匹配文本，支持模糊匹配
        
        Args:
            company: 待匹配的公司名称
            text: 待检查的文本
            threshold: 相似度阈值，默认0.8
            context_match: 是否进行上下文匹配分析
            
        Returns:
            匹配结果，包含是否匹配、匹配类型、匹配度等信息
        """
        result = {
            "match": False,
            "type": None,
            "score": 0.0,
            "matched_text": None
        }
        
        if not text or not company:
            return result
            
        # 1. 精确匹配检查
        if company in text:
            result["match"] = True
            result["type"] = "exact"
            result["score"] = 1.0
            result["matched_text"] = company
            return result
            
        # 2. 处理可能的公司简称（三个字及以上的公司名）
        if len(company) >= 3:
            # 提取公司行业/类型部分（如"科技"、"有限公司"等）
            suffix_patterns = ["有限公司", "有限责任公司", "股份公司", "股份有限公司", "集团", "集团公司", "企业"]
            company_name = company
            
            for pattern in suffix_patterns:
                if pattern in company:
                    company_name = company.replace(pattern, "").strip()
                    # 如果简称在文本中，视为匹配
                    if company_name and len(company_name) >= 2 and company_name in text:
                        result["match"] = True
                        result["type"] = "abbreviation"
                        result["score"] = 0.9
                        result["matched_text"] = company_name
                        return result
        
        # 3. 对文本进行分词，查找可能的部分匹配
        words = re.findall(r'[\w\u4e00-\u9fa5]+', text)
        for word in words:
            similarity = cls.get_similarity(company, word)
            if len(word) >= 2 and similarity > threshold:
                result["match"] = True
                result["type"] = "fuzzy"
                result["score"] = similarity
                result["matched_text"] = word
                
                # 取最高相似度的匹配
                if similarity > result.get("score", 0):
                    result["score"] = similarity
                    result["matched_text"] = word
        
        # 4. 上下文匹配分析（检查公司是否出现在特定上下文中）
        if context_match and not result["match"]:
            # 检查公司是否作为投标方
            bidder_patterns = [
                r'投标人[：:]\s*.*' + re.escape(company),
                r'中标人[：:]\s*.*' + re.escape(company),
                r'供应商[：:]\s*.*' + re.escape(company),
                re.escape(company) + r'\s*为?中标单位',
                re.escape(company) + r'\s*成为?供应商'
            ]
            
            # 检查公司是否作为采购方
            buyer_patterns = [
                r'采购人[：:]\s*.*' + re.escape(company),
                r'招标人[：:]\s*.*' + re.escape(company),
                r'甲方[：:]\s*.*' + re.escape(company),
                re.escape(company) + r'\s*[的]?采购项目'
            ]
            
            for pattern in bidder_patterns + buyer_patterns:
                if re.search(pattern, text):
                    role_type = "bidder" if pattern in bidder_patterns else "buyer"
                    result["match"] = True
                    result["type"] = f"context_{role_type}"
                    result["score"] = 0.85
                    match = re.search(pattern, text)
                    result["matched_text"] = match.group(0) if match else None
                    return result
                    
        return result
    
    @classmethod
    async def get_session(cls, use_proxy: bool = True, 
                         cookies: dict = None, 
                         headers: dict = None) -> aiohttp.ClientSession:
        """创建带有合适配置的请求会话"""
        # 设置基本请求头
        _headers = {
            'User-Agent': random.choice(cls.USER_AGENT_LIST),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 更新请求头
        if headers:
            _headers.update(headers)
        
        # 获取代理
        proxy = None
        if use_proxy:
            proxy = await cls.proxy_manager.get_proxy()
        
        # 创建会话
        session = aiohttp.ClientSession(
            cookies=cookies,
            headers=_headers
        )
        
        session._proxy = proxy  # 保存代理信息，以便后续使用
        return session
    
    @classmethod
    async def make_request(cls, 
                         url: str, 
                         method: str = 'GET', 
                         session: aiohttp.ClientSession = None,
                         params: dict = None,
                         data: dict = None,
                         json_data: dict = None,
                         use_proxy: bool = True,
                         rate_limit: float = 1.0,  # 每秒请求次数限制
                         retry_on_status: List[int] = None,
                         **kwargs) -> Tuple[int, Any]:
        """发送HTTP请求，带有重试、代理和频率限制"""
        if retry_on_status is None:
            retry_on_status = [403, 429, 500, 502, 503, 504]
            
        # 限制请求频率
        current_time = datetime.now()
        elapsed = (current_time - cls.last_request_time).total_seconds()
        min_interval = 1.0 / rate_limit
        
        if elapsed < min_interval:
            delay = min_interval - elapsed
            logger.debug(f"限制请求频率，等待 {delay:.2f} 秒...")
            await asyncio.sleep(delay)
        
        # 创建或使用现有会话
        should_close_session = False
        if session is None:
            session = await cls.get_session(use_proxy=use_proxy)
            should_close_session = True
        
        try:
            proxy = getattr(session, '_proxy', None) if use_proxy else None
            
            # 记录请求
            cls.request_count += 1
            cls.last_request_time = datetime.now()
            
            retry_count = 0
            while retry_count <= cls.retry_strategy.max_retries:
                try:
                    # 随机延迟，模拟人类行为
                    await asyncio.sleep(random.uniform(0.1, 0.5))
                    
                    # 构建请求参数
                    request_kwargs = {
                        'params': params,
                        'data': data,
                        'json': json_data,
                        'proxy': proxy,
                        'timeout': aiohttp.ClientTimeout(total=30),
                        **kwargs
                    }
                    
                    # 发送请求
                    async with getattr(session, method.lower())(url, **request_kwargs) as response:
                        status = response.status
                        
                        # 处理成功响应
                        if 200 <= status < 300:
                            if 'json' in response.content_type.lower():
                                return status, await response.json()
                            else:
                                return status, await response.text()
                        
                        # 处理需要重试的状态码
                        if status in retry_on_status:
                            logger.warning(f"请求 {url} 返回状态码 {status}，准备重试 ({retry_count+1}/{cls.retry_strategy.max_retries})")
                            
                            # 如果是IP被封，标记代理为失效
                            if status in [403, 429] and proxy:
                                cls.proxy_manager.mark_proxy_banned(proxy)
                                # 获取新代理
                                proxy = await cls.proxy_manager.get_proxy()
                                
                            retry_count += 1
                            await cls.retry_strategy.sleep(retry_count)
                            continue
                        
                        # 其他状态码直接返回
                        return status, await response.text()
                        
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"请求 {url} 出错: {str(e)}，准备重试 ({retry_count+1}/{cls.retry_strategy.max_retries})")
                    retry_count += 1
                    
                    # 可能是代理问题，尝试更换代理
                    if proxy:
                        cls.proxy_manager.mark_proxy_banned(proxy)
                        proxy = await cls.proxy_manager.get_proxy()
                        
                    await cls.retry_strategy.sleep(retry_count)
                    continue
                    
            # 所有重试都失败
            logger.error(f"请求 {url} 失败，已达到最大重试次数")
            return 0, None
            
        finally:
            if should_close_session:
                await session.close()
    
    @classmethod
    async def handle_captcha(cls, session, url, image_selector=".captcha-image", 
                            form_selector="form", retry_limit=3):
        """处理验证码（需要OCR服务或人工介入）"""
        logger.warning(f"检测到验证码，尝试处理: {url}")
        
        # 此处仅为示例，实际实现可能需要接入OCR服务或人工验证
        # 可以实现与Tesseract、百度OCR等服务的集成
        
        return False
    
    @classmethod
    async def process_javascript_page(cls, url, js_load_wait=5, 
                                    scrolling=True, scroll_count=3):
        """处理需要JavaScript渲染的页面"""
        try:
            # 这里示范如何与无头浏览器集成
            # 在实际部署中,可能需要创建一个单独的浏览器服务
            
            # 示例代码（实际使用时取消注释）
            """
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.goto(url, wait_until="networkidle")
                
                # 等待JS加载
                await asyncio.sleep(js_load_wait)
                
                # 执行滚动以加载懒加载内容
                if scrolling:
                    for i in range(scroll_count):
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")
                        await asyncio.sleep(1)
                
                # 获取页面内容
                content = await page.content()
                
                await browser.close()
                return content
            """
            
            logger.warning(f"需要处理JavaScript页面: {url}，但当前配置未启用JS渲染")
            return None
            
        except Exception as e:
            logger.error(f"JavaScript页面处理出错: {str(e)}")
            return None
    
    @classmethod
    def extract_amount(cls, text: str) -> Optional[float]:
        """从文本中提取金额信息"""
        # 匹配常见的金额格式，如"1.23亿元"、"456万元"、"7,890元"等
        amount_patterns = [
            r'(\d[\d,]*\.?\d*)\s*亿元',   # 亿元
            r'(\d[\d,]*\.?\d*)\s*万元',   # 万元
            r'(\d[\d,]*\.?\d*)\s*千元',   # 千元
            r'(\d[\d,]*\.?\d*)\s*元',     # 元
            r'(\d[\d,]*\.?\d*)\s*RMB',    # RMB
            r'￥\s*(\d[\d,]*\.?\d*)',      # ￥符号
            r'人民币\s*(\d[\d,]*\.?\d*)'   # 人民币
        ]
        
        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                amount_str = match.group(1).replace(',', '')
                amount = float(amount_str)
                
                # 根据单位转换为元
                if '亿元' in text:
                    amount *= 100_000_000
                elif '万元' in text:
                    amount *= 10_000
                elif '千元' in text:
                    amount *= 1_000
                    
                return amount
                
        return None
        
    @classmethod
    def extract_date(cls, text: str) -> Optional[str]:
        """从文本中提取日期信息"""
        # 匹配常见的日期格式
        date_patterns = [
            r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?)',  # 2023年01月01日
            r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2})',     # 2023-01-01
            r'(\d{2}[年/-]\d{1,2}[月/-]\d{1,2})'      # 23/01/01
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                
                # 标准化日期格式
                date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
                
                # 补全年份（如果是两位数）
                if re.match(r'\d{2}-', date_str):
                    year = int(date_str[:2])
                    current_year = datetime.now().year % 100
                    century = 2000 if year <= current_year else 1900
                    date_str = f"{century + year}{date_str[2:]}"
                    
                return date_str
                
        return None
        
    @classmethod
    def extract_entities(cls, text: str) -> Dict[str, Any]:
        """从文本中提取实体信息"""
        entities = {
            "companies": [],
            "locations": [],
            "dates": [],
            "amounts": [],
            "bid_type": None
        }
        
        # 提取日期
        date = cls.extract_date(text)
        if date:
            entities["dates"].append(date)
            
        # 提取金额
        amount = cls.extract_amount(text)
        if amount:
            entities["amounts"].append(amount)
            
        # 提取招标类型
        bid_types = {
            "公开招标": ["公开招标", "公开"],
            "邀请招标": ["邀请招标", "邀请", "邀标"],
            "竞争性谈判": ["竞争性谈判", "竞谈"],
            "竞争性磋商": ["竞争性磋商", "磋商"],
            "询价采购": ["询价", "询价采购"],
            "单一来源": ["单一来源", "单一"],
            "中标公告": ["中标公告", "中标结果", "中标"],
            "更正公告": ["更正公告", "变更", "澄清"]
        }
        
        for bid_type, keywords in bid_types.items():
            for keyword in keywords:
                if keyword in text:
                    entities["bid_type"] = bid_type
                    break
            if entities["bid_type"]:
                break
                
        # 提取地区（可扩展）
        locations = ["北京", "上海", "广州", "深圳", "天津", "重庆", "杭州", 
                    "南京", "武汉", "成都", "西安", "长沙", "青岛", "厦门"]
        for location in locations:
            if location in text:
                entities["locations"].append(location)
                
        return entities
    
    @classmethod
    @abstractmethod
    async def scrape(cls, company: str, start_date: str, end_date: str, 
                    keywords: List[str] = None, 
                    excluded_keywords: List[str] = None,
                    location: str = None,
                    fuzzy_match: bool = True,
                    match_threshold: float = 0.8,
                    **kwargs) -> List[Dict[str, Any]]:
        """抓取公司的招投标信息"""
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
    
    @classmethod
    @property
    @abstractmethod
    def source_url(cls) -> str:
        """数据源URL"""
        pass
    
    @classmethod
    @property
    def rate_limit(cls) -> float:
        """请求频率限制（每秒请求数）"""
        return 1.0 