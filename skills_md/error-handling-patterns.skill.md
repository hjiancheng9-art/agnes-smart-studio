# Error Handling Patterns
## Description
Robust error handling with logging, retry, and graceful degradation.
## Instructions
1. NEVER use bare except: or silent except Exception: pass
2. Catch specific exceptions, log details (type, message, traceback)
3. Retry transient failures (network, rate limit) with exponential backoff
4. Set timeouts on all network calls
5. Circuit-breaker: after N failures, stop trying and alert
6. Return meaningful error messages to users (never raw stack traces)
7. Log errors to stderr, never swallow them