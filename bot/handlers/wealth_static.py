"""
创业财富板块 — 静态IP内容
老王持仓 / 投资策略 / 美股开户教程
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.middleware import require_membership


_INVEST_BACK = InlineKeyboardMarkup([
    [InlineKeyboardButton("← 返回投资工具", callback_data="menu_invest")],
])

# ── 老王美股持仓 ──────────────────────────────────────────────────────────────

_PORTFOLIO_TEXT = """💡 *老王美股持仓*
_最近更新: 2026年4月_

━━━━━━━━━━━━━━━━━━━━

🟢 *核心持仓 (长期持有)*

• NVDA (英伟达) — AI算力龙头
• AAPL (苹果) — 生态+现金流
• MSFT (微软) — 企业AI+云
• GOOGL (谷歌) — 搜索+AI+云
• AMZN (亚马逊) — 电商+AWS

🟡 *成长持仓 (中期波段)*

• META (Meta) — 广告复苏+AI
• TSLA (特斯拉) — 看FSD进展
• PLTR (Palantir) — 政府AI

🔵 *观察仓 (小仓位试水)*

• 根据市场情况调整中...

━━━━━━━━━━━━━━━━━━━━

📌 *老王持仓原则*
• 核心仓位占70%，不轻易动
• 成长仓位占20%，跟趋势
• 观察仓占10%，试错用
• 单只股票不超过总仓位25%
• 永远留10%现金应对黑天鹅

⚡ *老王说：持仓不是秘密，纪律才是。你看到了我买什么，但更重要的是我怎么管理仓位。*

_注：以上为个人投资记录，非投资建议。投资有风险。_"""


@require_membership
async def show_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(_PORTFOLIO_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)
    else:
        await update.message.reply_text(_PORTFOLIO_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)


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
• 护城河: 有没有竞争壁垒？(品牌/网络效应/转换成本)
• 管理层: CEO是否有远见+执行力？
• 财务: 收入增长>20%? 自由现金流为正?
• 估值: 当前价格相对于增长是否合理？

💰 *仓位管理*

• 新建仓: 先买1/3，观察一周再加
• 加仓: 只在逻辑不变+价格更优时加
• 止损: 单只亏15%必须重新审视逻辑
• 止盈: 不设固定止盈，跟趋势走

⏰ *买卖时机*

• 买入: 大跌恐慌时 / 财报超预期后回调
• 卖出: 逻辑变了 / 估值严重泡沫 / 有更好的机会

📅 *操作频率*

• 核心仓: 季度审视，不频繁操作
• 成长仓: 月度审视
• 观察仓: 周度审视

━━━━━━━━━━━━━━━━━━━━

⚡ *老王说：投资最重要的不是选对，而是错的时候亏得少。资金管理>选股能力。*

_注：以上为个人投资框架，非投资建议。_"""


@require_membership
async def show_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(_STRATEGY_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)
    else:
        await update.message.reply_text(_STRATEGY_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)


# ── 美股开户教程 ──────────────────────────────────────────────────────────────

_US_STOCK_TEXT = """🏦 *中国用户美股开户教程*

━━━━━━━━━━━━━━━━━━━━

📌 *推荐券商*

🥇 *富途证券 (Futu/moomoo)*
• 优势: 中文界面、社区功能强、港美股都能买
• 开户: 身份证+银行卡，线上10分钟
• 入金: 支持汇款，最低门槛低

🥈 *老虎证券 (Tiger Brokers)*
• 优势: 交易体验好、佣金低、支持期权
• 开户: 身份证+地址证明
• 入金: 支持多种汇款方式

🥉 *盈透证券 (IBKR)*
• 优势: 全球最大互联网券商、品种最全
• 开户: 需要更多材料，审核严格
• 适合: 资金量大、需要专业工具的投资者

━━━━━━━━━━━━━━━━━━━━

📋 *开户步骤*

1️⃣ 选择券商，下载App
2️⃣ 注册账号，填写个人信息
3️⃣ 上传身份证正反面
4️⃣ 填写投资经验问卷
5️⃣ 等待审核（1-3个工作日）
6️⃣ 审核通过，开始入金

💰 *入金方式*

• 银行电汇（最常用，2-5个工作日）
• 每人每年5万美元换汇额度
• 建议: 先小额测试，确认通道畅通再大额转入

⚠️ *注意事项*

• 选择正规持牌券商，确认监管资质
• 美股T+0交易，注意资金管理
• 美股无涨跌停限制，波动可能较大
• 注意美国股息税（通常预扣30%）
• 建议先用模拟盘熟悉操作

━━━━━━━━━━━━━━━━━━━━

⚡ *老王说：开户只是第一步。真正的挑战是开户后如何管理你的钱。先学习，再投入。*"""


@require_membership
async def show_us_stock_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(_US_STOCK_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)
    else:
        await update.message.reply_text(_US_STOCK_TEXT, parse_mode="Markdown", reply_markup=_INVEST_BACK)
