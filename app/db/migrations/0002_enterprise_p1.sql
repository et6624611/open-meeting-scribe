-- 0002_enterprise_p1.sql — 企业版 P1 团队空间 schema（契约 v1.0 §1/§6/§8）
-- 纪律：除缺口A ctx_assets expand-contract（产品批准的 additive-only 首个例外，§6）外全部 additive。
-- 本文件整体单事务执行（database.py migrate runner 逐迁移 BEGIN/ROLLBACK），失败自动回滚——
-- DevOps 升级三件套（备份前置 + 迁移事务化 + 回滚演练）的首个正式用例。

-- ============ 团队主体（裁决2：tenant 内多团队、自由组合、不挂组织架构） ============
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(user_id),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),  -- 裁决④归档语义，无"解散"
    created_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    role TEXT NOT NULL CHECK(role IN ('viewer','editor','admin')),   -- 三档：只读/可编辑/团队管理员
    added_by TEXT REFERENCES users(user_id),
    joined_at TEXT NOT NULL,
    effective INTEGER NOT NULL DEFAULT 1,   -- 用户停用时置 0（行保留审计，§2 离职撤权）
    PRIMARY KEY (team_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id, effective);

-- ============ 任务与团队承接（§1：ADD COLUMN，scope⇔team_id 一致性由 DAO 强制） ============
ALTER TABLE ctx_tasks ADD COLUMN team_id TEXT REFERENCES teams(team_id);
ALTER TABLE ctx_tasks ADD COLUMN source_task_id TEXT REFERENCES ctx_tasks(task_id);  -- 发布副本追溯锚
CREATE INDEX IF NOT EXISTS idx_ctx_tasks_team ON ctx_tasks(team_id, status, updated_at);

-- 写作者归属拆分（§6 语义修正 B：旧行 owner==actor 恒等，回填即可）
ALTER TABLE ctx_revisions ADD COLUMN actor_user_id TEXT REFERENCES users(user_id);
UPDATE ctx_revisions SET actor_user_id = owner_user_id WHERE actor_user_id IS NULL;

-- ============ 团队留痕（K1 拍板十二值枚举，逐字 = 契约 §8.4；无审批态值） ============
CREATE TABLE IF NOT EXISTS team_edit_audit (
    audit_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    task_id TEXT REFERENCES ctx_tasks(task_id),
    rev INTEGER,
    actor_user_id TEXT NOT NULL REFERENCES users(user_id),
    action TEXT NOT NULL CHECK(action IN (
        'publish','edit','withdraw','decision_publish','decision_withdraw',
        'decision_delete','decision_restore',
        'member_add','member_role_change','member_remove','role_transfer','team_archive'
    )),
    target_ref TEXT,        -- decision_delete/decision_restore 指向的决策条目稳定 ID
    pre_delete_rev INTEGER, -- decision_delete 的删除前 rev；decision_restore=重推该版本（裁决③闭环）
    content_hash TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_audit ON team_edit_audit(team_id, ts);

-- ============ 企业资产收集层（裁决4"只收集不消费"：无读端点，404 by design） ============
CREATE TABLE IF NOT EXISTS enterprise_decision_assets (
    asset_id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL REFERENCES ctx_tasks(task_id),
    source_team_id TEXT NOT NULL REFERENCES teams(team_id),
    source_rev INTEGER NOT NULL,
    decision_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    collected_by TEXT NOT NULL REFERENCES users(user_id),
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'collected' CHECK(status IN ('collected','withdrawn','stale')),
    withdrawn_at TEXT,
    UNIQUE(source_task_id, decision_id)
);

-- ============ 团队共享词表（§4 team-owned asset） ============
CREATE TABLE IF NOT EXISTS team_assets (
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    kind TEXT NOT NULL CHECK(kind IN ('hotwords','speaker_aliases','decision_statuses')),
    current_rev INTEGER NOT NULL DEFAULT 0,
    blob_path TEXT NOT NULL,
    content_hash TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (team_id, kind)
);

-- ============ 缺口A：ctx_assets expand-contract 重建（唯一非 additive 项，§6 产品批准） ============
-- 旧约束 UNIQUE(owner_user_id, kind) + owner_user_id NOT NULL 无法表达团队拥有资产。
-- expand：新结构双归属（owner_user_id 或 team_id 恰一非空）+ 部分唯一索引；搬迁全部存量行；
-- contract：改名替换。存量个人词表内容逐字节保留（QA TB3 断言：迁移前后个人词表 diff=∅）。
CREATE TABLE IF NOT EXISTS ctx_assets_p1 (
    asset_id TEXT PRIMARY KEY,
    owner_user_id TEXT REFERENCES users(user_id),
    team_id TEXT REFERENCES teams(team_id),
    kind TEXT NOT NULL CHECK(kind IN ('hotwords','speaker_aliases','decision_statuses')),
    scope TEXT NOT NULL DEFAULT 'personal' CHECK(scope IN ('personal','team','enterprise')),
    tenant_id TEXT,
    acl TEXT,
    current_rev INTEGER NOT NULL DEFAULT 0,
    blob_path TEXT NOT NULL,
    content_hash TEXT,
    updated_at TEXT NOT NULL,
    CHECK((owner_user_id IS NOT NULL AND team_id IS NULL) OR (team_id IS NOT NULL AND owner_user_id IS NULL))
);
INSERT INTO ctx_assets_p1
    SELECT asset_id, owner_user_id, NULL, kind, scope, tenant_id, acl,
           current_rev, blob_path, content_hash, updated_at
    FROM ctx_assets;
DROP TABLE ctx_assets;
ALTER TABLE ctx_assets_p1 RENAME TO ctx_assets;
CREATE UNIQUE INDEX IF NOT EXISTS ux_assets_owner ON ctx_assets(owner_user_id, kind) WHERE owner_user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_assets_team ON ctx_assets(team_id, kind) WHERE team_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_assets_team ON ctx_assets(team_id);
