# Security & Hardening
## Description
Harden code against OWASP Top 10 and common vulnerabilities.
## Instructions
1. NEVER hardcode secrets (API keys, passwords, tokens)
2. Validate ALL user input (type, length, range, format)
3. Use parameterized queries (never string concatenation for SQL)
4. Escape output (XSS prevention)
5. Set secure defaults (deny by default)
6. Use HTTPS everywhere, verify TLS certificates
7. Implement rate limiting on all endpoints
8. Log security events without exposing sensitive data
9. Keep dependencies updated (pip audit, 
pm audit)
10. Apply principle of least privilege