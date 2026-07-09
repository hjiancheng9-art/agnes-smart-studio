"""Execution 异常定义"""


class ExecutionError(Exception):
    """执行基础异常"""
    pass


class SubmissionError(ExecutionError):
    """提交失败"""
    pass


class PollingTimeoutError(ExecutionError):
    """轮询超时"""
    pass


class OutputNotFoundError(ExecutionError):
    """输出产物未找到"""
    pass


class ComfyUIOfflineError(ExecutionError):
    """ComfyUI 离线"""
    pass


class QueueFullError(ExecutionError):
    """队列已满"""
    pass
