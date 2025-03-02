"""API路由定义"""
import os
import logging
import asyncio
import pandas as pd
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from typing import List, Optional
from datetime import datetime
import uuid
import json

import config
from modules import module_manager
from modules.api.models import CompanyPreviewResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("bidscrap")

# 全局进度存储
search_progress = {}

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

@router.post("/scrape_with_progress")
async def scrape_with_progress(request: Request):
    """处理抓取请求并返回任务ID"""
    form = await request.form()
    
    # 获取表单数据
    start_date = form.get('start_date', '').replace('-', ':')
    end_date = form.get('end_date', '').replace('-', ':')
    source_type = form.get('source_type', 'default')
    
    # 获取公司列表（与原scrape函数类似）
    if source_type == 'default':
        company = form.get('company', '').strip()
        if company:
            selected_companies = [company]
        else:
            selected_companies = form.getlist('default_companies')
            if not selected_companies:
                selected_companies = config.TARGET_COMPANIES
    else:
        # ... 其余处理与原函数相同 ...
        pass
        
    # 创建唯一任务ID
    task_id = str(uuid.uuid4())
    
    # 初始化进度信息
    search_progress[task_id] = {
        "status": "started",
        "total_companies": len(selected_companies),
        "processed_companies": 0,
        "current_company": "",
        "results_count": 0,
        "log": []
    }
    
    # 启动后台任务
    asyncio.create_task(
        execute_search(task_id, selected_companies, start_date, end_date)
    )
    
    return {"task_id": task_id}

async def execute_search(task_id, companies, start_date, end_date):
    """执行实际的搜索任务并更新进度"""
    all_results = []
    searched_companies = []
    search_stats = {}
    
    try:
        # 对每个公司执行搜索
        for i, company in enumerate(companies):
            # 更新进度
            search_progress[task_id]["current_company"] = company
            search_progress[task_id]["processed_companies"] = i
            search_progress[task_id]["log"].append(f"开始搜索: {company}")
            
            searched_companies.append(company)
            search_stats[company] = {"total": 0, "sources": {}}
            
            # 并行运行所有爬虫
            tasks = []
            for scraper_name, scraper in module_manager.scrapers.items():
                # 添加爬虫的超时时间设置
                scraper_timeout = getattr(scraper, "scraper_timeout", 60)  # 默认60秒
                tasks.append((scraper_name, scraper.scrape(company, start_date, end_date)))
            
            # 等待所有爬虫完成
            scraper_results = []
            for scraper_name, task in tasks:
                try:
                    # 使用asyncio的wait_for添加超时控制
                    scraper_timeout = getattr(module_manager.scrapers[scraper_name], 
                                             "scraper_timeout", 60)  # 默认60秒
                    results = await asyncio.wait_for(task, timeout=scraper_timeout)
                    scraper_results.append(results)
                    
                    # 记录每个来源的结果数
                    search_stats[company]["sources"][scraper_name] = len(results)
                    search_stats[company]["total"] += len(results)
                    search_progress[task_id]["log"].append(
                        f"来源 {scraper_name} 找到 {len(results)} 条记录"
                    )
                except asyncio.TimeoutError:
                    # 处理超时情况
                    logger.error(f"搜索公司 {company} 的来源 {scraper_name} 超时")
                    search_stats[company]["sources"][scraper_name] = 0
                    search_progress[task_id]["log"].append(
                        f"来源 {scraper_name} 搜索超时，已跳过"
                    )
                except Exception as e:
                    logger.error(f"搜索公司 {company} 的来源 {scraper_name} 失败: {str(e)}")
                    search_stats[company]["sources"][scraper_name] = 0
                    search_progress[task_id]["log"].append(
                        f"来源 {scraper_name} 搜索失败: {str(e)}"
                    )
            
            # 合并结果
            for results in scraper_results:
                all_results.extend(results)
                
            # 更新进度
            search_progress[task_id]["results_count"] = len(all_results)
            search_progress[task_id]["log"].append(
                f"完成搜索: {company}, 共找到 {search_stats[company]['total']} 条记录"
            )
        
        # 保存结果到Excel
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        output_file = os.path.join(config.OUTPUT_DIR, f"招投标信息_{timestamp}.xlsx")
        
        if all_results:
            df = pd.DataFrame(all_results)
            df.to_excel(output_file, index=False)
            filename = os.path.basename(output_file)
        else:
            filename = None
            
        # 更新最终状态
        search_progress[task_id].update({
            "status": "completed",
            "processed_companies": len(companies),
            "success": len(all_results) > 0,
            "filename": filename,
            "search_stats": search_stats,
            "searched_companies": searched_companies,
            "results": all_results if len(all_results) < 100 else all_results[:100],  # 限制大小
            "count": len(all_results)
        })
            
    except Exception as e:
        # 处理错误
        search_progress[task_id].update({
            "status": "error",
            "error": str(e),
            "log": search_progress[task_id]["log"] + [f"错误: {str(e)}"]
        })

@router.get("/search_progress/{task_id}")
async def get_search_progress(task_id: str):
    """获取搜索进度"""
    if task_id not in search_progress:
        raise HTTPException(status_code=404, detail="任务ID不存在")
    
    return search_progress[task_id]

@router.get("/search_progress_stream/{task_id}")
async def search_progress_stream(task_id: str):
    """Server-Sent Events流式更新进度"""
    if task_id not in search_progress:
        raise HTTPException(status_code=404, detail="任务ID不存在")
    
    async def event_generator():
        last_status = None
        while True:
            current = search_progress[task_id]
            
            # 只有状态变化时才发送
            if current != last_status:
                yield f"data: {json.dumps(current, ensure_ascii=False)}\n\n"
                last_status = current.copy()
            
            # 如果已完成或出错，结束流
            if current.get("status") in ["completed", "error"]:
                break
                
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

@router.get("/search_results/{task_id}")
async def get_search_results(request: Request, task_id: str):
    """显示搜索结果页面"""
    if task_id not in search_progress:
        raise HTTPException(status_code=404, detail="任务ID不存在")
    
    progress = search_progress[task_id]
    
    if progress.get("status") != "completed":
        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "success": False,
                "error": "搜索任务尚未完成",
                "task_id": task_id
            }
        )
    
    # 准备模板数据
    template_data = {
        "request": request,
        "success": progress.get("success", False),
        "results": progress.get("results", []),
        "count": progress.get("count", 0),
        "companies_count": len(progress.get("searched_companies", [])),
        "filename": progress.get("filename"),
        "searched_companies": progress.get("searched_companies", []),
        "search_stats": progress.get("search_stats", {}),
        "search_params": {
            "start_date": progress.get("start_date", "").replace(':', '-'),
            "end_date": progress.get("end_date", "").replace(':', '-')
        },
        "task_id": task_id
    }
    
    if not progress.get("success", False):
        template_data["error"] = "未找到符合条件的招投标信息"
    
    return templates.TemplateResponse("results.html", template_data)

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