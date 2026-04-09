"""
创业财富板块 — 老王持仓(分层) / 投资策略 / 美股开户 / 交易信号
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.middleware import require_membership
from db.users import get_user
from db.client import get_client


_INVEST_BACK = InlineKeyboardMarkup([
    [InlineKeyboardButton("← 返回投资工具", callback_data="menu_invest")],
])


def _get_tier(user_id: int) -> str:
    """获取用户会员等级: free/member/vip/admin"""
    user = get_user(user_id)
    if not user:
        return "free"
    if user.get("membership_status") == "admin":
        return "admin"
    return user.get("membership_tier", "free")


# ── 老王30只核心股票池 ────────────────────────────────────────────────────────

_FULL_PORTFOLIO = [
    {"ticker": "NVDA", "name": "英伟达", "direction": "🟢 持有", "weight": "核心", "note": "AI算力龙头"},
    {"ticker": "AAPL", "name": "苹果", "direction": "🟢 持有", "weight": "核心", "note": "生态+现金流"},
    {"ticker": "MSFT", "name": "微软", "direction": "🟢 持有", "weight": "核心", "note": "企业AI+云"},
    {"ticker": "GOOGL", "name": "谷歌", "direction": "🟢 持有", "weight": "核心", "note": "搜索+AI+云"},
    {"ticker": "AMZN", "name": "亚马逊", "direction": "🟢 持有", "weight": "核心", "note": "电商+AWS"},
    {"ticker": "META", "name": "Meta", "direction": "🟢 持有", "weight": "成长", "note": "广告+AI"},
    {"ticker": "TSLA", "name": "特斯拉", "direction": "🟡 观望", "weight": "成长", "note": "看FSD进展"},
    {"ticker": "PLTR", "name": "Palantir", "direction": "🟢 持有", "weight": "成长", "note": "政府AI"},
    {"ticker": "CRM", "name": "Salesforce", "direction": "🟢 持有", "weight": "成长", "note": "企业SaaS+AI"},
    {"ticker": "AMD", "name": "AMD", "direction": "🟢 持有", "weight": "核心", "note": "AI芯片第二"},
    {"ticker": "AVGO", "name": "博通", "direction": "🟢 持有", "weight": "核心", "note": "定制AI芯片"},
    {"ticker": "NFLX", "name": "Netflix", "direction": "🟢 持有", "weight": "成长", "note": "内容+广告"},
    {"ticker": "COST", "name": "Costco", "direction": "🟢 持有", "weight": "防守", "note": "消费必需品"},
    {"ticker": "LLY", "name": "礼来", "direction": "🟢 持有", "weight": "成长", "note": "减肥药龙头"},
    {"ticker": "V", "name": "Visa", "direction": "🟢 持有", "weight": "防守", "note": "支付垄断"},
    {"ticker": "JPM", "name": "摩根大通", "direction": "🟢 持有", "weight": "防守", "note": "银行龙头"},
    {"ticker": "UNH", "name": "联合健康", "direction": "🟡 观望", "weight": "观察", "note": "医疗保险"},
    {"ticker": "UBER", "name": "Uber", "direction": "🟢 持有", "weight": "成长", "note": "出行+外卖"},
    {"ticker": "ABNB", "name": "Airbnb", "direction": "🟡 观望", "weight": "观察", "note": "旅游复苏"},
    {"ticker": "SHOP", "name": "Shopify", "direction": "🟢 持有", "weight": "成长", "note": "电商基础设施"},
    {"ticker": "SQ", "name": "Block", "direction": "🟡 观望", "weight": "观察", "note": "支付+比特币"},
    {"ticker": "SNOW", "name": "Snowflake", "direction": "🟡 观望", "weight": "观察", "note": "数据云"},
    {"ticker": "COIN", "name": "Coinbase", "direction": "🟡 观望", "weight": "观察", "note": "加密交易所"},
    {"ticker": "NET", "name": "Cloudflare", "direction": "🟢 持有", "weight": "成长", "note": "网络安全+CDN"},
    {"ticker": "DDOG", "name": "Datadog", "direction": "🟢 持有", "weight": "成长", "note": "可观测性"},
    {"ticker": "PANW", "name": "Palo Alto", "direction": "🟢 持有", "weight": "成长", "note": "网络安全"},
    {"ticker": "MDB", "name": "MongoDB", "direction": "🟡 观望", "weight": "观察", "note": "数据库"},
    {"ticker": "CRWD", "name": "CrowdStrike", "direction": "🟢 持有", "weight": "成长", "note": "端点安全"},
    {"ticker": "ARM", "name": "ARM", "direction": "🟢 持有", "weight": "核心", "note": "芯片架构"},
    {"ticker": "MELI", "name": "MercadoLibre", "direction": "🟢 持有", "weight": "成长", "note": "拉美电商"},
]

_FREE_COUNT = 5  # 免费用户可看5只


@require_membership
async def show_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    reply = query.message.reply_text if query else update.message.reply_text

    user_id = update.effective_user.id
    tier = _get_tier(user_id)

    if tier in ("vip", "admin"):
        # 私董会：完整持仓 + 最近交易信号
        lines = ["👑 *老王实时持仓* | 私董会专属\n"]

        for cat in ["核心", "成长", "防守", "观察"]:
            cat_stocks = [s for s in _FULL_PORTFOLIO if s["weight"] == cat]
            if cat_stocks:
                lines.append(f"\n*{cat}仓位:*")
                for s in cat_stocks:
                    lines.append(f"  {s['direction']} `{s['ticker']}` {s['name']} — {s['note']}")

        # 最近交易信号
        db = get_client()
        signals = db.table("trade_signals").select("*").order("created_at", desc=True).limit(5).execute()
        if signals.data:
            lines.append("\n━━━━━━━━━━━━━━━━━━━━")
            lines.append("\n📡 *最近交易信号:*\n")
            for s in signals.data:
                emoji = "🟢" if s["direction"] == "buy" else "🔴"
                ts = s["created_at"][:10]
                lines.append(f"  {emoji} {s['action']} `{s['ticker']}` {s.get('price','')} ({ts})")
                if s.get("reason"):
                    lines.append(f"     _{s['reason']}_")

        lines.append("\n\n⚡ *实时交易会第一时间推送到私董群*")
        await reply("\n".join(lines), parse_mode="Markdown", reply_markup=_INVEST_BACK)

    elif tier in ("member",):
        # 普通会员：季度完整持仓快照
        lines = ["💎 *老王持仓* | 季度快照\n"]

        for cat in ["核心", "成长", "防守", "观察"]:
            cat_stocks = [s for s in _FULL_PORTFOLIO if s["weight"] == cat]
            if cat_stocks:
                lines.append(f"\n*{cat}仓位:*")
                for s in cat_stocks:
                    lines.append(f"  {s['direction']} `{s['ticker']}` {s['name']}")

        lines.append(f"\n共 {len(_FULL_PORTFOLIO)} 只 | 季度更新")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("\n🔒 *升级私董会* 可查看实时持仓+每笔交易推送")
        lines.append("联系 @scorpia2004 了解详情")

        await reply("\n".join(lines), parse_mode="Markdown", reply_markup=_INVEST_BACK)

    else:
        # 免费用户：只看5只
        preview = _FULL_PORTFOLIO[:_FREE_COUNT]
        lines = ["💡 *老王持仓* | 预览\n"]
        for s in preview:
            lines.append(f"  {s['direction']} `{s['ticker']}` {s['name']} — {s['note']}")

        remaining = len(_FULL_PORTFOLIO) - _FREE_COUNT
        lines.append(f"\n🔒 还有 *{remaining}只* 需要会员查看")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("\n💎 *会员* — 查看全部季度持仓")
        lines.append("👑 *私董会* — 实时持仓+交易推送")

        await reply(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 开通会员", callback_data="join_member")],
                [InlineKeyboardButton("← 返回投资工具", callback_data="menu_invest")],
            ]),
        )


# ── 老王投资策略 ──────────────────────────────────────────────────────────────

_STRATEGY_TEXT = """📋 *老王投资策略*

