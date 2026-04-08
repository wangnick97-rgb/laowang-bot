"""
会员开通流程（手动审核）
用户点击"开通会员" → 显示收款信息 + 收款码 → 用户付款后联系管理员 → 管理员 /addmember
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

JOIN_TEXT = """💰 *开通老王工具箱会员*

*会员权益：*
• 10 个专业 AI 工具无限使用
• 每日 AI 财经简报自动推送
• 后续新功能优先体验

*价格：*
• 月卡：$9.9 / 月
• 季卡：$24.9 / 季（省 $5）
• 年卡：$79.9 / 年（省 $40）

*开通方式：*
1️⃣ 扫下方收款码付款
2️⃣ 付款后截图发给 @scorpia2004
3️⃣ 备注你的 Telegram 用户名
4️⃣ 管理员确认后立即开通"""

_QR_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "payment_qr.jpg")


def _buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 联系管理员开通", url="https://t.me/scorpia2004")],
        [InlineKeyboardButton("← 返回", callback_data="menu_main")],
    ])


async def callback_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 先发文字说明
    await query.edit_message_text(
        JOIN_TEXT,
        parse_mode="Markdown",
        reply_markup=_buttons(),
    )

    # 如果有收款码图片，发送图片
    if os.path.exists(_QR_PATH):
        await query.message.reply_photo(
            photo=open(_QR_PATH, "rb"),
            caption="👆 扫码付款后截图发给 @scorpia2004",
            parse_mode="Markdown",
        )
