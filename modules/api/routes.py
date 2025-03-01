"""API路由定义"""
import os
import logging
import asyncio
import pandas as pd
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
from datetime import datetime

import config
from modules import module_manager
from modules.api.models import CompanyPreviewResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("bidscrap")

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页"""
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "companies": config.TARGET_COMPANIES,
            "start_date": config.DEFAULT_START_DATE.replace(':', '-'),
            "end_date": config.DEFAULT_END_DATE.replace(':', '-')
        }
    )

@router.post("/preview_companies")
async def preview_companies(
    file: UploadFile = File(...),
    column_index: int = Form(0),
    skip_rows: int = Form(1)
):
    """预览上传文件中的企业名称"""
    try:
        if not file:
            return CompanyPreviewResponse(success=False, error="未上传文件")
            
        if not file.filename:
            return CompanyPreviewResponse(success=False, error="未选择文件")
        
        try:
            # 获取文件扩展名
            _, file_extension = os.path.splitext(file.filename)
            file_extension = file_extension.lower()
            
            # 查找合适的解析器
            parser = None
            for p in module_manager.parsers.values():
                if p.can_handle(file_extension):
                    parser = p
                    break
            
            if not parser:
                return CompanyPreviewResponse(success=False, error=f"不支持的文件格式: {file_extension}")
            
            # 解析文件
            companies = await parser.parse(file, column_index, skip_rows)
            
            if not companies:
                return CompanyPreviewResponse(success=False, error="文件中未找到有效的企业名称")
                
            return CompanyPreviewResponse(
                success=True, 
                companies=companies,
                count=len(companies)
            )
        except Exception as e:
            logger.error(f"解析文件失败: {str(e)}")
            return CompanyPreviewResponse(success=False, error=f"解析文件失败: {str(e)}")
    except Exception as e:
        logger.error(f"服务器错误: {str(e)}")
        return CompanyPreviewResponse(success=False, error=f"服务器错误: {str(e)}")

@router.post("/scrape", response_class=HTMLResponse)
async def scrape(request: Request):
    """处理抓取请求"""
    try:
        form = await request.form()
        
        # 获取表单数据
        start_date = form.get('start_date', '').replace('-', ':')
        end_date = form.get('end_date', '').replace('-', ':')
        source_type = form.get('source_type', 'default')
        
        # 根据来源类型获取公司列表
        if source_type == 'default':
            # 使用预设公司列表
            selected_companies = form.getlist('default_companies')
            if not selected_companies:
                selected_companies = config.TARGET_COMPANIES
        else:
            # 获取预览确认后的企业列表
            selected_companies = form.getlist('uploaded_companies')
            
            if not selected_companies:
                # 如果没有预览确认的企业，尝试从文件中解析
                if 'company_file' not in form:
                    return templates.TemplateResponse(
                        "results.html", 
                        {
                            "request": request,
                            "success": False,
                            "error": "未上传企业名录文件"
                        }
                    )
                    
                file = form['company_file']
                if not file.filename:
                    return templates.TemplateResponse(
                        "results.html", 
                        {
                            "request": request,
                            "success": False,
                            "error": "未选择企业名录文件"
                        }
                    )
                
                try:
                    # 获取文件扩展名
                    _, file_extension = os.path.splitext(file.filename)
                    file_extension = file_extension.lower()
                    
                    # 查找合适的解析器
                    parser = None
                    for p in module_manager.parsers.values():
                        if p.can_handle(file_extension):
                            parser = p
                            break
                    
                    if not parser:
                        return templates.TemplateResponse(
                            "results.html", 
                            {
                                "request": request,
                                "success": False,
                                "error": f"不支持的文件格式: {file_extension}"
                            }
                        )
                    
                    column_index = int(form.get('column_index', 0))
                    skip_rows = int(form.get('skip_rows', 1))
                    
                    # 解析文件
                    selected_companies = await parser.parse(file, column_index, skip_rows)
                    
                    if not selected_companies:
                        return templates.TemplateResponse(
                            "results.html", 
                            {
                                "request": request,
                                "success": False,
                                "error": "企业名录文件中未找到有效的企业名称"
                            }
                        )
                    logger.info(f"成功从文件中解析出 {len(selected_companies)} 家企业")
                except Exception as e:
                    return templates.TemplateResponse(
                        "results.html", 
                        {
                            "request": request,
                            "success": False,
                            "error": f"解析企业名录文件失败: {str(e)}"
                        }
                    )
            else:
                return templates.TemplateResponse(
                    "results.html", 
                    {
                        "request": request,
                        "success": False,
                        "error": "未提供企业名称"
                    }
                )
        
        # 创建临时文件名
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        output_file = os.path.join(config.OUTPUT_DIR, f"招投标信息_{timestamp}.xlsx")
        
        # 执行抓取
        all_results = []
        
        # 对每个公司使用所有可用的爬虫
        for company in selected_companies:
            # 并行运行所有爬虫
            tasks = []
            for scraper in module_manager.scrapers.values():
                tasks.append(scraper.scrape(company, start_date, end_date))
            
            # 等待所有爬虫完成
            scraper_results = await asyncio.gather(*tasks)
            
            # 合并结果
            for results in scraper_results:
                all_results.extend(results)
        
        # 保存结果
        if all_results:
            df = pd.DataFrame(all_results)
            df.to_excel(output_file, index=False)
            logger.info(f"结果已保存到 {output_file}，共 {len(all_results)} 条记录")
            
            # 返回结果
            return templates.TemplateResponse(
                "results.html",
                {
                    "request": request,
                    "success": True,
                    "results": all_results,
                    "count": len(all_results),
                    "companies_count": len(selected_companies),
                    "filename": os.path.basename(output_file)
                }
            )
        else:
            return templates.TemplateResponse(
                "results.html",
                {
                    "request": request,
                    "success": False,
                    "error": "未找到符合条件的招投标信息"
                }
            )
        
    except Exception as e:
        logger.error(f"爬虫执行出错: {str(e)}")
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "success": False,
                "error": f"爬虫执行出错: {str(e)}"
            }
        )

@router.get("/download/{filename}")
async def download(filename: str):
    """下载Excel文件"""
    file_path = os.path.join(config.OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        raise HTTPException(status_code=404, detail="文件不存在") 