━━━━━━━━━━━━━━━━━━━━

🧠 *投资哲学*

1. 只投自己能理解的公司
2. 好公司+好价格 > 普通公司+超低价格
3. 时间是朋友，频繁交易是敌人
4. 永远控制下行风险

📊 *选股框架*

• 行业: 是否在长期增长赛道？(AI/云/SaaS)
• 护城河: 有没有竞争壁垒？
• 管理层: CEO是否有远见+执行力？
• 财务: 收入增长>20%? 自由现金流为正?
• 估值: 当前价格相对于增长是否合理？

💰 *仓位管理*

• 新建仓: 先买1/3，观察再加
• 止损: 单只亏15%必须重新审视
• 核心仓70% / 成长仓20% / 观察仓10%

━━━━━━━━━━━━━━━━━━━━

⚡ *老王说：投资最重要的不是选对，而是错的时候亏得少。*

_注：个人投资框架，非投资建议。_"""


@require_membership
async def show_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    reply = query.message.reply_text if query else update.message.reply_text
    await reply(_STRATEGY_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)


# ── 美股开户教程 ──────────────────────────────────────────────────────────────

_US_STOCK_TEXT = """🏦 *中国用户美股开户教程*

━━━━━━━━━━━━━━━━━━━━

📌 *推荐券商*

