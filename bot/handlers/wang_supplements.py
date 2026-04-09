"""
Feature: 老王20种补给
静态 IP 内容，直接展示。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.middleware import require_membership

_TEXT = """💊 *老王20种补给*

🥩 *蛋白质来源 TOP5*

1. 鸡胸肉 — 性价比之王，100g=31g蛋白质
2. 三文鱼 — Omega3+蛋白质，一鱼两得
3. 鸡蛋 — 最完美的全食，便宜又好用
4. 希腊酸奶 — 肠道+肌肉双修
5. 乳清蛋白粉 — 训练后30min内必备

🥦 *微量营养素 TOP5*

6. 西兰花 — 天然抗雌+高纤维
7. 菠菜 — 铁+镁，恢复利器
8. 蓝莓 — 抗氧化之王
9. 红薯 — 缓释碳水，稳定血糖
10. 牛油果 — 好脂肪+钾

💊 *补剂 TOP5*

11. 肌酸 (5g/天) — 唯一有硬证据的补剂
12. 维生素D3 (2000IU/天) — 大部分人都缺
13. 鱼油 (1-2g/天) — 抗炎+心血管
14. 镁 (400mg/天) — 改善睡眠+恢复
15. 锌 (15mg/天) — 睾酮+免疫

🥤 *日常饮品 TOP5*

16. 黑咖啡 — 训练前最佳燃脂饮品
17. 绿茶 — 代谢+抗氧化
18. 电解质水 — 训练中必备
19. 骨汤 — 关节+肠道修复
20. 纯净水 — 一天3L起步

━━━━━━━━━━━━━━━━━━━━

⚡ *老王说：补剂是锦上添花，不是雪中送炭。先把前10种食物吃对，再考虑后面的补剂。*"""


def _kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍫 零食白名单", callback_data="feature_snacks"),
         InlineKeyboardButton("🧮 蛋白质计算", callback_data="feature_protein")],
        [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
    ])


@require_membership
async def show_supplements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(_TEXT, parse_mode="Markdown", reply_markup=_kb())
    else:
        await update.message.reply_text(_TEXT, parse_mode="Markdown", reply_markup=_kb())
