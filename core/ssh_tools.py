"""SSH tools — remote command execution and file transfer.

Tools:
    ssh_exec       Execute command on remote host
    ssh_upload     Upload file via SCP
    ssh_download   Download file via SCP
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess


def _ssh_base_args(host: str, user: str, port: int, key_file: str, timeout: int) -> list[str]:
    """Build common SSH base arguments."""
    args = ["ssh"]
    args.extend(["-o", "StrictHostKeyChecking=accept-new"])
    args.extend(["-o", f"ConnectTimeout={timeout}"])
    args.extend(["-o", "BatchMode=yes" if not key_file else "BatchMode=no"])
    if port != 22:
        args.extend(["-p", str(port)])
    if key_file:
        args.extend(["-i", key_file])
    target = f"{host}" if not user else f"{user}@{host}"
    args.append(target)
    return args


def _is_windows() -> bool:
    return platform.system() == "Windows"


def ssh_exec(
    host: str,
    command: str,
    user: str = "",
    port: int = 22,
    password: str = "",
    key_file: str = "",
    timeout: int = 30,
) -> str:
    """Execute a command on a remote host via SSH.

    Args:
        host: Remote hostname or IP
        command: Shell command to execute
        user: SSH username (default: current user)
        port: SSH port (default: 22)
        password: SSH password (requires sshpass on Linux)
        key_file: Path to private key file
        timeout: Timeout in seconds (default: 30)

    Returns:
        JSON with stdout, stderr, exit_code
    """
    if not host or not command:
        return "[错误] host 和 command 参数不能为空"

    if not shutil.which("ssh"):
        if _is_windows():
            return "[错误] 未找到 ssh 命令。Windows 10+ 可在 设置→应用→可选功能 中安装 OpenSSH 客户端"
        return "[错误] 未找到 ssh 命令。请安装: sudo apt install openssh-client"

    args = _ssh_base_args(host, user, port, key_file, timeout)
    args.append(command)

    if password:
        sshpass = shutil.which("sshpass")
        if sshpass:
            # Use sshpass and add BatchMode=no
            args = ["sshpass", "-p", password, "ssh"]
            args.extend(["-o", "StrictHostKeyChecking=accept-new"])
            args.extend(["-o", f"ConnectTimeout={timeout}"])
            if port != 22:
                args.extend(["-p", str(port)])
            target = f"{host}" if not user else f"{user}@{host}"
            args.append(target)
            args.append(command)
        else:
            return json.dumps(
                {
                    "error": "密码认证需要 sshpass",
                    "hint": "Windows: choco install sshpass  |  Linux: sudo apt install sshpass",
                    "alternative": "请使用 key_file 参数指定私钥文件",
                },
                ensure_ascii=False,
                indent=2,
            )

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            creationflags=0x08000000 if _is_windows() else 0,
        )
        return json.dumps(
            {
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "exit_code": proc.returncode,
            },
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        return f"[错误] SSH 命令超时 ({timeout}s)"
    except Exception as e:
        return f"[错误] SSH 执行失败: {e}"


def ssh_upload(
    host: str,
    local_path: str,
    remote_path: str,
    user: str = "",
    port: int = 22,
    password: str = "",
    key_file: str = "",
) -> str:
    """Upload a file to remote host via SCP.

    Args:
        host: Remote hostname or IP
        local_path: Local file path
        remote_path: Remote destination path
        user: SSH username
        port: SSH port
        password: SSH password (requires sshpass)
        key_file: Path to private key file

    Returns:
        JSON with status
    """
    if not host or not local_path or not remote_path:
        return "[错误] host, local_path, remote_path 参数不能为空"
    if not os.path.isfile(local_path):
        return f"[错误] 本地文件不存在: {local_path}"

    if not shutil.which("scp"):
        if _is_windows():
            return "[错误] 未找到 scp 命令。请安装 OpenSSH 客户端"
        return "[错误] 未找到 scp 命令"

    args = ["scp"]
    args.extend(["-o", "StrictHostKeyChecking=accept-new"])
    if port != 22:
        args.extend(["-P", str(port)])
    if key_file:
        args.extend(["-i", key_file])
    args.append(local_path)
    target = f"{host}:{remote_path}" if not user else f"{user}@{host}:{remote_path}"
    args.append(target)

    if password:
        sshpass = shutil.which("sshpass")
        if sshpass:
            args = ["sshpass", "-p", password, *args]
        else:
            return json.dumps(
                {
                    "error": "密码认证需要 sshpass",
                    "hint": "Windows: choco install sshpass  |  Linux: sudo apt install sshpass",
                },
                ensure_ascii=False,
                indent=2,
            )

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=0x08000000 if _is_windows() else 0,
        )
        if proc.returncode == 0:
            return json.dumps(
                {
                    "status": "ok",
                    "local_path": local_path,
                    "remote": f"{host}:{remote_path}",
                    "size": os.path.getsize(local_path),
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "error",
                "exit_code": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        return "[错误] SCP 上传超时 (60s)"
    except Exception as e:
        return f"[错误] SCP 上传失败: {e}"


def ssh_download(
    host: str,
    remote_path: str,
    local_path: str,
    user: str = "",
    port: int = 22,
    password: str = "",
    key_file: str = "",
) -> str:
    """Download a file from remote host via SCP.

    Args:
        host: Remote hostname or IP
        remote_path: Remote file path
        local_path: Local destination path
        user: SSH username
        port: SSH port
        password: SSH password (requires sshpass)
        key_file: Path to private key file

    Returns:
        JSON with status
    """
    if not host or not remote_path or not local_path:
        return "[错误] host, remote_path, local_path 参数不能为空"

    if not shutil.which("scp"):
        if _is_windows():
            return "[错误] 未找到 scp 命令。请安装 OpenSSH 客户端"
        return "[错误] 未找到 scp 命令"

    args = ["scp"]
    args.extend(["-o", "StrictHostKeyChecking=accept-new"])
    if port != 22:
        args.extend(["-P", str(port)])
    if key_file:
        args.extend(["-i", key_file])
    source = f"{host}:{remote_path}" if not user else f"{user}@{host}:{remote_path}"
    args.append(source)
    args.append(local_path)

    if password:
        sshpass = shutil.which("sshpass")
        if sshpass:
            args = ["sshpass", "-p", password, *args]
        else:
            return json.dumps(
                {
                    "error": "密码认证需要 sshpass",
                    "hint": "Windows: choco install sshpass  |  Linux: sudo apt install sshpass",
                },
                ensure_ascii=False,
                indent=2,
            )

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=0x08000000 if _is_windows() else 0,
        )
        if proc.returncode == 0:
            size = os.path.getsize(local_path) if os.path.isfile(local_path) else 0
            return json.dumps(
                {
                    "status": "ok",
                    "remote": f"{host}:{remote_path}",
                    "local_path": local_path,
                    "size": size,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": "error",
                "exit_code": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
    except subprocess.TimeoutExpired:
        return "[错误] SCP 下载超时 (60s)"
    except Exception as e:
        return f"[错误] SCP 下载失败: {e}"
