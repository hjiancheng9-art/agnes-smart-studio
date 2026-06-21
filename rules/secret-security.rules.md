# 密钥安全规范

1. 绝对不提交 API Key/密码到代码
2. 用环境变量或 .env 管理密钥
3. .env 加入 .gitignore
4. 代码中不硬编码 token/password
5. 发现泄露立即轮换