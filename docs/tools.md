# 外部工具 (12 个)

智能体模式 (`/agent`) 下自动加载 tools.json 定义的 12 个工具：

| 工具 | 类型 | 功能 |
|------|------|------|
| `read_file` | shell | 读取文件内容 |
| `write_file` | shell | 写入文件 |
| `search_files` | shell | 正则搜索文件内容 |
| `list_files` | shell | 列出目录 |
| `run_python` | shell | 执行 Python 代码 |
| `run_test` | shell | 运行 pytest |
| `web_fetch` | shell | 获取网页内容 |
| `web_search` | shell | DuckDuckGo 搜索 |
| `git_status` | shell | git 状态 |
| `git_diff` | shell | git 未提交更改 |
| `git_log` | shell | 最近提交记录 |
| `pip_install` | shell | 安装 Python 包 |

## 添加新工具

编辑 `tools.json`，格式见 `docs/authoring.md`：

```json
{
  "name": "my_tool",
  "type": "shell",
  "description": "工具描述",
  "command": "执行命令",
  "parameters": { "arg": {"type": "string", "required": true} }
}
```

保存后 `/agent` 重新加载生效。
