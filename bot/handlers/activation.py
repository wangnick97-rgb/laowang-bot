"""
激活码系统
- Admin: /gencode <plan> [数量] — 生成激活码
- User: /activate <code> — 激活会员
"""
import string
import random
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.client import get_client
from db.users import get_user, is_member

# 套餐定义
PLANS = {
    "month": {"name": "月度会员", "days": 30, "price": "$9.9"},
    "quarter": {"name": "季度会员", "days": 90, "price": "$24.9"},
    "year": {"name": "年度会员", "days": 365, "price": "$79.9"},
    "week": {"name": "周体验", "days": 7, "price": "免费体验"},
}


def _gen_code(length: int = 8) -> str:
    """生成随机激活码：大写字母+数字，8位。"""
    chars = string.ascii_uppercase + string.digits
    # 去掉容易混淆的字符
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "").replace("L", "")
    return "".join(random.choices(chars, k=length))


async def cmd_gencode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin命令：生成激活码。用法: /gencode month [数量]"""
    user = get_user(update.effective_user.id)
    if not user or user.get("membership_status") != "admin":
        return

    args = context.args or []
    if not args:
        plans_text = "\n".join(f"  `{k}` — {v['name']} ({v['days']}天, {v['price']})" for k, v in PLANS.items())
        await update.message.reply_text(
            "🔑 *生成激活码*\n\n"
            f"用法: `/gencode <套餐> [数量]`\n\n"
            f"可用套餐:\n{plans_text}\n\n"
            f"示例:\n"
            f"  `/gencode month` — 生成1个月度码\n"
            f"  `/gencode quarter 5` — 生成5个季度码",
            parse_mode="Markdown",
        )
        return

    plan = args[0].lower()
    if plan not in PLANS:
        await update.message.reply_text(f"❌ 未知套餐: `{plan}`\n可选: {', '.join(PLANS.keys())}", parse_mode="Markdown")
        return

    count = 1
    if len(args) > 1:
        try:
            count = min(int(args[1]), 20)  # 最多一次20个
        except ValueError:
            count = 1

    plan_info = PLANS[plan]
    db = get_client()
    codes = []

    for _ in range(count):
        code = _gen_code()
        # 确保不重复
        while True:
            existing = db.table("activation_codes").select("code").eq("code", code).maybe_single().execute()
            if not existing or not existing.data:
                break
            code = _gen_code()

        db.table("activation_codes").insert({
            "code": code,
            "plan_type": plan,
            "days": plan_info["days"],
            "price": plan_info["price"],
        }).execute()
        codes.append(code)

    if count == 1:
        await update.message.reply_text(
            f"✅ *激活码已生成*\n\n"
            f"📋 套餐: {plan_info['name']} ({plan_info['days']}天)\n"
            f"💰 价格: {plan_info['price']}\n\n"
            f"🔑 激活码: `{codes[0]}`\n\n"
            f"发给用户，让Ta在Bot里发送:\n"
            f"`/activate {codes[0]}`",
            parse_mode="Markdown",
        )
    else:
        codes_text = "\n".join(f"  `{c}`" for c in codes)
        await update.message.reply_text(
            f"✅ *已生成 {count} 个激活码*\n\n"
            f"📋 套餐: {plan_info['name']} ({plan_info['days']}天)\n"
            f"💰 价格: {plan_info['price']}\n\n"
            f"🔑 激活码:\n{codes_text}\n\n"
            f"用户在Bot里发送 `/activate 码` 即可激活",
            parse_mode="Markdown",
        )


async def cmd_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用户命令：使用激活码开通会员。"""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    args = context.args or []

    reply = query.message.reply_text if query else update.message.reply_text

    if not args:
        await reply(
            "🔑 *激活会员*\n\n"
            "请输入你的激活码:\n"
            "`/activate 你的激活码`\n\n"
            "例如: `/activate ABC12345`\n\n"
            "还没有激活码？联系 @scorpia2004 获取",
            parse_mode="Markdown",
        )
        return

    code = args[0].upper().strip()
    db = get_client()

    # 查找激活码
    result = db.table("activation_codes").select("*").eq("code", code).maybe_single().execute()

    if not result or not result.data:
        await update.message.reply_text(
            "❌ *激活码无效*\n\n"
            "请检查激活码是否正确，或联系 @scorpia2004",
            parse_mode="Markdown",
        )
        return

    code_data = result.data

    if code_data.get("used"):
        await update.message.reply_text(
            "❌ *此激活码已被使用*\n\n"
            "每个激活码只能使用一次。\n"
            "如需新的激活码，请联系 @scorpia2004",
            parse_mode="Markdown",
        )
        return

    # 激活会员
    days = code_data["days"]
    plan_name = PLANS.get(code_data["plan_type"], {}).get("name", code_data["plan_type"])

    # 计算新的到期时间
    user = get_user(user_id)
    now = datetime.now(timezone.utc)

    if user and user.get("membership_expires_at"):
        current_expires = datetime.fromisoformat(user["membership_expires_at"].replace("Z", "+00:00"))
        base = max(current_expires, now)
    else:
        base = now

    new_expires = (base + timedelta(days=days)).isoformat()

    # 更新用户会员状态
    db.table("users").update({
        "membership_status": "member",
        "membership_expires_at": new_expires,
    }).eq("id", user_id).execute()

    # 标记激活码已使用
    db.table("activation_codes").update({
        "used": True,
        "used_by": user_id,
        "used_at": now.isoformat(),
    }).eq("code", code).execute()

    expires_str = (base + timedelta(days=days)).strftime("%Y年%m月%d日")

    await update.message.reply_text(
        f"🎉 *会员激活成功！*\n\n"
        f"📋 套餐: *{plan_name}*\n"
        f"⏰ 有效期: *{days}天*\n"
        f"📅 到期日: *{expires_str}*\n\n"
        f"现在你可以使用全部功能了！\n"
        f"发送 /menu 开始使用 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 进入主菜单", callback_data="menu_main")],
        ]),
    )

    # 通知管理员
    from db.users import get_admin_ids
    name = update.effective_user.full_name or update.effective_user.username or str(user_id)
    for admin_id in get_admin_ids():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"✅ *激活码已使用*\n\n"
                    f"用户: {name} (`{user_id}`)\n"
                    f"激活码: `{code}`\n"
                    f"套餐: {plan_name} ({days}天)\n"
                    f"到期: {expires_str}"
                ),
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def cmd_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin命令：查看所有未使用的激活码。"""
    user = get_user(update.effective_user.id)
    if not user or user.get("membership_status") != "admin":
        return

    db = get_client()
    unused = db.table("activation_codes").select("*").eq("used", False).order("created_at", desc=True).limit(30).execute()

    if not unused.data:
        await update.message.reply_text("📋 当前没有未使用的激活码。\n用 `/gencode` 生成新的。", parse_mode="Markdown")
        return

    lines = ["🔑 *未使用的激活码*\n"]
    for c in unused.data:
        plan_name = PLANS.get(c["plan_type"], {}).get("name", c["plan_type"])
        lines.append(f"  `{c['code']}` — {plan_name} ({c['days']}天)")

    lines.append(f"\n共 {len(unused.data)} 个")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
