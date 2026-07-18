"""Redis tools — Redis command execution.

Tools:
    redis_exec  Execute a Redis command

Dependency is optional — graceful error if redis-py not installed.
"""

from __future__ import annotations

import json

# Dangerous Redis commands blocked by default
_DANGEROUS_COMMANDS = frozenset(
    {
        "FLUSHALL",
        "FLUSHDB",
        "SHUTDOWN",
        "CONFIG",
        "DEBUG",
        "SAVE",
        "BGSAVE",
        "BGREWRITEAOF",
        "SLAVEOF",
        "REPLICAOF",
        "MIGRATE",
        "RESTORE",
        "MODULE",
        "ACL",
        "SCRIPT",
    }
)


def redis_exec(
    command: str,
    host: str = "localhost",
    port: int = 6379,
    password: str = "",
    db: int = 0,
) -> str:
    """Execute a Redis command.

    Args:
        command: Redis command string, e.g. "GET mykey" or "SET mykey myvalue EX 60"
        host: Host (default: localhost)
        port: Port (default: 6379)
        password: Redis password (optional)
        db: Database number (default: 0)

    Returns:
        JSON with the command result
    """
    if not command:
        return "[错误] command 参数不能为空"

    parts = command.strip().split()
    cmd_name = parts[0].upper()
    cmd_args = parts[1:]

    if cmd_name in _DANGEROUS_COMMANDS:
        return f"[安全拒绝] 命令 '{cmd_name}' 已被阻止（危险操作）"

    try:
        import redis
    except ImportError:
        return "[错误] redis-py 未安装。运行: pip install redis"

    display_host = f"{host}:{port}/db{db}"

    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password or None,
            db=db,
            decode_responses=True,
            socket_connect_timeout=10,
        )
        # Ping to verify connection
        client.ping()

        # Execute command with parsed arguments
        result = client.execute_command(cmd_name, *cmd_args)

        client.close()

        return json.dumps(
            {
                "command": command,
                "result": result,
                "connection": display_host,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    except Exception as e:
        err_msg = str(e).replace(password, "***") if password else str(e)
        return f"[错误] Redis 命令失败 ({display_host}): {err_msg}"
