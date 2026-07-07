"""Incident Playbook — 故障修复剧本，每条故障类别对应可执行的修复步骤。"""


# 故障修复剧本
PLAYBOOKS = {
    "provider_unavailable": {
        "title": "Provider 不可用",
        "severity": "high",
        "steps": [
            "检查 provider API key 是否有效：/provider",
            "检查网络连接是否正常",
            "尝试切换到备用 provider：/provider <name>",
            "如果持续失败，检查熔断状态：/providers",
        ],
        "auto_commands": ["/providers"],
        "suggested_commands": ["/provider crux", "/provider deepseek"],
    },
    "timeout": {
        "title": "任务超时",
        "severity": "medium",
        "steps": [
            "增大 timeout 设置或拆分任务",
            "检查 provider 响应是否正常",
            "考虑增加 max_workers 提高并行度",
        ],
        "auto_commands": [],
        "suggested_commands": [],
    },
    "rate_limit": {
        "title": "频率限制 (Rate Limit)",
        "severity": "medium",
        "steps": [
            "降低请求频率，添加退避等待",
            "检查 API 配额是否用尽",
            "考虑升级套餐或切换 provider",
        ],
        "auto_commands": [],
        "suggested_commands": ["/providers"],
    },
    "auth_error": {
        "title": "认证错误",
        "severity": "high",
        "steps": [
            "检查 API key 是否过期",
            "检查 API key 权限是否足够",
            "更新环境变量中的 API key",
            "重启后重试",
        ],
        "auto_commands": [],
        "suggested_commands": ["/provider"],
    },
    "dag_deadlock": {
        "title": "DAG 死锁",
        "severity": "high",
        "steps": [
            "检查任务依赖关系是否正确",
            "检查是否存在循环依赖",
            "检查是否有 task 引用了不存在的依赖",
            "查看 /replay <trace_id> 分析死锁原因",
        ],
        "auto_commands": ["/replay {trace_id}"],
        "suggested_commands": [],
    },
    "circuit_breaker": {
        "title": "熔断器触发",
        "severity": "medium",
        "steps": [
            "等待冷却时间后自动恢复",
            "查看 provider 状态：/providers",
            "如果急需恢复，手动重置熔断",
        ],
        "auto_commands": ["/providers"],
        "suggested_commands": [],
    },
    "internal_error": {
        "title": "服务端错误",
        "severity": "high",
        "steps": [
            "等待几秒后重试",
            "如果持续失败，切换 provider",
            "记录错误信息用于排查",
        ],
        "auto_commands": [],
        "suggested_commands": ["/providers"],
    },
    "model_error": {
        "title": "模型错误",
        "severity": "medium",
        "steps": [
            "检查模型 ID 是否正确",
            "确认模型在当前 provider 可用",
            "尝试切换到其他模型或 provider",
        ],
        "auto_commands": [],
        "suggested_commands": [],
    },
    "unknown": {
        "title": "未知错误",
        "severity": "low",
        "steps": [
            "收集错误日志",
            "查看 /replay <trace_id> 获取完整时间线",
            "如持续出现请联系开发团队",
        ],
        "auto_commands": ["/replay {trace_id}"],
        "suggested_commands": [],
    },
}


def get_playbook(category: str) -> dict:
    """获取指定故障类别的修复剧本。"""
    return PLAYBOOKS.get(category, PLAYBOOKS["unknown"])


def format_playbook(category: str, trace_id: str = "") -> str:
    """格式化为可读的修复指南。"""
    pb = get_playbook(category)
    lines = [
        f"故障: {pb['title']} (severity={pb['severity']})",
        "建议步骤:",
    ]
    for i, step in enumerate(pb["steps"], 1):
        formatted = step.replace("{trace_id}", trace_id)
        lines.append(f"  {i}. {formatted}")
    if pb.get("suggested_commands"):
        lines.append("可用命令:")
        for cmd in pb["suggested_commands"]:
            lines.append(f"  {cmd}")  # cmd already includes /
    return "\n".join(lines)


def auto_remediation(incident: dict, trace_id: str = "") -> list[str]:
    """基于故障分类自动生成修复命令列表。"""
    category = incident.get("primary_category", "unknown")
    pb = get_playbook(category)
    commands = []
    for cmd in pb.get("auto_commands", []):
        commands.append(cmd.replace("{trace_id}", trace_id))
    return commands
