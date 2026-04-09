"""
Feature: 老王训练计划库
5套固定周期计划（静态内容），选择阶段后展示完整周计划。
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from bot.middleware import require_membership

_MENU_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 新手破冰 (0-3月)", callback_data="wplan_beginner")],
    [InlineKeyboardButton("🟡 基础构建 (3-6月)", callback_data="wplan_foundation")],
    [InlineKeyboardButton("🔵 进阶雕刻 (6-12月)", callback_data="wplan_intermediate")],
    [InlineKeyboardButton("🔴 高手打磨 (1年+)", callback_data="wplan_advanced")],
    [InlineKeyboardButton("⚫ 老王同款", callback_data="wplan_wang")],
    [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
])

_BACK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("← 返回计划列表", callback_data="feature_wangplan"),
     InlineKeyboardButton("🏋️ 今日训练", callback_data="feature_workout")],
    [InlineKeyboardButton("← 返回健康菜单", callback_data="menu_health")],
])

_PLANS = {
    "wplan_beginner": (
        "🟢 *新手破冰计划 | 全身3天/周*\n"
        "适合：0-3个月训练经验\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 *周一 — 全身A*\n"
        "1. 杠铃深蹲 3×10\n"
        "2. 杠铃卧推 3×10\n"
        "3. 哑铃划船 3×10\n"
        "4. 肩推(哑铃) 3×10\n"
        "5. 平板支撑 3×30s\n\n"
        "📅 *周三 — 全身B*\n"
        "1. 罗马尼亚硬拉 3×10\n"
        "2. 上斜哑铃卧推 3×10\n"
        "3. 高位下拉 3×10\n"
        "4. 哑铃侧平举 3×12\n"
        "5. 卷腹 3×15\n\n"
        "📅 *周五 — 全身C*\n"
        "1. 腿举 3×12\n"
        "2. 双杠臂屈伸 3×8\n"
        "3. 坐姿划船 3×10\n"
        "4. 面拉 3×15\n"
        "5. 农夫行走 3×30s\n\n"
        "📅 *周二四六日 — 休息*\n"
        "可做轻度有氧(散步/拉伸20min)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 *要点*\n"
        "• 每个动作优先学好姿势，不急加重\n"
        "• 组间休息60-90秒\n"
        "• 渐进超负荷：每周尝试加2.5kg或多做1rep\n\n"
        "⚡ *老王说：新手最大的敌人不是重量，是不稳定的出勤率。*"
    ),

    "wplan_foundation": (
        "🟡 *基础构建计划 | 上下分化4天/周*\n"
        "适合：3-6个月训练经验\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 *周一 — 上肢A(推)*\n"
        "1. 杠铃卧推 4×8\n"
        "2. 上斜哑铃卧推 3×10\n"
        "3. 坐姿肩推 3×10\n"
        "4. 绳索夹胸 3×12\n"
        "5. 三头下压 3×12\n\n"
        "📅 *周二 — 下肢A*\n"
        "1. 杠铃深蹲 4×8\n"
        "2. 罗马尼亚硬拉 3×10\n"
        "3. 腿举 3×12\n"
        "4. 腿弯举 3×12\n"
        "5. 小腿提踵 4×15\n\n"
        "📅 *周四 — 上肢B(拉)*\n"
        "1. 引体向上/高位下拉 4×8\n"
        "2. 杠铃划船 3×10\n"
        "3. 坐姿划船 3×10\n"
        "4. 面拉 3×15\n"
        "5. 二头弯举 3×12\n\n"
        "📅 *周五 — 下肢B*\n"
        "1. 前蹲/哈克深蹲 4×8\n"
        "2. 直腿硬拉 3×10\n"
        "3. 保加利亚分腿蹲 3×10/侧\n"
        "4. 腿伸展 3×12\n"
        "5. 悬垂举腿 3×12\n\n"
        "📅 *周三六日 — 休息/轻有氧*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 *要点*\n"
        "• 复合动作优先，逐渐增加孤立动作\n"
        "• 组间休息：复合60-90s，孤立45-60s\n"
        "• 每周增加总训练量(组数或重量)\n\n"
        "⚡ *老王说：这个阶段决定了你的力量底子。别急着雕刻，先把地基打牢。*"
    ),

    "wplan_intermediate": (
        "🔵 *进阶雕刻计划 | PPL 5天/周*\n"
        "适合：6-12个月训练经验\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 *周一 — Push(推)*\n"
        "1. 杠铃卧推 4×6-8\n"
        "2. 上斜哑铃卧推 3×8-10\n"
        "3. 绳索夹胸 3×12-15\n"
        "4. 坐姿肩推 4×8\n"
        "5. 侧平举 4×12-15\n"
        "6. 三头绳索下压 3×12\n\n"
        "📅 *周二 — Pull(拉)*\n"
        "1. 硬拉 4×5\n"
        "2. 引体向上 4×力竭\n"
        "3. 杠铃划船 3×8\n"
        "4. 坐姿划船 3×10\n"
        "5. 面拉 3×15\n"
        "6. 二头锤式弯举 3×12\n\n"
        "📅 *周三 — Legs(腿)*\n"
        "1. 杠铃深蹲 4×6-8\n"
        "2. 腿举 3×10-12\n"
        "3. 罗马尼亚硬拉 3×10\n"
        "4. 腿弯举 3×12\n"
        "5. 腿伸展 3×12\n"
        "6. 小腿提踵 4×15\n\n"
        "📅 *周四 — 休息*\n\n"
        "📅 *周五 — Push 2(轻重量高次数)*\n"
        "上斜卧推 3×12 + 蝴蝶机 3×15 + 阿诺德推 3×12 + 侧平举超级组 4×15 + 三头过头臂屈伸 3×12\n\n"
        "📅 *周六 — Pull 2 / Arms*\n"
        "高位下拉 3×12 + T杠划船 3×10 + 面拉 3×15 + 二头杠铃弯举 4×10 + 三头双杠 3×力竭\n\n"
        "📅 *周日 — 休息*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ *老王说：PPL是最经典的分化。在这个框架里，你会找到属于自己的节奏。*"
    ),

    "wplan_advanced": (
        "🔴 *高手打磨计划 | PPL+专项 6天/周*\n"
        "适合：1年以上训练经验\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 *周一 — 力量推(重量日)*\n"
        "1. 杠铃卧推 5×5 (RPE 8-9)\n"
        "2. 上斜卧推 4×6\n"
        "3. 坐姿肩推 4×6\n"
        "4. 加重双杠臂屈伸 3×8\n\n"
        "📅 *周二 — 力量拉(重量日)*\n"
        "1. 硬拉 5×3 (RPE 8-9)\n"
        "2. 加重引体向上 4×6\n"
        "3. 杠铃划船 4×6\n"
        "4. 面拉 3×15\n\n"
        "📅 *周三 — 力量腿(重量日)*\n"
        "1. 杠铃深蹲 5×5 (RPE 8-9)\n"
        "2. 前蹲 3×6\n"
        "3. 罗马尼亚硬拉 3×8\n"
        "4. 腿举 3×10\n\n"
        "📅 *周四 — 泵感推(容量日)*\n"
        "上斜哑铃 4×12 + 绳索飞鸟超级组 4×15 + 侧平举 5×15 + 反向飞鸟 3×15 + 三头孤立 4×15\n\n"
        "📅 *周五 — 泵感拉(容量日)*\n"
        "宽握下拉 4×12 + 单臂划船 3×12 + 直臂下压 3×15 + 二头21s法 3组 + 锤式弯举 3×12\n\n"
        "📅 *周六 — 泵感腿(容量日)*\n"
        "哈克深蹲 4×12 + 保加利亚蹲 3×12/侧 + 腿弯举 4×12 + 腿伸展 4×12 + 小腿 5×15\n\n"
        "📅 *周日 — 休息/恢复*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 *关键：力量日追重量，容量日追泵感。Deload每4周做1次。*\n\n"
        "⚡ *老王说：到这个阶段，训练已经是生活方式。差距在恢复和营养。*"
    ),

    "wplan_wang": (
        "⚫ *老王同款训练计划*\n"
        "这是老王本人当前在用的计划\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🗓️ *周期：PPL + 有氧，每周6练*\n\n"
        "📅 *周一 — 推日*\n"
        "1. 杠铃卧推 4×6-8 (渐进加重)\n"
        "2. 上斜哑铃卧推 3×10\n"
        "3. 绳索夹胸 3×12\n"
        "4. 坐姿肩推 4×8\n"
        "5. 侧平举 4×15\n"
        "6. 绳索三头下压 3×12\n"
        "训练后：15min快走\n\n"
        "📅 *周二 — 拉日*\n"
        "1. 硬拉 4×5\n"
        "2. 引体向上 4×力竭\n"
        "3. 坐姿划船 3×10\n"
        "4. 单臂哑铃划船 3×10\n"
        "5. 面拉 3×15\n"
        "6. 锤式弯举 3×12\n"
        "训练后：15min快走\n\n"
        "📅 *周三 — 腿日*\n"
        "1. 杠铃深蹲 4×6-8\n"
        "2. 腿举 3×12\n"
        "3. 罗马尼亚硬拉 3×10\n"
        "4. 保加利亚蹲 3×10/侧\n"
        "5. 腿弯举 3×12\n"
        "6. 小腿提踵 4×15\n"
        "训练后：不加有氧(腿日够累了)\n\n"
        "📅 *周四 — 推日2*\n"
        "轻重量高次数版本，补弱项\n\n"
        "📅 *周五 — 拉日2*\n"
        "轻重量高次数版本，侧重背部宽度\n\n"
        "📅 *周六 — 30min HIIT + 核心*\n"
        "波比跳/壶铃摇摆/战绳/划船机 循环\n\n"
        "📅 *周日 — 完全休息*\n"
        "拉伸、泡沫轴、散步\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🍽️ *老王的饮食原则*\n"
        "• 每天蛋白质 160g+\n"
        "• 训练日碳水多吃，休息日碳水减少\n"
        "• 早晨黑咖啡，训练前香蕉\n"
        "• 不戒零食，但只吃白名单里的\n"
        "• 每周允许一餐放纵(但不暴食)\n\n"
        "💊 *老王的补剂栈*\n"
        "肌酸 5g/天 + 维D3 2000IU + 鱼油 2g + 镁 400mg(睡前)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚡ *老王说：这套计划我跑了一年多了。没什么花样，但每一天都在进步。最好的计划就是你能坚持的计划。*"
    ),
}


@require_membership
async def show_plan_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "💪 *老王训练计划库*\n\n"
            "5套经过验证的训练计划，选择你的阶段 👇",
            parse_mode="Markdown",
            reply_markup=_MENU_KB,
        )
    else:
        await update.message.reply_text(
            "💪 *老王训练计划库*\n\n"
            "5套经过验证的训练计划，选择你的阶段 👇",
            parse_mode="Markdown",
            reply_markup=_MENU_KB,
        )


async def show_plan_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data not in _PLANS:
        return

    await query.message.reply_text(
        _PLANS[data],
        parse_mode="Markdown",
        reply_markup=_BACK_KB,
    )
