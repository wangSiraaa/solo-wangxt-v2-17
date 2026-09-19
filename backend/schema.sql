-- 研究数据授权与撤回演示平台 —— 数据库结构
-- PostgreSQL 15

-- 触发函数：更新 updated_at
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============ 身份与角色 ============
CREATE TABLE participants (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,          -- 对外展示的脱敏代号，如 P-1001
    display_name    TEXT NOT NULL,                 -- 演示用化名
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE researchers (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    institution     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE admins (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 统一登录身份（本地演示：无密码，前端用 X-Test-Identity 头指定）
CREATE TABLE identities (
    id              BIGSERIAL PRIMARY KEY,
    identity_key    TEXT NOT NULL UNIQUE,          -- 如 participant-1001 / researcher-01 / admin-01
    role            TEXT NOT NULL CHECK (role IN ('participant','researcher','admin')),
    participant_id  BIGINT REFERENCES participants(id),
    researcher_id   BIGINT REFERENCES researchers(id),
    admin_id        BIGINT REFERENCES admins(id),
    label           TEXT NOT NULL,
    CONSTRAINT identities_role_shape CHECK (
        (role = 'participant' AND participant_id IS NOT NULL) OR
        (role = 'researcher'  AND researcher_id  IS NOT NULL) OR
        (role = 'admin'       AND admin_id       IS NOT NULL)
    )
);

-- ============ 脱敏样本数据 ============
CREATE TABLE datasets (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    is_deidentified BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE dataset_records (
    id              BIGSERIAL PRIMARY KEY,
    dataset_id      BIGINT NOT NULL REFERENCES datasets(id),
    participant_id  BIGINT NOT NULL REFERENCES participants(id),
    row_no          INT  NOT NULL,
    payload         JSONB NOT NULL,               -- 脱敏后的字段（年龄段/区间值，无姓名联系方式）
    UNIQUE (dataset_id, row_no)
);

CREATE TABLE purposes (
    id              BIGSERIAL PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT ''
);

-- ============ 授权（版本化） ============
-- 每位参与者 × 每类用途一行“当前授权状态”，consent_events 保留全部版本历史
CREATE TABLE consents (
    id              BIGSERIAL PRIMARY KEY,
    participant_id  BIGINT NOT NULL REFERENCES participants(id),
    purpose_id      BIGINT NOT NULL REFERENCES purposes(id),
    version         INT NOT NULL DEFAULT 1,
    status          TEXT NOT NULL CHECK (status IN ('granted','withdrawn')),
    granted_at      TIMESTAMPTZ,
    withdrawn_at    TIMESTAMPTZ,
    withdraw_reason TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (participant_id, purpose_id)
);

CREATE TABLE consent_events (
    id              BIGSERIAL PRIMARY KEY,
    consent_id      BIGINT NOT NULL REFERENCES consents(id),
    version         INT NOT NULL DEFAULT 1,
    action          TEXT NOT NULL CHECK (action IN ('granted','withdrawn')),
    actor_identity_id BIGINT REFERENCES identities(id),
    reason          TEXT NOT NULL DEFAULT '',
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_consent_events_consent ON consent_events(consent_id, version);

-- 授权并发锁位：撤回事务与导出/下载检查点事务都先锁这些行，保证全局一致的加锁顺序
-- （先锁 consent_slots，再改 export_jobs），避免并发事务各执一锁互相绕过
CREATE TABLE consent_slots (
    participant_id  BIGINT NOT NULL REFERENCES participants(id),
    purpose_id      BIGINT NOT NULL REFERENCES purposes(id),
    PRIMARY KEY (participant_id, purpose_id)
);

-- ============ 数据访问申请与限时授权 ============
CREATE TABLE access_requests (
    id              BIGSERIAL PRIMARY KEY,
    researcher_id   BIGINT NOT NULL REFERENCES researchers(id),
    dataset_id      BIGINT NOT NULL REFERENCES datasets(id),
    purpose_id      BIGINT NOT NULL REFERENCES purposes(id),
    justification   TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at      TIMESTAMPTZ,
    decided_by      BIGINT REFERENCES admins(id),
    grant_expires_at TIMESTAMPTZ,                 -- 限时下载窗口
    reviewer_note   TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (researcher_id, dataset_id, purpose_id)
);

-- ============ 导出任务（队列） ============
CREATE TABLE export_jobs (
    id              BIGSERIAL PRIMARY KEY,
    request_id      BIGINT NOT NULL REFERENCES access_requests(id),
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','cancelled','complete','failed')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    record_count    INT,
    file_path       TEXT,
    file_sha256     TEXT,
    denial_reason   TEXT NOT NULL DEFAULT '',      -- participant_withdrew / grant_expired / link_revoked...
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_export_jobs_status ON export_jobs(status, requested_at);
CREATE INDEX idx_export_jobs_request ON export_jobs(request_id);

-- ============ 下载链接（每次访问都要重新校验授权） ============
CREATE TABLE download_links (
    id                  BIGSERIAL PRIMARY KEY,
    token               TEXT NOT NULL UNIQUE,
    export_id           BIGINT NOT NULL REFERENCES export_jobs(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,      -- 链接本身有效期（随授权窗口）
    revoked             BOOLEAN NOT NULL DEFAULT FALSE,
    last_accessed_at    TIMESTAMPTZ,
    access_count        INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_download_links_export ON download_links(export_id);

-- ============ 访问事件（只追加，撤回不删除历史） ============
CREATE TABLE access_events (
    id                  BIGSERIAL PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_identity_id   BIGINT REFERENCES identities(id),
    action              TEXT NOT NULL CHECK (action IN (
        'request_submitted','request_approved','request_rejected',
        'export_queued','export_started','export_completed','export_cancelled',
        'download','download_denied','link_revoked',
        'consent_granted','consent_withdrawn'
    )),
    request_id          BIGINT REFERENCES access_requests(id),
    export_id           BIGINT REFERENCES export_jobs(id),
    link_id             BIGINT REFERENCES download_links(id),
    consent_id          BIGINT REFERENCES consents(id),
    detail              JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_access_events_time ON access_events(occurred_at DESC);
CREATE INDEX idx_access_events_actor ON access_events(actor_identity_id, occurred_at DESC);

CREATE TRIGGER trg_consents_updated BEFORE UPDATE ON consents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_requests_updated BEFORE UPDATE ON access_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_exports_updated BEFORE UPDATE ON export_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
