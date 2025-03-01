"""模块管理系统 - 管理所有模块的加载和注册"""
import logging
import importlib
import os
import sys
from typing import Dict, List, Any, Type, Optional

logger = logging.getLogger("bidscrap")

class ModuleManager:
    """模块管理器 - 负责模块的注册、发现和加载"""
    
    def __init__(self):
        """初始化模块管理器"""
        # 存储已注册的模块
        self.parsers = {}
        self.scrapers = {}
    
    def discover_modules(self):
        """发现并加载所有模块"""
        # 加载文件解析器模块
        from modules.parsers import load_parsers
        self.parsers = load_parsers()
        logger.info(f"已加载 {len(self.parsers)} 个文件解析器模块")
        
        # 加载爬虫模块
        from modules.scrapers import load_scrapers
        self.scrapers = load_scrapers()
        logger.info(f"已加载 {len(self.scrapers)} 个爬虫模块")
    
    def get_parser(self, file_type: str):
        """根据文件类型获取相应的解析器"""
        if file_type in self.parsers:
            return self.parsers[file_type]
        return None
    
    def get_all_scrapers(self):
        """获取所有爬虫模块"""
        return self.scrapers.values()
    
    def get_scraper(self, name: str):
        """根据名称获取爬虫模块"""
        if name in self.scrapers:
            return self.scrapers[name]
        return None

# 创建全局模块管理器实例
module_manager = ModuleManager() 