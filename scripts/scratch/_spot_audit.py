"""Spot audit checks - output to file"""
from pathlib import Path

root = Path('.')
issues = []

# 1. python_executor import injection
tools_py = Path('core/tools.py').read_text(encoding='utf-8')
if 'mod_path.startswith(' not in tools_py:
    issues.append("CRITICAL: python_executor imports ANY module from tools.json with no whitelist")

# 2. notify.py PowerShell injection
notify_py = Path('core/notify.py').read_text(encoding='utf-8')
if '{title}' in notify_py:
    issues.append("HIGH: notify.py PowerShell script interpolates title/message unescaped")

# 3. web_browser.py SSRF
wb = Path('core/web_browser.py').read_text(encoding='utf-8')
if '_validate_url' not in wb:
    issues.append("HIGH: web_browser.py browser navigation has no SSRF check")

# 4. cost_tracker NOT wired
chat = Path('core/chat.py').read_text(encoding='utf-8')
if 'record_usage' not in chat:
    issues.append("MEDIUM: chat.py never calls cost_tracker.record_usage() - cost tracking is dead code")

# 5. MCP process cleanup
mcp = Path('core/mcp_client.py').read_text(encoding='utf-8')
if '__del__' not in mcp and 'atexit' not in mcp:
    issues.append("MEDIUM: MCPClient Popen processes have no cleanup on crash (zombie risk)")

# 6. comfyui_tools urllib
comf = Path('core/comfyui_tools.py').read_text(encoding='utf-8')
if 'urllib.request' in comf:
    issues.append("LOW: comfyui_tools uses raw urllib instead of httpx (no connect timeout)")

# 7. notify.py empty except: pass
if 'except Exception:\n            pass' in notify_py:
    issues.append("LOW: notify.py silently swallows all errors")

# 8. check if validators are actually called in chat
if 'validate_' not in chat:
    issues.append("INFO: chat.py doesn't validate model/size/frames params before API calls")

with open('spot_audit_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(issues) if issues else 'All clear - no new issues')
print('done')
