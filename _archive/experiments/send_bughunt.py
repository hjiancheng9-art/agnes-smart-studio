
PROMPT = """# ComfyUI 智能体: 全方位 Bug Hunt

## 项目现状
4轮迭代已完成，22模块/34回归测试通过，健康分 82+

## 代码扫描结果 (91个.py文件, 50628行, 1058函数)

### 问题分布:
- 📄 6个大文件(>300行): workflow_handler.py / lora_manager.py / server.py.bak / workflow_generator.py / recovery.py / agent_flow.py
- 🌐 18个文件用 `from X import *`  (wildcard imports — 命名空间污染)
- 📝 4个文件含 TODO/FIXME 未处理
- ⚠️ 1个 bare except

### 需要重点审查:
1. workflow_handler.py — 最大文件, 集中了所有路由处理函数(workflow + recovery + ux + lora)
2. server.py — ROUTES 字典是否和 handler 函数一一对应? 有没有遗漏?
3. lora_manager.py — 训练参数预设是否正确?
4. recovery.py — 熔断器和队列是否线程安全?
5. 跨模块依赖 — handlers/ 和 server.py 之间有没有循环引用的风险?

### 项目完整文件列表:
91个.py文件, 50628行代码, 1058个函数/类

### 请从下面几个角度全面找Bug:

1. 架构层面: 模块拆分是否合理? 单点故障在哪里?
2. 代码层面: 有没有潜在的空指针/未处理异常/资源泄漏?
3. 业务逻辑: 工作流推荐→执行→恢复的完整链路有没有断裂点?
4. 并发安全: 多个HTTP请求同时执行时会不会有竞态?
5. 数据安全: 有没有敏感信息泄漏(API key/路径)?
6. 边界条件: 工作流为空/参数缺失/ComfyUI 未安装时会发生什么?

## 请给出排序的Bug列表(P0/P1/P2), 每个带具体位置和修复方案"""
