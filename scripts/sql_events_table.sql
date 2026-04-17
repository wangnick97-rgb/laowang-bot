-- 埋点事件表：记录 H5 用户行为以便做漏斗/留存分析
-- 执行位置：Supabase Dashboard → SQL Editor → New query → 粘贴 → Run

CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT,
  event       TEXT NOT NULL,
  props       JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_user_id    ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_event      ON events(event);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC);

-- 常见查询示例（埋点收集后用）：
--
-- 1. 看每个功能被点开多少次：
-- SELECT props->>'key' AS feature, COUNT(*)
-- FROM events WHERE event='feature_open'
-- GROUP BY 1 ORDER BY 2 DESC;
--
-- 2. 看会员升级按钮点击到付款的漏斗：
-- SELECT event, COUNT(DISTINCT user_id)
-- FROM events WHERE event IN ('membership_view','membership_upgrade_click')
-- GROUP BY 1;
--
-- 3. 看新手礼包完成率：
-- SELECT DATE(created_at) AS d, COUNT(*) AS claimed
-- FROM events WHERE event='onboarding_claimed'
-- GROUP BY 1 ORDER BY 1 DESC;
