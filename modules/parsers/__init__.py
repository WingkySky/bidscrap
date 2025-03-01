"""文件解析器模块管理 - 负责注册和管理所有文件解析器"""
import logging
import os
import importlib
from typing import Dict, Type
from modules.parsers.base import FileParser

logger = logging.getLogger("bidscrap")

# 存储所有已注册的解析器
_parsers = {}

def register_parser(parser_class):
    """注册文件解析器模块"""
    _parsers[parser_class.name] = parser_class
    logger.info(f"已注册文件解析器模块: {parser_class.name}")
    return parser_class

def load_parsers() -> Dict[str, Type[FileParser]]:
    """加载所有解析器模块"""
    # 导入所有解析器模块
    try:
        from modules.parsers import excel
        from modules.parsers import csv
        from modules.parsers import word
    except ImportError as e:
        logger.warning(f"导入解析器模块时出错: {str(e)}")
    
    # 返回已注册的解析器
    return _parsers

def get_parser_for_file(file_extension: str) -> Type[FileParser]:
    """根据文件扩展名获取适合的解析器"""
    for parser in _parsers.values():
        if parser.can_handle(file_extension):
            return parser
    return None 