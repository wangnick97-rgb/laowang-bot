-- 老王工具箱 Supabase 数据库初始化
-- 在 Supabase SQL Editor 中执行此文件

-- ── 用户与会员 ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,                         -- Telegram user_id
    username TEXT,
    full_name TEXT,
    membership_status TEXT NOT NULL DEFAULT 'free', -- 'free' | 'member' | 'admin'
    membership_expires_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    daily_usage_count INTEGER NOT NULL DEFAULT 0,
    usage_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
    notes TEXT                                     -- 管理员备注
);

-- ── 对话状态持久化（Bot 重启不丢失用户进度）────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_states (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    current_state INTEGER NOT NULL DEFAULT 0,
    collected_data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, feature)
);

-- ── 使用量追踪（成本控制 + 分析）──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_logs_user_date ON usage_logs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_logs_feature_date ON usage_logs(feature, created_at);

-- ── 新闻缓存（同一天只调用 Claude 一次）────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_cache (
    cache_date DATE NOT NULL,
    category TEXT NOT NULL,           -- 'brief' | 'premarket' | 'postmarket'
    raw_articles JSONB,               -- [{title, url, summary, source}]
    claude_summary TEXT,              -- Claude 处理后的中文简报
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cache_date, category)
);

-- ── 每日打卡记录 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS checkin_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL,
    prompt_sent TEXT,                 -- 发给用户的打卡题
    user_reflection TEXT,            -- 用户的回答
    claude_response TEXT,            -- Claude 的反馈
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, checkin_date)
);

-- ── 调度器运行日志 ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduler_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,             -- 'success' | 'failed' | 'partial'
    users_reached INTEGER DEFAULT 0,
    error_message TEXT,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 启用行级安全（RLS）────────────────────────────────────────────────────────
-- Service role key（Bot 使用）自动绕过 RLS
-- 如果未来 Mini App 使用 anon key，RLS 确保用户只能看自己的数据

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkin_logs ENABLE ROW LEVEL SECURITY;

-- Bot 用 service role key，不需要额外 policy
-- 以下 policy 供未来 Mini App 的 anon 用户使用：
CREATE POLICY "Users can read own data" ON users
    FOR SELECT USING (id = (current_setting('request.jwt.claims', true)::json->>'sub')::bigint);

CREATE POLICY "Users can read own usage" ON usage_logs
    FOR SELECT USING (user_id = (current_setting('request.jwt.claims', true)::json->>'sub')::bigint);

CREATE POLICY "Users can read own checkins" ON checkin_logs
    FOR SELECT USING (user_id = (current_setting('request.jwt.claims', true)::json->>'sub')::bigint);
