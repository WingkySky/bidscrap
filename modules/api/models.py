"""API数据模型"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class CompanyPreviewResponse(BaseModel):
    """企业预览响应模型"""
    success: bool
    companies: Optional[List[str]] = None
    count: Optional[int] = None
    error: Optional[str] = None

class TenderItem(BaseModel):
    """招投标信息项目"""
    company: str
    title: str
    publish_date: str
    content: str
    source: str
    url: str
    scrape_time: str

class TenderResult(BaseModel):
    """招投标结果"""
    success: bool
    items: List[TenderItem] = []
    count: int = 0
    companies_count: int = 0
    output_file: Optional[str] = None
    error: Optional[str] = None 