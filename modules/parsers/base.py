"""文件解析器基础类 - 定义所有文件解析器必须实现的接口"""
from abc import ABC, abstractmethod
from typing import List, Any

class FileParser(ABC):
    """文件解析器抽象基类"""
    
    @classmethod
    @abstractmethod
    async def parse(cls, file, column_index: int = 0, skip_rows: int = 1) -> List[str]:
        """
        解析文件提取企业名称
        :param file: 上传的文件对象
        :param column_index: 企业名称所在的列索引 (从0开始)
        :param skip_rows: 要跳过的行数
        :return: 企业名称列表
        """
        pass
    
    @classmethod
    @abstractmethod
    def can_handle(cls, file_extension: str) -> bool:
        """
        判断该解析器是否能处理指定扩展名的文件
        :param file_extension: 文件扩展名 (包含.)
        :return: 如果能处理则返回True
        """
        pass
    
    @classmethod
    @property
    @abstractmethod
    def name(cls) -> str:
        """解析器名称"""
        pass 