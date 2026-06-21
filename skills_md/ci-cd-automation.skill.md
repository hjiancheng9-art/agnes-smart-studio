# CI/CD & Automation
## Description
Automate build, test, and deploy pipelines.
## Instructions
1. Every push runs: syntax check -> lint -> test -> build
2. Failed pipeline blocks merge
3. Use GitHub Actions / GitLab CI / Jenkins
4. Cache dependencies between runs
5. Run security scans (SAST, dependency audit) in CI
6. Deploy to staging automatically, production with approval
7. Monitor deploy health, auto-rollback on failure