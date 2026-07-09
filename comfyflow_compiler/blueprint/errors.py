"""Blueprint 异常定义"""


class BlueprintError(Exception):
    """蓝图基础异常"""
    pass


class BlueprintValidationError(BlueprintError):
    """蓝图校验失败 — schema 不通过"""
    pass


class BlueprintNotFoundError(BlueprintError):
    """蓝图未找到"""
    pass


class BlueprintPackingError(BlueprintError):
    """打包 workflow → blueprint 失败"""
    pass


class BlueprintLoadError(BlueprintError):
    """加载蓝图文件失败"""
    pass
