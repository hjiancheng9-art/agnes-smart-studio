# Git Workflow Patterns
## Description
Structured git workflow for solo and team development.
## Instructions
1. Commit early, commit often — each commit = one logical change
2. Write descriptive commit messages: 'Fix: handle null input in parse_user()'
3. Branch naming: feature/xxx, bugfix/xxx, refactor/xxx
4. Rebase feature branches on main before merging
5. NEVER force push to shared branches
6. Use git stash for experimental changes
7. Review your own diff before committing (git diff --staged)