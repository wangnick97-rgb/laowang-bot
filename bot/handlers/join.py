"""
会员开通 — 展示三级会员权益+价格+激活码入口
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

JOIN_TEXT = """💰 *开通老王工具箱*

━━━━━━━━━━━━━━━━━━━━

💎 *会员*
• 全部51个AI工具无限使用（每日20次）
• 老王持仓（季度快照30只）
• 老王投资策略完整版
• 每日情报：早报+盘前+盘后
• 个人成长+健康全部功能

💰 月卡 $9.9 | 季卡 $24.9 | 年卡 $79.9

━━━━━━━━━━━━━━━━━━━━

👑 *私董会*（限50人）
• 会员全部权益
• 🔴 *老王实时持仓+每笔交易推送*
• 老王每周语音分享
• 私董会专属群
• 每月1次15分钟免费咨询
• 老王周报深度推送

💰 月卡 $99 | 季卡 $249 | 年卡 $899

━━━━━━━━━━━━━━━━━━━━

*开通方式：*
1️⃣ 微信联系 @scorpia2004 付款
2️⃣ 收到激活码后发送 `/activate 码`
3️⃣ 自动开通，立即使用"""


def _buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 联系老王开通", url="https://t.me/scorpia2004")],
        [InlineKeyboardButton("🔑 我有激活码", callback_data="feature_activate")],
        [InlineKeyboardButton("← 返回", callback_data="menu_main")],
    ])


async def callback_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        JOIN_TEXT,
        parse_mode="Markdown",
        reply_markup=_buttons(),
    )

    # 如果有收款码图片，发送
    _QR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "payment_qr.jpg")
    if os.path.exists(_QR_PATH):
        await query.message.reply_photo(
            photo=open(_QR_PATH, "rb"),
            caption="👆 扫码付款后联系 @scorpia2004 获取激活码",
        )
