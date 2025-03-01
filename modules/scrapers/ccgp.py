"""中国政府采购网爬虫 - 负责抓取中国政府采购网的招投标信息"""
import logging
import time
import random
import aiohttp
import asyncio
from datetime import datetime
from lxml import etree
from urllib.parse import urljoin
from typing import List, Dict, Any, Optional

from modules.scrapers.base import BaseScraper
from modules.scrapers import register_scraper

logger = logging.getLogger("bidscrap")

@register_scraper
class CCGPScraper(BaseScraper):
    """中国政府采购网爬虫"""
    
    # 网站配置
    BASE_URL = "http://www.ccgp.gov.cn/"
    SEARCH_API = "http://search.ccgp.gov.cn/bxsearch"
    
    @classmethod
    async def scrape(cls, company: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """抓取中国政府采购网的招投标信息"""
        logger.info(f"开始从中国政府采购网抓取 {company} 的招投标信息")
        results = []
        
        # 搜索参数
        params = {
            "searchtype": "1",  # 1表示招标公告
            "page_index": "1",
            "bidSort": "0",
            "buyerName": "",
            "projectId": "",
            "pinMu": "0",
            "bidType": "0",
            "dbselect": "bidx",
            "kw": company,  # 公司名称关键词
            "start_time": start_date,  # 开始时间
            "end_time": end_date,  # 结束时间
            "timeType": "6",  # 时间类型
            "displayZone": "0",
        }
        
        # 请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # 最多抓取5页
                for page in range(1, 6):
                    params["page_index"] = str(page)
                    
                    try:
                        # 发送请求
                        async with session.get(
                            cls.SEARCH_API, 
                            params=params, 
                            headers=headers,
                            timeout=10
                        ) as response:
                            if response.status != 200:
                                logger.warning(f"请求失败，状态码: {response.status}")
                                continue
                            
                            # 解析HTML
                            html_text = await response.text()
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
                                    
                                    # 使用改进的模糊匹配方法判断是否相关
                                    if (cls.is_company_match(company, title) or 
                                        cls.is_company_match(company, content)):
                                        results.append({
                                            '公司名称': company,
                                            '标题': title,
                                            '发布日期': publish_date,
                                            '内容摘要': content,
                                            '链接': url,
                                            '数据来源': cls.display_name,
                                            '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                            '匹配度': 'high' if company in title or company in content else 'medium'
                                        })
                                        logger.info(f"找到匹配信息: {title}")
                                        
                                        # 可选：抓取详情页获取更多信息
                                        # details = await cls.fetch_details(url, session, headers)
                                        # if details:
                                        #     results[-1].update(details)
                                except Exception as e:
                                    logger.error(f"解析项目时出错: {str(e)}")
                            
                            # 如果结果少于预期，可能没有更多页面
                            if len(items) < 10:  # 假设每页显示10条
                                break
                            
                            # 页面间暂停，防止被反爬
                            await asyncio.sleep(random.uniform(2, 5))
                            
                    except Exception as e:
                        logger.error(f"处理第 {page} 页时出错: {str(e)}")
                        break
                        
        except Exception as e:
            logger.error(f"抓取过程出错: {str(e)}")
        
        logger.info(f"从中国政府采购网共抓取到 {len(results)} 条 {company} 的招投标信息")
        return results
    
    @classmethod
    async def fetch_details(cls, url: str, session, headers) -> Dict[str, Any]:
        """抓取详情页内容获取更多信息"""
        details = {}
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html_text = await response.text()
                    html = etree.HTML(html_text)
                    
                    # 提取更多字段，根据网站结构调整XPath
                    project_id = "".join(html.xpath("//div[contains(text(), '项目编号')]/following-sibling::div[1]/text()")).strip()
                    if project_id:
                        details['项目编号'] = project_id
                        
                    buyer_name = "".join(html.xpath("//div[contains(text(), '采购人')]/following-sibling::div[1]/text()")).strip()
                    if buyer_name:
                        details['采购人'] = buyer_name
                    
                    # 添加更多字段...
        except Exception as e:
            logger.error(f"抓取详情页出错: {str(e)}")
        
        return details

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