"""Capability 异常定义"""


class CapabilityError(Exception):
    """能力探测基础异常"""
    pass


class ComfyOfflineError(CapabilityError):
    """ComfyUI 离线"""
    pass


class MissingNodeError(CapabilityError):
    """缺少节点"""
    pass


class MissingModelError(CapabilityError):
    """缺少模型"""
    pass
