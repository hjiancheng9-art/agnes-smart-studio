# Python Anti-Patterns
## Description
Avoid common Python mistakes. Write idiomatic code.
## Instructions
1. Never use rom module import * — always explicit imports
2. Use with for resource management (files, locks, connections)
3. Prefer list/dict/set comprehensions over loops for simple transforms
4. Use f-strings (not % or .format()) for string formatting
5. Use type hints on all function signatures
6. Don't use mutable default arguments (def f(x=[]): is a bug)
7. Use is None not == None
8. Catch specific exceptions, not bare except: