"""API模块 - 处理所有Web API请求"""
from fastapi import APIRouter
from modules.api.routes import router

# 导出路由
__all__ = ['router'] 