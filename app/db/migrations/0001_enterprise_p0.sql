-- 0001_enterprise_p0.sql — 企业版 P0 初始 schema（契约 v1.0 §2.2）
-- 纪律：P0 全部后续变更 additive-only（只加表/加列）；本文件建表后永不修改。

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    login_account TEXT UNIQUE NOT NULL,
    phone TEXT UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT,                          -- 邀请码激活前为 NULL（无初始密码）
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('admin','member')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('active','disabled','pending')),
    tenant_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    jwt_jti TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS invites (
    invite_id TEXT PRIMARY KEY,
    code_hash TEXT UNIQUE NOT NULL,              -- 服务端只存 sha256(code)
    created_by TEXT REFERENCES users(user_id),
    target_user_id TEXT REFERENCES users(user_id),
    max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT,
    disabled_at TEXT
);

CREATE TABLE IF NOT EXISTS device_tokens (
    device_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    token_hash TEXT UNIQUE NOT NULL,
    device_name TEXT NOT NULL DEFAULT '',
    revoked_at TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pairings (
    pairing_id TEXT PRIMARY KEY,
    pairing_code_hash TEXT UNIQUE NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    expires_at TEXT NOT NULL,
    redeemed_at TEXT
);

CREATE TABLE IF NOT EXISTS instance_config (
    key TEXT PRIMARY KEY,                        -- service_open / ai_enabled / ai_provider / egress_allowlist / bootstrap_done
    value_json TEXT NOT NULL,
    updated_by TEXT REFERENCES users(user_id),
    updated_at TEXT NOT NULL
);

-- 上下文域：所有业务表强制三件套 owner_user_id / scope / tenant_id（+acl 预留）
CREATE TABLE IF NOT EXISTS ctx_tasks (
    task_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    scope TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('personal','team','enterprise')),
    tenant_id TEXT,
    acl TEXT,
    legacy_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    meeting_time TEXT,
    participants_text TEXT,
    source TEXT NOT NULL DEFAULT 'client' CHECK(source IN ('client','web_import')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','deleted')),
    deleted_at TEXT,
    current_rev INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ctx_tasks_owner ON ctx_tasks(owner_user_id, status, updated_at);

CREATE TABLE IF NOT EXISTS ctx_revisions (
    rev_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES ctx_tasks(task_id),
    owner_user_id TEXT NOT NULL,
    rev INTEGER NOT NULL,
    client_mutation_id TEXT NOT NULL,
    blob_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, rev),
    UNIQUE(owner_user_id, client_mutation_id)    -- 幂等键（契约 §1.4）
);

CREATE TABLE IF NOT EXISTS ctx_entities (
    task_id TEXT NOT NULL REFERENCES ctx_tasks(task_id),
    kind TEXT NOT NULL CHECK(kind IN ('formal','summary','decisions','notes','insights_html')),
    payload_json TEXT NOT NULL,
    current INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (task_id, kind)
);

CREATE TABLE IF NOT EXISTS ctx_assets (
    asset_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(user_id),
    kind TEXT NOT NULL CHECK(kind IN ('hotwords','speaker_aliases','decision_statuses')),
    scope TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('personal','team','enterprise')),
    tenant_id TEXT,
    acl TEXT,
    current_rev INTEGER NOT NULL DEFAULT 0,
    blob_path TEXT NOT NULL,
    content_hash TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_user_id, kind)
);

CREATE TABLE IF NOT EXISTS user_prefs (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    prefs_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 存量迁移台账（裁决④：老数据归 13373013103；告知即过、无回执端点）
CREATE TABLE IF NOT EXISTS legacy_import_ledger (
    legacy_id TEXT PRIMARY KEY,
    target_table TEXT NOT NULL,
    target_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    migrated_at TEXT NOT NULL
);

-- 数据出境审计（QA 域 B 可断言来源）
CREATE TABLE IF NOT EXISTS egress_audit (
    audit_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    user_id TEXT,
    action TEXT NOT NULL,
    object_ref TEXT,
    byte_len INTEGER,
    client_mutation_id TEXT
);
