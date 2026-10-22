# Laowang Bot 操作说明

- 用中文沟通。密钥只存 `~/.secrets/`，不得写入聊天、代码、日志或提交。
- 生产部署、停用密钥、线上数据变更前先说明影响。
- Python 依赖在 `requirements.txt`；Railway 启动命令在 `railway.toml`。
- 数据库客户端入口为 `db/client.py`。新格式 Supabase secret key 需要兼容的 SDK；2.7.4 会拒绝此格式，当前固定为 2.33.0。
- 验证依赖时使用隔离虚拟环境，运行 `python -m pip check`。数据库只读连通性验证可以查询 `users` 的 `id` 并设置 `limit(0)`。禁止输出配置值或异常中的完整请求。
- 不要在检查中启动应用 lifespan：它会启动 Telegram bot、scheduler 并变更 webhook。
- `laowang-toolbox` 的线上版本来自 CLI 快照；重新部署前需要核对实际源码，不能直接假定与 GitHub main 相同。
- 2026-10-22 Railway 安全事件处置：独立的新 Supabase secret key 已在私有密钥目录准备并通过只读验证。本分支只解决 SDK 兼容性，不代表线上已部署、旧凭证已撤销或全部凭证已轮换。
