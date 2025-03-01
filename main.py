"""招投标信息抓取系统主入口"""
import logging
import os
import asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bidscrap.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("bidscrap")

# 创建FastAPI应用
app = FastAPI(title="企业招投标信息抓取系统", description="基于FastAPI的模块化企业招投标信息抓取系统")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 确保输出目录存在
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

# 加载所有模块
from modules import module_manager
module_manager.discover_modules()

# 导入API路由
from modules.api import router
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info("==== 招投标信息抓取系统启动 ====")
    logger.info(f"模块系统已加载 {len(module_manager.parsers)} 个文件解析器和 {len(module_manager.scrapers)} 个爬虫")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=3000, reload=True) 