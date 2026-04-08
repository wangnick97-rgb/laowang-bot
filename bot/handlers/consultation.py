"""
Feature: 老王 1v1 私人咨询（额外付费）

完整预约流程：
  入口 → 服务介绍 → 选择套餐 → 填写咨询主题 → 确认预约 → 通知管理员

支持菜单按钮 + /consult 命令双入口。
"""
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from db.users import get_user, get_admin_ids
from db.client import get_client

logger = logging.getLogger(__name__)

# ── Conversation states ──────────────────────────────────────────────────────
CHOOSE_PACKAGE, ASK_TOPIC, CONFIRM = range(3)

# ── 套餐配置 ──────────────────────────────────────────────────────────────────
PACKAGES = {
    "consult_30": {
        "name": "⚡ 快速咨询 30 分钟",
        "duration": "30 分钟",
        "price": "$109",
        "desc": "聚焦单一问题，快速给出方向和行动建议",
    },
    "consult_60": {
        "name": "🔥 深度咨询 60 分钟",
        "duration": "60 分钟",
        "price": "$299",
        "desc": "系统性梳理问题，制定完整策略和执行计划",
        "tag": "最受欢迎",
    },
    "consult_vip": {
        "name": "👑 VIP 陪跑 3 次",
        "duration": "3 × 60 分钟",
        "price": "$499",
        "desc": "三次深度跟进，陪你从想法到落地，持续复盘",
        "tag": "最超值",
    },
}

# ── 服务介绍页（入口） ────────────────────────────────────────────────────────
INTRO_TEXT = """🎯 *老王 1v1 私人咨询*

━━━━━━━━━━━━━━━━━━━━

跟老王来一场高密度、不废话的 1 对 1 通话。

不是泛泛而谈的「建议」，而是根据你的具体情况，
给你*可以直接执行的方案*。

━━━━━━━━━━━━━━━━━━━━

🔍 *咨询方向*

📊 *投资策略*
交易体系搭建 · 仓位管理 · 风控纪律 · 心态调整

✍️ *自媒体 & 内容变现*
账号定位 · 爆款方法论 · 变现路径 · 从 0 到 1 起号

🏠 *Airbnb & 副业*
选房策略 · 定价优化 · 运营效率 · 从第 1 套到第 N 套

🚀 *创业 & 商业*
商业模式梳理 · 产品定位 · 冷启动策略 · 融资准备

━━━━━━━━━━━━━━━━━━━━

💬 *过往咨询反馈*

_「一次通话抵我自己摸索半年。」_
_「老王直接指出了我定位的核心问题，省了几万块试错成本。」_
_「不说废话，全是干货，通话完就能动手干。」_

━━━━━━━━━━━━━━━━━━━━

👇 选择适合你的咨询套餐"""


def _package_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for key, pkg in PACKAGES.items():
        tag = f" 【{pkg['tag']}】" if pkg.get("tag") else ""
        buttons.append([InlineKeyboardButton(
            f"{pkg['name']}  {pkg['price']}{tag}",
            callback_data=key,
        )])
    buttons.append([InlineKeyboardButton("← 返回主菜单", callback_data="cancel_consult")])
    return InlineKeyboardMarkup(buttons)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 确认预约", callback_data="consult_confirm")],
        [InlineKeyboardButton("🔄 重新选择", callback_data="consult_restart")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_consult")],
    ])


def _done_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 联系老王", url="https://t.me/scorpia2004")],
        [InlineKeyboardButton("← 返回主菜单", callback_data="menu_main")],
    ])


# ── Step 1: 服务介绍 → 选套餐 ────────────────────────────────────────────────

async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            INTRO_TEXT,
            parse_mode="Markdown",
            reply_markup=_package_keyboard(),
        )
    else:
        await update.message.reply_text(
            INTRO_TEXT,
            parse_mode="Markdown",
            reply_markup=_package_keyboard(),
        )
    return CHOOSE_PACKAGE


# ── Step 2: 选套餐 → 填写咨询主题 ────────────────────────────────────────────

