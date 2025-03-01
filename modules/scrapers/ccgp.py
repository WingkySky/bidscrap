"""中国政府采购网爬虫 - 负责抓取中国政府采购网的招投标信息"""
import logging
import time
import random
import json
import asyncio
import aiohttp
from datetime import datetime
from lxml import etree
from urllib.parse import urljoin, parse_qs, urlparse
from typing import List, Dict, Any, Optional, Set, Tuple

from modules.scrapers.base import BaseScraper
from modules.scrapers import register_scraper

logger = logging.getLogger("bidscrap")

@register_scraper
class CCGPScraper(BaseScraper):
    """中国政府采购网爬虫"""
    
    # 网站配置
    BASE_URL = "http://www.ccgp.gov.cn/"
    SEARCH_API = "http://search.ccgp.gov.cn/bxsearch"
    DETAIL_BASE_URL = "http://www.ccgp.gov.cn/oss/download"
    
    # 请求频率限制（降低以避免被封）
    @classmethod
    @property
    def rate_limit(cls) -> float:
        return 0.5  # 每秒最多0.5个请求
    
    # 类别映射
    BID_TYPES = {
        "0": "全部",
        "1": "招标公告",
        "2": "中标公告",
        "3": "更正公告",
        "4": "废标公告",
        "7": "采购意向公告",
        "8": "竞争性谈判公告"
    }
    
    @classmethod
    @property
    def name(cls) -> str:
        """爬虫名称"""
        return "ccgp"
    
    @classmethod
    @property
    def display_name(cls) -> str:
        """显示名称"""
        return "中国政府采购网"
    
    @classmethod
    @property
    def source_url(cls) -> str:
        """数据源URL"""
        return "http://www.ccgp.gov.cn/"
    
    @classmethod
    async def scrape(cls, company: str, start_date: str, end_date: str, 
                   keywords: List[str] = None, 
                   excluded_keywords: List[str] = None,
                   location: str = None,
                   fuzzy_match: bool = True,
                   match_threshold: float = 0.8,
                   max_pages: int = 5,
                   bid_types: List[str] = None,
                   fetch_details: bool = True,
                   **kwargs) -> List[Dict[str, Any]]:
        """抓取中国政府采购网的招投标信息
        
        Args:
            company: 公司名称
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            keywords: 额外关键词列表
            excluded_keywords: 排除关键词列表
            location: 地区限制
            fuzzy_match: 是否启用模糊匹配
            match_threshold: 模糊匹配阈值
            max_pages: 最大抓取页数
            bid_types: 招标类型列表，如["1", "2"]表示招标公告和中标公告
            fetch_details: 是否获取详情页信息
            
        Returns:
            招投标信息列表
        """
        logger.info(f"开始从中国政府采购网抓取 {company} 的招投标信息")
        results = []
        seen_urls = set()  # 用于去重
        
        # 处理搜索关键词
        search_keywords = [company]
        if keywords:
            search_keywords.extend(keywords)
            
        # 处理排除关键词
        exclude_keywords = excluded_keywords or []
        
        # 处理招标类型
        bid_types_param = ",".join(bid_types) if bid_types else "0"
        
        # 处理日期格式
        formatted_start_date = start_date.replace("-", ":")
        formatted_end_date = end_date.replace("-", ":")
        
        try:
            # 创建会话
            async with aiohttp.ClientSession() as session:
                # 最多抓取指定页数
                for page in range(1, max_pages + 1):
                    params = {
                        "searchtype": "1",  # 1表示按照关键词搜索
                        "page_index": str(page),
                        "bidSort": "0",
                        "pinMu": "0",
                        "bidType": bid_types_param,
                        "dbselect": "bidx",
                        "kw": search_keywords[0],  # 搜索关键词
                        "start_time": formatted_start_date,  # 开始时间
                        "end_time": formatted_end_date,  # 结束时间
                        "timeType": "6",  # 时间类型：6表示发布日期
                        "displayZone": "",  # 地区，可选
                    }
                    
                    # 添加地区筛选
                    if location:
                        params["displayZone"] = location
                    
                    # 请求头
                    headers = {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Cache-Control': 'max-age=0',
                        'Connection': 'keep-alive',
                        'Referer': 'http://www.ccgp.gov.cn/',
                        'Upgrade-Insecure-Requests': '1',
                    }
                    
                    # 使用随机User-Agent
                    headers['User-Agent'] = random.choice(cls.USER_AGENT_LIST)
                    
                    try:
                        # 发送请求（使用基类的通用请求方法）
                        status, html_text = await cls.make_request(
                            cls.SEARCH_API, 
                            session=session,
                            params=params,
                            headers=headers
                        )
                        
                        if status != 200 or not html_text:
                            logger.warning(f"请求第 {page} 页失败，状态码: {status}")
                            continue
                        
                        # 解析HTML
                        html = etree.HTML(html_text)
                        
                        # 提取招投标信息
                        items = html.xpath("//div[@class='vT-srch-result-list-bid']//li")
                        
                        if not items:
                            logger.info(f"第 {page} 页没有找到匹配的招投标信息，停止翻页")
                            break
                        
                        for item in items:
                            try:
                                title = "".join(item.xpath(".//a/text()")).strip()
                                url = "".join(item.xpath(".//a/@href")).strip()
                                publish_date = "".join(item.xpath(".//span/text()")).strip()
                                content = "".join(item.xpath(".//p/text()")).strip()
                                
                                # 确保URL是完整的
                                if url and not url.startswith(('http://', 'https://')):
                                    url = urljoin(cls.BASE_URL, url)
                                
                                # 如果URL已经处理过，跳过
                                if url in seen_urls:
                                    continue
                                    
                                seen_urls.add(url)
                                
                                # 检查排除关键词
                                should_exclude = False
                                for exclude_kw in exclude_keywords:
                                    if exclude_kw in title or exclude_kw in content:
                                        should_exclude = True
                                        break
                                        
                                if should_exclude:
                                    continue
                                
                                # 获取正文文本用于匹配分析
                                full_text = f"{title} {content}"
                                
                                # 执行公司匹配分析
                                match_result = cls.is_company_match(
                                    company, 
                                    full_text,
                                    threshold=match_threshold,
                                    context_match=True
                                )
                                
                                # 如果匹配成功或者当前是关键词搜索且包含公司名
                                if match_result["match"] or (search_keywords[0] != company and company in full_text):
                                    # 提取实体信息
                                    entities = cls.extract_entities(full_text)
                                    
                                    # 构建结果
                                    bid_info = {
                                        '公司名称': company,
                                        '标题': title,
                                        '发布日期': publish_date,
                                        '内容摘要': content,
                                        '链接': url,
                                        '数据来源': cls.display_name,
                                        '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        '匹配度': match_result["score"],
                                        '匹配类型': match_result.get("type", "keyword_related") if search_keywords[0] != company else match_result["type"],
                                        '匹配文本': match_result.get("matched_text"),
                                        '地区': entities.get("locations", []),
                                        '金额': entities.get("amounts", []),
                                        '公告类型': entities.get("bid_type", cls.determine_bid_type(title, content))
                                    }
                                    
                                    # 如果是通过关键词匹配到的，记录关键词
                                    if search_keywords[0] != company:
                                        bid_info['关键词'] = search_keywords[0]
                                        
                                    # 获取详情页数据
                                    if fetch_details:
                                        try:
                                            details = await cls.fetch_details(url, session, headers)
                                            if details:
                                                bid_info.update(details)
                                        except Exception as e:
                                            logger.error(f"获取详情页失败: {url}, 错误: {str(e)}")
                                            
                                    results.append(bid_info)
                                    logger.info(f"找到匹配信息: {title} [匹配度: {match_result.get('score', 0):.2f}]")
                                
                            except Exception as e:
                                logger.error(f"解析项目时出错: {str(e)}")
                        
                        # 如果结果少于预期，可能没有更多页面
                        if len(items) < 10:  # 假设每页显示10条
                            break
                        
                        # 页面间暂停，防止被反爬
                        await cls.rate_limit_sleep()
                        
                    except Exception as e:
                        logger.error(f"处理第 {page} 页时出错: {str(e)}")
                        if "Forbidden" in str(e) or "403" in str(e):
                            logger.warning("检测到可能被封禁，暂停抓取")
                            break
                            
                    # 添加随机延迟，避免被识别为爬虫
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    
        except Exception as e:
            logger.error(f"会话创建或请求过程出错: {str(e)}")
        
        logger.info(f"从中国政府采购网共抓取到 {len(results)} 条 {company} 的招投标信息")
        return results
    
    @classmethod
    async def fetch_details(cls, url: str, session, headers) -> Dict[str, Any]:
        """抓取详情页内容获取更多信息"""
        details = {}
        
        # 确保不要频繁请求
        await cls.rate_limit_sleep()
        
        try:
            # 使用通用请求方法获取详情页
            status, html_text = await cls.make_request(
                url, 
                session=session,
                headers=headers
            )
            
            if status != 200 or not html_text:
                logger.warning(f"获取详情页失败，状态码: {status}")
                return details
                
            html = etree.HTML(html_text)
            
            # 提取招标详情信息（根据网站结构调整XPath）
            try:
                # 提取项目编号
                project_id_xpath = [
                    "//div[contains(text(), '项目编号')]/following-sibling::div[1]/text()",
                    "//td[contains(text(), '项目编号')]/following-sibling::td[1]/text()",
                    "//span[contains(text(), '项目编号')]/following-sibling::span[1]/text()",
                    "//p[contains(text(), '项目编号')]/text()"
                ]
                
                for xpath in project_id_xpath:
                    project_id = "".join(html.xpath(xpath)).strip()
                    if project_id:
                        details['项目编号'] = project_id
                        break
                
                # 提取采购人信息
                buyer_xpath = [
                    "//div[contains(text(), '采购人')]/following-sibling::div[1]//text()",
                    "//td[contains(text(), '采购人')]/following-sibling::td[1]//text()",
                    "//span[contains(text(), '采购人')]/following-sibling::span[1]//text()",
                    "//p[contains(text(), '采购人')]/following::text()[1]"
                ]
                
                for xpath in buyer_xpath:
                    buyer = "".join(html.xpath(xpath)).strip()
                    if buyer:
                        details['采购人'] = buyer
                        break
                
                # 提取项目金额
                amount_xpath = [
                    "//div[contains(text(), '金额') or contains(text(), '价格')]/following-sibling::div[1]//text()",
                    "//td[contains(text(), '金额') or contains(text(), '价格')]/following-sibling::td[1]//text()",
                    "//span[contains(text(), '金额') or contains(text(), '价格')]/following-sibling::span[1]//text()"
                ]
                
                for xpath in amount_xpath:
                    amount_text = "".join(html.xpath(xpath)).strip()
                    if amount_text:
                        # 尝试提取金额
                        amount = cls.extract_amount(amount_text)
                        if amount:
                            details['项目金额'] = amount
                            break
                
                # 提取项目联系人
                contact_xpath = [
                    "//div[contains(text(), '联系人')]/following-sibling::div[1]//text()",
                    "//td[contains(text(), '联系人')]/following-sibling::td[1]//text()",
                    "//span[contains(text(), '联系人')]/following-sibling::span[1]//text()"
                ]
                
                for xpath in contact_xpath:
                    contact = "".join(html.xpath(xpath)).strip()
                    if contact:
                        details['联系人'] = contact
                        break
                
                # 提取完整正文
                content_xpath = [
                    "//div[contains(@class, 'vF_detail_content')]//text()",
                    "//div[contains(@class, 'detail_content')]//text()",
                    "//div[contains(@class, 'content')]//text()"
                ]
                
                for xpath in content_xpath:
                    content_parts = html.xpath(xpath)
                    if content_parts:
                        full_content = "".join([part.strip() for part in content_parts if part.strip()])
                        if len(full_content) > 100:  # 确保内容有足够长度
                            details['完整内容'] = full_content
                            break
                
            except Exception as e:
                logger.error(f"解析详情页内容出错: {str(e)}")
            
        except Exception as e:
            logger.error(f"获取详情页出错: {str(e)}")
        
        return details
    
    @classmethod
    def determine_bid_type(cls, title: str, content: str) -> Optional[str]:
        """根据标题和内容判断招标类型"""
        text = f"{title} {content}"
        
        bid_type_keywords = {
            "招标公告": ["招标公告", "招标文件", "投标邀请", "资格预审"],
            "中标公告": ["中标公告", "中标结果", "中标人", "成交结果", "成交公告"],
            "更正公告": ["更正公告", "变更公告", "澄清公告", "修改公告"],
            "废标公告": ["废标公告", "流标公告", "终止公告"],
            "采购意向": ["采购意向", "需求公示"],
            "单一来源": ["单一来源", "单一供应商"],
            "竞争性谈判": ["竞争性谈判"],
            "询价公告": ["询价公告"],
            "竞争性磋商": ["竞争性磋商"]
        }
        
        for bid_type, keywords in bid_type_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return bid_type
        
        return None
    
    @classmethod
    async def rate_limit_sleep(cls):
        """按照频率限制暂停请求"""
        current_time = datetime.now()
        elapsed = (current_time - cls.last_request_time).total_seconds()
        min_interval = 1.0 / cls.rate_limit
        
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed + random.uniform(0.1, 0.5)  # 添加随机抖动
            await asyncio.sleep(sleep_time)
            
        cls.last_request_time = datetime.now()
        cls.request_count += 1 