🥇 *富途证券 (moomoo)* — 中文界面、社区强
🥈 *老虎证券* — 交易体验好、佣金低
🥉 *盈透证券 (IBKR)* — 全球最大、品种最全

📋 *开户步骤*

1️⃣ 选择券商，下载App
2️⃣ 注册账号，上传身份证
3️⃣ 填写投资经验问卷
4️⃣ 等待审核（1-3个工作日）
5️⃣ 银行电汇入金

💰 *入金: 每人每年5万美元换汇额度*

⚠️ *注意*
• 选正规持牌券商
• 美股T+0，无涨跌停
• 股息税通常预扣30%
• 先用模拟盘熟悉

⚡ *老王说：开户只是第一步。真正的挑战是开户后如何管理你的钱。*"""


@require_membership
async def show_us_stock_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    reply = query.message.reply_text if query else update.message.reply_text
    await reply(_US_STOCK_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)


# ── 自动交易脚本（敬请期待）────────────────────────────────────────────────────

async def show_autotrading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    reply = query.message.reply_text if query else update.message.reply_text
    await reply(
        "🤖 *老王自动交易脚本*\n\n"
        "老王自研的美股Day Trading自动化系统，正在内测中。\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 *功能预告:*\n"
        "• 自动识别日内交易信号\n"
        "• 实时监控+自动执行\n"
        "• 风控系统内置\n"
        "• 回测数据公开透明\n\n"
        "💰 *获取方式:*\n"
        "• 单独购买（价格待定）\n"
        "• 👑 私董会积分兑换\n\n"
        "🔔 *上线后第一时间通知所有会员*\n\n"
        "⚡ 老王说：好的交易系统不会让你暴富，但会让你不暴亏。",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("← 返回投资工具", callback_data="menu_invest")],
        ]),
    )


# ── Admin: 发布交易信号 ──────────────────────────────────────────────────────

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin命令：发布交易信号。用法: /signal buy NVDA $950 理由"""
    user = get_user(update.effective_user.id)
    if not user or user.get("membership_status") != "admin":
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "📡 *发布交易信号*\n\n"
            "用法: `/signal <buy/sell/add/trim> <ticker> [价格] [理由]`\n\n"
            "示例:\n"
            "  `/signal buy NVDA $950 AI需求持续增长`\n"
            "  `/signal sell TSLA FSD进展低于预期`\n"
            "  `/signal add AAPL $185 回调加仓`",
            parse_mode="Markdown",
        )
        return

    action = args[0].lower()
    ticker = args[1].upper()
    price = ""
    reason = ""

    remaining = args[2:]
    for i, a in enumerate(remaining):
        if a.startswith("$"):
            price = a
        else:
            reason = " ".join(remaining[i:])
            break

    direction = "buy" if action in ("buy", "add") else "sell"

    db = get_client()
    db.table("trade_signals").insert({
        "action": action,
        "ticker": ticker,
        "direction": direction,
        "price": price,
        "reason": reason,
    }).execute()

    action_names = {"buy": "买入", "sell": "卖出", "add": "加仓", "trim": "减仓"}
    action_emoji = {"buy": "🟢", "sell": "🔴", "add": "🟢", "trim": "🟡"}

    signal_text = (
        f"📡 *老王交易信号*\n\n"
        f"{action_emoji.get(action, '📡')} *{action_names.get(action, action)}* `{ticker}` {price}\n"
    )
    if reason:
        signal_text += f"💬 理由: _{reason}_\n"
    signal_text += f"\n⚡ 仅供私董会成员参考，非投资建议。"

    # 推送给所有私董会成员
    vip_users = db.table("users").select("id").in_("membership_tier", ["vip", "admin"]).eq("is_active", True).execute()
    reached = 0
    for u in (vip_users.data or []):
        try:
            await context.bot.send_message(
                chat_id=u["id"], text=signal_text, parse_mode="Markdown",
            )
            reached += 1
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ 信号已发布并推送给 {reached} 位私董会成员\n\n"
        f"{action_emoji.get(action, '')} {action_names.get(action, action)} `{ticker}` {price}",
        parse_mode="Markdown",
    )
