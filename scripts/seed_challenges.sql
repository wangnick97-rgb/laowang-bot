-- 初始挑战任务种子数据
-- 在 Supabase SQL Editor 中执行

-- 周挑战（需要每周手动更新 start_date/end_date，或后续做自动化）
INSERT INTO challenges (challenge_type, title, description, target_type, target_value, reward_points, start_date, end_date) VALUES
('weekly', '训练打卡3次', '本周完成3次健身打卡', 'workout_count', 3, 50, CURRENT_DATE, CURRENT_DATE + INTERVAL '6 days'),
('weekly', '连续记录饮食5天', '本周记录5天饮食', 'cal_log_days', 5, 40, CURRENT_DATE, CURRENT_DATE + INTERVAL '6 days'),
('weekly', '健康打卡7天', '本周每天健康打卡', 'health_checkin_days', 7, 60, CURRENT_DATE, CURRENT_DATE + INTERVAL '6 days');

-- 月挑战
INSERT INTO challenges (challenge_type, title, description, target_type, target_value, reward_points, start_date, end_date) VALUES
('monthly', '训练打卡15次', '本月完成15次健身打卡', 'workout_count', 15, 200, DATE_TRUNC('month', CURRENT_DATE)::date, (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month - 1 day')::date),
('monthly', '卡路里打卡25天', '本月记录25天饮食', 'cal_log_days', 25, 150, DATE_TRUNC('month', CURRENT_DATE)::date, (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month - 1 day')::date),
('monthly', '健康打卡28天', '本月健康打卡28天', 'health_checkin_days', 28, 300, DATE_TRUNC('month', CURRENT_DATE)::date, (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month - 1 day')::date);

-- 特别挑战（长期）
INSERT INTO challenges (challenge_type, title, description, target_type, target_value, reward_points, start_date, end_date) VALUES
('special', '21天零奶茶挑战', '连续21天健康打卡（坚持健康饮食）', 'health_checkin_days', 21, 200, CURRENT_DATE, CURRENT_DATE + INTERVAL '30 days'),
('special', '百炼成钢', '累计训练100次', 'workout_count', 100, 500, CURRENT_DATE, CURRENT_DATE + INTERVAL '365 days');
