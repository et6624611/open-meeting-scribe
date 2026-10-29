"""企业版 P0 数据层（EP0-BE 第一增量）。

契约基线：shared/P0-BACKEND-DESIGN-MULTIUSER-20261029.md v1.0（2026-10-29 09:30 UTC 冻结）。
范围：DATA_ROOT 解析、SQLite schema 迁移 runner、口令/邀请码/token 安全原语、
actor 强制 DAO（账号域 + 上下文快照域）、一致性备份快照。
"""
