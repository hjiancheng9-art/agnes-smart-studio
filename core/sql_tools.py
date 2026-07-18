"""SQL tools — PostgreSQL and MySQL query execution.

Tools:
    pg_query     Execute SQL on PostgreSQL
    mysql_query  Execute SQL on MySQL

Dependencies are optional — graceful error if not installed.
"""

from __future__ import annotations

import json
import re

# Write-operation keywords to block when allow_write=False
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|RENAME)\b",
    re.IGNORECASE,
)

_MAX_ROWS = 500


def _is_write_query(query: str) -> bool:
    """Check if a SQL query contains write operations."""
    return bool(_WRITE_KEYWORDS.search(query))


def pg_query(
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "",
    database: str = "postgres",
    query: str = "",
    params: str = "",
    allow_write: bool = False,
) -> str:
    """Execute a SQL query on PostgreSQL.

    Args:
        host: Host (default: localhost)
        port: Port (default: 5432)
        user: Username (default: postgres)
        password: Password
        database: Database name (default: postgres)
        query: SQL query to execute
        params: Optional JSON array of query parameters, e.g. '["val1", 42]'
        allow_write: Allow INSERT/UPDATE/DELETE/DDL (default: false)

    Returns:
        JSON array of rows for SELECT, or rowcount for DML
    """
    if not query:
        return "[错误] query 参数不能为空"

    if not allow_write and _is_write_query(query):
        return f"[安全拒绝] 检测到写操作，需要 allow_write=true。（查询: {query[:100]}）"

    try:
        import psycopg2
    except ImportError:
        return "[错误] psycopg2 未安装。运行: pip install psycopg2-binary"

    parsed_params = None
    if params:
        try:
            parsed_params = json.loads(params)
        except json.JSONDecodeError:
            return f"[错误] params 参数不是有效的 JSON: {params}"

    # Redact password in connection display
    display_host = f"{host}:{port}/{database}"

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database,
            connect_timeout=10,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(query, parsed_params)

        if cur.description:
            # SELECT-like: return rows
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchmany(_MAX_ROWS + 1)
            truncated = len(rows) > _MAX_ROWS
            if truncated:
                rows = rows[:_MAX_ROWS]
            result = [dict(zip(columns, row, strict=False)) for row in rows]

            out = {
                "columns": columns,
                "rows": result,
                "row_count": len(result),
                "truncated": truncated,
                "connection": display_host,
            }
            if truncated:
                out["warning"] = f"结果已截断至 {_MAX_ROWS} 行"
        else:
            out = {
                "rowcount": cur.rowcount,
                "connection": display_host,
            }

        cur.close()
        conn.close()
        return json.dumps(out, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        # Redact password from error messages
        err_msg = str(e).replace(password, "***") if password else str(e)
        return f"[错误] PostgreSQL 查询失败 ({display_host}): {err_msg}"


def mysql_query(
    host: str = "localhost",
    port: int = 3306,
    user: str = "root",
    password: str = "",
    database: str = "",
    query: str = "",
    params: str = "",
    allow_write: bool = False,
) -> str:
    """Execute a SQL query on MySQL.

    Args:
        host: Host (default: localhost)
        port: Port (default: 3306)
        user: Username (default: root)
        password: Password
        database: Database name (required)
        query: SQL query to execute
        params: Optional JSON array of query parameters, e.g. '["val1", 42]'
        allow_write: Allow INSERT/UPDATE/DELETE/DDL (default: false)

    Returns:
        JSON array of rows for SELECT, or rowcount for DML
    """
    if not query:
        return "[错误] query 参数不能为空"
    if not database:
        return "[错误] database 参数不能为空"

    if not allow_write and _is_write_query(query):
        return f"[安全拒绝] 检测到写操作，需要 allow_write=true。（查询: {query[:100]}）"

    try:
        import pymysql
    except ImportError:
        return "[错误] pymysql 未安装。运行: pip install pymysql"

    parsed_params = None
    if params:
        try:
            parsed_params = json.loads(params)
        except json.JSONDecodeError:
            return f"[错误] params 参数不是有效的 JSON: {params}"

    display_host = f"{host}:{port}/{database}"

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=10,
            charset="utf8mb4",
        )
        cur = conn.cursor()
        cur.execute(query, parsed_params)

        if cur.description:
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchmany(_MAX_ROWS + 1)
            truncated = len(rows) > _MAX_ROWS
            if truncated:
                rows = rows[:_MAX_ROWS]
            result = [dict(zip(columns, row, strict=False)) for row in rows]

            out = {
                "columns": columns,
                "rows": result,
                "row_count": len(result),
                "truncated": truncated,
                "connection": display_host,
            }
            if truncated:
                out["warning"] = f"结果已截断至 {_MAX_ROWS} 行"
        else:
            conn.commit()
            out = {
                "rowcount": cur.rowcount,
                "connection": display_host,
            }

        cur.close()
        conn.close()
        return json.dumps(out, ensure_ascii=False, indent=2, default=str)

    except Exception as e:
        err_msg = str(e).replace(password, "***") if password else str(e)
        return f"[错误] MySQL 查询失败 ({display_host}): {err_msg}"
