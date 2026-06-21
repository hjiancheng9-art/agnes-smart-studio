# Code Review & Quality
## Description
Multi-axis code review: bugs, security, performance, style, architecture.
## Instructions
1. Read the diff completely before commenting
2. Check: logic errors, security vulnerabilities, resource leaks, edge cases
3. Check: naming conventions, code duplication, test coverage
4. Check: error handling completeness, input validation
5. Suggest improvements with concrete examples
6. Run python -c "import ast" on every modified Python file
7. Run python -m pytest tests/ -q after changes