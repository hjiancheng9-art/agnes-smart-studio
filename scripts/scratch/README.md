# scratch/

一次性调试/探测脚本归档。这些文件**不属于正式代码**，不保证可运行，
未被任何生产代码 import，仅作历史留档。

## 来源
这些 `_*.py` / `del_temp.py` 曾散落在仓库根目录（共 25 个），在 v5.0.0
清理时统一移到此处。它们主要用于：
- 网络/代理连通性探测（`_net_test`, `_proxy_check`, `_px`, `_enc_test`, `_simple_env`）
- CodeBuddy / 技能市场安装探测（`_cb_install`, `_cb_probe`, `_install_skill`）
- 审计/冒烟测试的一次性版本（`_audit_*`, `_spot_audit`, `_verify_*`）
- 工具/ComfyUI 连通检查（`_check_tools`, `_check_comfyui`）
- 旧 CLI 拆分实验（`_split_cli`）

## 注意
如需重新使用，请先理解其依赖，不要直接 `python scripts/scratch/xxx.py`。
正确的探测/诊断功能已整合进 `/self` `/audit` 命令（见 `core/self_audit.py`、
`core/audit_handler.py`）。
