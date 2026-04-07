"""
手动导入初始会员
用法: python scripts/seed_members.py

在 .env 配置好 Supabase 后运行。
如何获取 Telegram user_id: 发消息给 @userinfobot
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_client

# ── 在这里填写你的初始会员列表 ────────────────────────────────────────────────
# 格式: (telegram_user_id, username, display_name, membership_status)
# membership_status: "member" 或 "admin"
INITIAL_MEMBERS = [
    # (123456789, "laowang", "老王", "admin"),
    # (987654321, "member_alice", "Alice", "member"),
]


def seed():
    if not INITIAL_MEMBERS:
        print("⚠️  INITIAL_MEMBERS 为空。请先在脚本里填写会员信息。")
        return

    db = get_client()
    inserted = 0
    skipped = 0

    for user_id, username, full_name, status in INITIAL_MEMBERS:
        try:
            db.table("users").upsert({
                "id": user_id,
                "username": username,
                "full_name": full_name,
                "membership_status": status,
                "is_active": True,
            }, on_conflict="id").execute()
            print(f"✅ 导入: {full_name} (@{username}) — {status}")
            inserted += 1
        except Exception as e:
            print(f"❌ 失败: {full_name} — {e}")
            skipped += 1

    print(f"\n完成: {inserted} 导入, {skipped} 失败")


if __name__ == "__main__":
    seed()
