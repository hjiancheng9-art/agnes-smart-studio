---
default-active: false
---
# Error Translation — 错误信息翻译

## 规则
所有工具返回的错误信息，在显示给用户前，自动翻译为通俗易懂的中文。

## 翻译映射
| 技术错误 | 用户语言 |
|----------|---------|
| `429 rate limit exceeded` | "服务繁忙，稍等几秒再试" |
| `500 internal server error` | "后端服务异常，已自动切换备用线路" |
| `ConnectionRefusedError` | "服务未启动或端口被占用" |
| `ModuleNotFoundError: No module named 'xxx'` | "缺少依赖包 xxx，已尝试自动安装" |
| `PermissionError` | "没有写入权限，请检查文件是否被占用" |
| `FileNotFoundError` | "文件不存在，已自动搜索相似路径" |
| `SyntaxError` | "代码语法有误，已定位到具体行" |
| `TimeoutError` | "操作超时，已触发重试" |
| `API key invalid` | "API 密钥无效，请检查配置" |
| `Out of memory` | "内存不足，已自动降级处理" |

## 行为规范
- 不直接输出原始堆栈。
- 先给用户翻译后的原因 + 建议操作。
- 技术细节折叠在 `<details>` 里（仅开发模式展开）。