async def choose_package(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    pkg_key = query.data

    if pkg_key not in PACKAGES:
        return CHOOSE_PACKAGE

    pkg = PACKAGES[pkg_key]
    context.user_data["consult_package"] = pkg_key

    await query.edit_message_text(
        f"📋 *你选择了：{pkg['name']}*\n\n"
        f"⏱ 时长：{pkg['duration']}\n"
        f"💰 费用：{pkg['price']}\n"
        f"📌 {pkg['desc']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"请用 *2-3 句话* 描述你想咨询的问题或方向：\n\n"
        f"例：\n"
        f"_• 我想做 AI 工具类自媒体，但不确定怎么定位和变现_\n"
        f"_• 在洛杉矶做 Airbnb，想聊选房策略和运营优化_\n"
        f"_• 做了 3 年交易，总是拿不住盈利单，想解决心态问题_\n\n"
        f"👇 发给我你的咨询主题",
        parse_mode="Markdown",
    )
    return ASK_TOPIC


# ── Step 3: 填写主题 → 确认 ──────────────────────────────────────────────────

async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    topic = update.message.text.strip()
    if len(topic) < 5:
        await update.message.reply_text(
            "请稍微详细描述一下你想咨询的问题（至少 5 个字），这样老王可以提前准备 🙏"
        )
        return ASK_TOPIC

    context.user_data["consult_topic"] = topic

    pkg_key = context.user_data.get("consult_package", "consult_60")
    pkg = PACKAGES[pkg_key]
    tg_user = update.effective_user
    name = tg_user.full_name or tg_user.username or str(tg_user.id)

    await update.message.reply_text(
        f"📝 *预约确认*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 姓名：{name}\n"
        f"📦 套餐：{pkg['name']}\n"
        f"⏱ 时长：{pkg['duration']}\n"
        f"💰 费用：{pkg['price']}\n\n"
        f"💬 咨询主题：\n_{topic}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"确认无误后点击「确认预约」，\n"
        f"老王会在 24 小时内联系你安排时间。",
        parse_mode="Markdown",
        reply_markup=_confirm_keyboard(),
    )
    return CONFIRM


# ── Step 4: 确认预约 → 通知管理员 ────────────────────────────────────────────

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    tg_user = update.effective_user
    pkg_key = context.user_data.get("consult_package", "consult_60")
    pkg = PACKAGES[pkg_key]
    topic = context.user_data.get("consult_topic", "（未填写）")
    name = tg_user.full_name or tg_user.username or str(tg_user.id)
    uname = f"@{tg_user.username}" if tg_user.username else "无用户名"

    # 保存预约到数据库
    try:
        db = get_client()
        db.table("consultation_bookings").insert({
            "user_id": tg_user.id,
            "package": pkg_key,
            "topic": topic,
            "status": "pending",
        }).execute()
    except Exception as e:
        logger.warning("Failed to save booking: %s", e)

    # 给用户确认
    await query.edit_message_text(
        f"✅ *预约成功！*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 {pkg['name']}\n"
        f"💰 {pkg['price']}\n\n"
        f"*接下来：*\n"
        f"1️⃣ 老王会在 *24 小时内* 私信你确认时间\n"
        f"2️⃣ 确认时间后完成付款\n"
        f"3️⃣ 通话前老王会提前了解你的情况\n"
        f"4️⃣ 通话后你会收到一份*文字总结和行动清单*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"如有问题可以直接联系老王 👇",
        parse_mode="Markdown",
        reply_markup=_done_keyboard(),
    )

    # 通知管理员
    admin_text = (
        f"🔔 *新咨询预约*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 用户：{name}（{uname}）\n"
        f"🆔 ID：`{tg_user.id}`\n"
        f"📦 套餐：{pkg['name']}\n"
        f"⏱ 时长：{pkg['duration']}\n"
        f"💰 费用：{pkg['price']}\n\n"
        f"💬 *咨询主题：*\n_{topic}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 提交时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"💬 联系用户：tg://user?id={tg_user.id}"
    )
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_id, text=admin_text, parse_mode="Markdown",
            )
        except Exception:
            logger.warning("Failed to notify admin %s about booking", admin_id)

    context.user_data.pop("consult_package", None)
    context.user_data.pop("consult_topic", None)
    return ConversationHandler.END


# ── 重新选择 ──────────────────────────────────────────────────────────────────

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await entry(update, context)


# ── 取消 ──────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("已取消。发送 /menu 返回主菜单。")
    else:
        await update.message.reply_text("已取消。发送 /menu 返回主菜单。")
    context.user_data.pop("consult_package", None)
    context.user_data.pop("consult_topic", None)
    return ConversationHandler.END


# ── ConversationHandler 构造 ──────────────────────────────────────────────────

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("consult", entry),
            CallbackQueryHandler(entry, pattern="^feature_consult$"),
        ],
        states={
            CHOOSE_PACKAGE: [
                CallbackQueryHandler(choose_package, pattern="^consult_(30|60|vip)$"),
            ],
            ASK_TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_booking, pattern="^consult_confirm$"),
                CallbackQueryHandler(restart, pattern="^consult_restart$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("menu", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel_consult$"),
        ],
        conversation_timeout=600,
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )
