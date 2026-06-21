# Performance Optimization
## Description
Profile first, then optimize. Never guess.
## Instructions
1. MEASURE before optimizing — use cProfile, memory_profiler, timeit
2. Identify the actual bottleneck (not what you think is slow)
3. Cache expensive computations (lru_cache, redis)
4. Use generators for large datasets (yield instead of list)
5. Batch database/API calls (N+1 elimination)
6. Async I/O for network-bound operations
7. Profile again after optimization to confirm improvement