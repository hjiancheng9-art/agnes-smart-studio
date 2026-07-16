## 提分修复

1. **补测试**: runtime_types(3) + runtime_result(3) + tool_executor(2) = 8 tests
2. **修复 video poll 线程**: join(2s) vs wait(120s) 不匹配，改为同步等待
3. **补 provider fallback 测试**: ProviderManager._apply_builtin_defaults 验证