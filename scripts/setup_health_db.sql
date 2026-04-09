-- 老王健康执行系统 — 数据库扩展
-- 在 Supabase SQL Editor 中执行此文件

-- ── 用户健康档案 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    weight DECIMAL(5,1),                -- kg
    height DECIMAL(5,1),                -- cm
    age INTEGER,
    goal TEXT CHECK (goal IN ('bulk', 'cut', 'maintain')),
    experience TEXT CHECK (experience IN ('beginner', 'intermediate', 'advanced')),
    dietary_pref TEXT DEFAULT 'none',   -- none | no_pork | vegetarian
    daily_calories INTEGER,             -- 计算后的每日卡路里目标
    daily_protein INTEGER,              -- 计算后的每日蛋白质目标
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 健身打卡记录 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gym_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE,
    workout_type TEXT NOT NULL,          -- push | pull | legs | full | cardio | rest
    duration_min INTEGER,
    intensity INTEGER CHECK (intensity BETWEEN 1 AND 5),
    notes TEXT,
    points_earned INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, log_date)
);
CREATE INDEX IF NOT EXISTS idx_gym_logs_user_date ON gym_logs(user_id, log_date);

-- ── 健康打卡记录 ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checkin_date DATE NOT NULL DEFAULT CURRENT_DATE,
    mood TEXT CHECK (mood IN ('struggling', 'okay', 'good', 'fire')),
    note TEXT,
    health_streak INTEGER NOT NULL DEFAULT 1,
    points_earned INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, checkin_date)
);
CREATE INDEX IF NOT EXISTS idx_health_checkins_user_date ON health_checkins(user_id, checkin_date);

-- ── 卡路里打卡记录 ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calorie_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE,
    meal_type TEXT CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    food_description TEXT,
    estimated_calories INTEGER,
    estimated_protein DECIMAL(5,1),
    estimated_carbs DECIMAL(5,1),
    estimated_fat DECIMAL(5,1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_calorie_logs_user_date ON calorie_logs(user_id, log_date);

-- ── 在 users 表添加健康相关字段 ───────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS health_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_health_checkin DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS gym_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_gym_date DATE;

-- ── 挑战任务 ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS challenges (
    id SERIAL PRIMARY KEY,
    challenge_type TEXT NOT NULL CHECK (challenge_type IN ('weekly', 'monthly', 'special')),
    title TEXT NOT NULL,
    description TEXT,
    target_type TEXT NOT NULL,           -- workout_count, cal_log_days, health_checkin_days, etc.
    target_value INTEGER NOT NULL,
    reward_points INTEGER NOT NULL DEFAULT 0,
    reward_badge TEXT,                   -- badge key or NULL
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_challenges (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
    current_progress INTEGER NOT NULL DEFAULT 0,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, challenge_id)
);

-- ── 战队 ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    captain_id BIGINT NOT NULL REFERENCES users(id),
    invite_code TEXT UNIQUE NOT NULL,
    max_members INTEGER NOT NULL DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

-- ── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE health_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE gym_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_checkins ENABLE ROW LEVEL SECURITY;
ALTER TABLE calorie_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
