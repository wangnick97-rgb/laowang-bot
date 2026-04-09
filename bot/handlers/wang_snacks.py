"""
Feature: 老王零食白名单
静态 IP 内容，直接展示。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.middleware import require_membership

_TEXT = """🍫 *老王零食白名单*

✅ *放心吃（减脂期也OK）*

🥛 希腊酸奶（无糖） — 蛋白质炸弹，饱腹感强
🥩 牛肉干（低钠） — 随身蛋白质来源
🍫 黑巧克力 85%+ — 抗氧化+解馋神器
🥜 坚果混合 30g — 好脂肪，别超量
🫘 毛豆/鹰嘴豆 — 纤维+植物蛋白
🍌 香蕉 — 训练前完美碳水
🍎 苹果+花生酱 — 完美加餐组合
🥚 水煮蛋（随时可吃） — 最便宜的蛋白质
🥒 番茄/黄瓜 — 几乎零热量，随便吃
🫧 气泡水 — 戒饮料第一步

━━━━━━━━━━━━━━━━━━━━

❌ *老王黑名单*

🧋 奶茶 — 一杯 = 跑步1小时白费
🍟 薯片 — 碳水+油脂双重暴击
🥤 含糖饮料 — 胰岛素过山车
🍰 蛋糕甜点 — 糖+脂肪，最差组合
🍕 外卖pizza — 你以为是一顿，其实是两顿的热量

━━━━━━━━━━━━━━━━━━━━

⚡ *老王说：零食不是奖励，是你的燃料补给站。选对了是助力，选错了是拖累。*"""


def _kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💊 老王20种补给", callback_data="feature_supplements"),
         InlineKeyboardButton("🧮 蛋白质计算", callback_data="feature_protein")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


@require_membership
async def show_snacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(_TEXT, parse_mode="Markdown", reply_markup=_kb())
    else:
        await update.message.reply_text(_TEXT, parse_mode="Markdown", reply_markup=_kb())
