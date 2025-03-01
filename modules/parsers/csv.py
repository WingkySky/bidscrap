"""CSV文件解析器 - 处理.csv文件"""
import os
import tempfile
import logging
import pandas as pd
from typing import List

from modules.parsers.base import FileParser
from modules.parsers import register_parser

logger = logging.getLogger("bidscrap")

@register_parser
class CSVParser(FileParser):
    """CSV文件解析器"""
    
    @classmethod
    async def parse(cls, file, column_index: int = 0, skip_rows: int = 1) -> List[str]:
        """解析CSV文件提取企业名称"""
        companies = []
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
        
        try:
            # 读取上传的文件内容
            content = await file.read()
            
            # 写入临时文件
            with open(temp_file.name, "wb") as f:
                f.write(content)
            
            # 使用pandas读取CSV文件
            df = pd.read_csv(temp_file.name, skiprows=skip_rows)
            
            # 提取指定列的企业名称
            if column_index < len(df.columns):
                companies = df.iloc[:, column_index].dropna().tolist()
                # 清理公司名称
                companies = [str(company).strip() for company in companies if str(company).strip()]
            else:
                raise ValueError(f"列索引 {column_index} 超出范围，文件只有 {len(df.columns)} 列")
                
        except Exception as e:
            logger.error(f"解析CSV文件时出错: {str(e)}")
            raise e
        finally:
            # 删除临时文件
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        
        return companies
    
    @classmethod
    def can_handle(cls, file_extension: str) -> bool:
        """判断是否可以处理该文件类型"""
        return file_extension.lower() == '.csv'
    
    @classmethod
    @property
    def name(cls) -> str:
        """解析器名称"""
        return "csv" 