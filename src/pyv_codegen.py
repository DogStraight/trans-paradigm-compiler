from pyv_definition import Node
from typing import List

class CodeGenerator:
    """编译器代码生成后端基础框架"""
    
    def __init__(self):
        """初始化代码生成器"""
        pass
    
    def generate(self, ast: Node) -> List[str]:
        """
        生成目标代码主入口
        :param ast: 抽象语法树
        :return: 生成的目标代码列表
        """
        raise NotImplementedError
        
    def optimize(self, code: List[str]) -> List[str]:
        """
        代码优化接口
        :param code: 生成的目标代码
        :return: 优化后的代码
        """
        raise NotImplementedError
        
    def dump(self, code: List[str]) -> None:
        """
        代码输出接口
        :param code: 要输出的代码
        """
        raise NotImplementedError
