"""Every sentence the assistant says from a template, in English and Chinese, and the one rule that picks.

A reply is written in the language of the household's message. A message with no words to tell by
(a number, a quantity, "ok") keeps the language of their last message that had some. Templates are
looked up by key, so a new reply is added here once, in both languages, instead of at its call site.
"""

import re
from collections.abc import Iterable

CJK = re.compile(r"[一-鿿]")
ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")


def language(message: str, history: Iterable = ()) -> str:
    """'zh' or 'en': the message's language, else that of the latest user message in `history` that has one."""
    earlier = [getattr(item, "content", "") for item in history if getattr(item, "role", "user") == "user"]
    for text in [message, *reversed(earlier)]:
        if CJK.search(text):
            return "zh"
        if ENGLISH_WORD.search(text):
            return "en"
    return "en"


def say(key: str, lang: str, **values) -> str:
    english, chinese = REPLIES[key]
    return (chinese if lang == "zh" else english).format(**values)


def people(count: int, lang: str) -> str:
    if lang == "zh":
        return f"{count} 个人"
    return f"{count} {'person' if count == 1 else 'people'}"


def joined(items: Iterable[str], lang: str) -> str:
    return ("、" if lang == "zh" else ", ").join(items)


def listed(items: list[str], lang: str) -> str:
    """'A, B and C', or A、B和C."""
    if len(items) < 2:
        return "".join(items)
    return f"{joined(items[:-1], lang)}{'和' if lang == 'zh' else ' and '}{items[-1]}"


def weekday(day, lang: str) -> str:
    """'Mon 5 Oct' or '周一 10月5日' for a date."""
    if lang == "zh":
        return f"周{'一二三四五六日'[day.weekday()]} {day.month}月{day.day}日"
    return f"{day:%a} {day.day} {day:%b}"


# Words the summary and the limits name, in Chinese; an English word is used as it is.
ZH_WORDS = {
    "vegetarian": "素食",
    "vegan": "纯素",
    "gluten-free": "无麸质",
    "dairy-free": "无乳制品",
    "low-sodium": "少盐",
    "low-sugar": "少糖",
    "lower-calorie": "低热量",
    "peanut": "花生",
    "soy": "大豆",
    "gluten": "麸质",
    "sesame": "芝麻",
    "dairy": "乳制品",
    "egg": "鸡蛋",
    "fish": "鱼",
    "shellfish": "贝类",
    "tree_nut": "坚果",
    "group:alcohol": "酒类",
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
    "main": "主菜",
    "vegetable": "配菜",
    "soup": "汤",
}


def word(value: str, lang: str) -> str:
    """One constraint value as the household reads it: 'tree nut', or 坚果."""
    if lang == "zh":
        if value in ZH_WORDS:
            return ZH_WORDS[value]
        from app.agent.ingredient_matcher import names_of

        names = names_of("zh_names").get(value)
        if names:
            return names[0]
    return value.replace("group:", "").replace("_", " ").replace("-", " ")


# What the planner (planning/product_path.py) and a change to a saved week (services/replanning.py) say when
# they turn a request down, in Chinese.
PLANNER_ZH = {
    "Enter a budget in whole cents and try again.": "预算请精确到分（最多两位小数）再试一次。",
    "Combine duplicate pantry entries before trying again.": "家里的食材有重复的条目，合并之后再试一次。",
    "Enter finite pantry quantities and try again.": "家里食材的数量要写成具体的数字，再试一次。",
    "Recipe coverage for a requested allergen is missing; update the allergen data before planning.": (
        "你说的某种过敏原，食谱数据里还没有覆盖；要先补上过敏原数据才能规划。"
    ),
    "Recipe or price details could not be verified; refresh them and try again.": (
        "有些食谱或价格信息没法核实，刷新之后再试一次。"
    ),
    "Some recipe or price details are missing. Try again in a moment.": "有些食谱或价格信息缺失，请稍后再试。",
    "I couldn't find a week that meets every limit. Try relaxing one of them.": (
        "我找不到满足所有限制的安排，放宽其中一个再试试。"
    ),
    "Planning took longer than it should this time. Please try again.": "这次规划花的时间太长了，请再试一次。",
    "No candidate plan was found; try a different recipe selection.": "没有找到可行的安排，换一些菜再试试。",
    "No recipes satisfy the supplied hard constraints.": "没有菜符合你的硬性限制。",
    "A week plans at least one meal a day.": "一周每天至少要安排一顿饭。",
    "Changing meals is not available here.": "这里不能调整饭菜的安排。",
    "Completed meals are historical records and cannot be replanned.": "已经做过的饭菜是历史记录，不能再调整。",
    "This meal is locked and cannot be replanned.": "这顿饭已经锁定，不能调整。",
    "This meal is already cancelled.": "这顿饭已经取消了。",
}
# ... and those that carry a value: a meal is named in Chinese, a dish by its title.
PLANNER_ZH_PATTERNS = (
    (
        r"I couldn't fit seven dinners into S\$(?P<budget>[\d.]+)\. The cheapest week I found costs "
        r"S\$(?P<cost>[\d.]+)\. Try a higher budget or fewer limits\.",
        "S${budget} 排不下这些饭菜：我找到的最便宜的一周要 S${cost}。可以提高预算，或者少一些限制。",
    ),
    (r"There is no (?P<meal>\w+) left to change on those days\.", "那几天已经没有可以调整的{meal}了。"),
    (r"(?P<meal>\w+) is not planned on those days\.", "那几天没有安排{meal}。"),
    (
        r"No dish other than (?P<title>.+) satisfies the current hard constraints\.",
        "除了{title}，没有别的菜符合现在的限制。",
    ),
)


def planner_message(message: str, lang: str) -> str:
    """The planner's own reason, in the conversation's language; one it has no Chinese for is said in general
    terms rather than in English."""
    if lang != "zh":
        return message
    if message in PLANNER_ZH:
        return PLANNER_ZH[message]
    for pattern, chinese in PLANNER_ZH_PATTERNS:
        if found := re.fullmatch(pattern, message):
            values = found.groupdict()
            if "meal" in values:
                values["meal"] = word(values["meal"].lower(), lang)
            return chinese.format(**values)
    return "有个限制这次满足不了。"


def details(stated, lang: str) -> list[str]:
    """What a message (an extraction) or a conversation (its constraints) says, one short phrase each."""

    def words(values) -> str:
        return joined((word(value, lang) for value in values), lang)

    parts: list[str] = []
    if stated.household_size:
        parts.append(people(stated.household_size, lang))
    if stated.weekly_budget_sgd:
        parts.append(say("weekly_detail", lang, amount=stated.weekly_budget_sgd))
    if stated.budget_per_meal_sgd:
        parts.append(say("meal_detail", lang, amount=stated.budget_per_meal_sgd))
    if stated.max_cooking_time_minutes:
        parts.append(say("time_detail", lang, minutes=stated.max_cooking_time_minutes))
    if stated.dietary_preferences:
        parts.append(words(stated.dietary_preferences))
    if stated.health_preferences:
        parts.append(words(stated.health_preferences))
    if stated.allergens:
        parts.append(say("allergy_detail", lang, words=words(stated.allergens)))
    if stated.excluded_ingredients:
        parts.append(say("exclusion_detail", lang, words=words(stated.excluded_ingredients)))
    if stated.available_ingredients:
        parts.append(
            say("pantry_detail", lang, words=words(item.normalized_name for item in stated.available_ingredients))
        )
    if stated.max_uses_per_recipe == 1:
        parts.append(say("no_repeats_detail", lang))
    elif stated.max_uses_per_recipe:
        parts.append(say("cap_detail", lang, count=stated.max_uses_per_recipe))
    return parts


REPLIES: dict[str, tuple[str, str]] = {
    # Scope boundaries (orchestration/runtime.py).
    "social": (
        "Hello. I can help plan meals, explain a MealCraft plan, or adjust an existing plan.",
        "你好！我可以帮你规划饭菜、解释 MealCraft 的计划，或者调整已有的计划。",
    ),
    "out_of_scope": (
        "That request is outside MealCraft's meal-planning scope. I can help with recipes, "
        "dietary constraints, groceries, budgets, or an existing meal plan.",
        "这个请求不在 MealCraft 的饮食规划范围内。我可以帮你处理食谱、饮食限制、买菜、预算，或调整已有的计划。",
    ),
    "restricted": (
        "MealCraft does not create disease-treatment diets or medical prescriptions. "
        "I can apply explicit allergens, general preferences, and nutrition targets you provide.",
        "MealCraft 不制定疾病治疗饮食或医疗处方。我可以按你明确给出的过敏原、一般偏好和营养目标来安排。",
    ),
    "adversarial": (
        "I cannot reveal credentials, system instructions, or bypass MealCraft's safety and authorization rules.",
        "我不能透露凭据或系统指令，也不能绕过 MealCraft 的安全和授权规则。",
    ),
    "ambiguous": (
        "I am not sure whether this is a meal-planning request. Tell me what meal, recipe, grocery, "
        "budget, or dietary-planning task you want help with, or pick one of these.",
        "我不太确定这是不是饮食规划的请求。告诉我想安排哪一餐、哪道菜，或者预算、买菜、饮食上需要什么帮助，也可以直接选下面一项。",
    ),
    "domain_question": (
        "I can answer questions using the saved MealCraft plan and grounded tool results.",
        "我可以根据已保存的 MealCraft 计划和工具查到的结果回答问题。",
    ),
    "unsupported": (
        "I could not safely process that request. Please restate the supported meal-planning task.",
        "我没法安全地处理这个请求。请换个说法，告诉我想怎么安排饭菜。",
    ),
    "partial": (
        "I handled the meal-planning part only. I cannot help with the unrelated part of that request. ",
        "我只处理了和饮食规划有关的部分，其余无关的部分我帮不上忙。",
    ),
    # "Something nice", 我想吃点好的: a wish, not yet a request.
    "wish": (
        "Happy to help you eat well. Tell me who's eating and what you like, or start with one of these.",
        "好呀，我来帮你吃得好一点。告诉我几个人吃、喜欢吃什么，或者从下面选一个开始。",
    ),
    "wish_planned": (
        "Want something different? I can swap tonight's dinner, or a dish on another day. "
        "Nothing changes until you confirm.",
        "想换换口味？我可以换掉今晚的晚餐，也可以换别的日子的菜。确认之前什么都不会改。",
    ),
    # "The dishes are boring", 菜很单调: a wish for variety.
    "variety": (
        "Let's make it more varied. I can plan a week with no dish twice.",
        "那就多换些花样。我可以规划一周、菜不重样。",
    ),
    "variety_planned": (
        "Let's make it more varied. I can plan a new week with different dishes, or swap a dish.",
        "那就多换些花样。我可以重新规划一周、换一批菜，也可以换掉一道菜。",
    ),
    # A new week with different dishes (services/agent.py _plan_again).
    "varied_planned": (
        "Here's a new week with {count} different dishes (the last one had {before}){fresh}. "
        "Tap a dish for the recipe, or ask me to swap anything.",
        "新的一周排好了：{count} 道不同的菜（上一周是 {before} 道）{fresh}。点一道菜看食谱，想换什么都可以告诉我。",
    ),
    "varied_fresh": (", none of them from last week", "，没有一道是上一周的"),
    "varied_back": (
        ", {count} from last week because too few others fit",
        "，其中 {count} 道是上一周的，因为别的菜不够",
    ),
    "varied_kept": (
        "Your week stays as it is. For a new week with different dishes: {why}",
        "这周保持不变。换一批菜的新一周：{why}",
    ),
    "varied_no_more": (
        "Your week stays as it is: the most varied new week I could plan{within} has {count} different dishes, "
        "{new} of them new, and this one has {before}. I can swap a dish instead.",
        "这周保持不变：我能排出的最多样的新一周{within}有 {count} 道不同的菜，其中 {new} 道是新的，这周是 {before} 道。"
        "可以换掉一道菜试试。",
    ),
    "varied_within": (" within S${budget:g}", "（S${budget:g} 以内）"),
    # Conversation (agent/workflow.py, agent/parser.py).
    "got_it": ("Got it: {details}.", "好的：{details}。"),
    "noted": ("Noted.", "好的。"),
    "offline": (
        " (The assistant's model didn't answer in time, so I read this with simple rules.)",
        "（助手的模型没有及时回应，所以我用简单规则读了这条消息。）",
    ),
    "ask_people": ("How many people should this weekly plan serve?", "这周的计划给几个人吃？"),
    "unmatched": (
        "I could not match “{term}” to an ingredient or allergen I can check, so it is not applied yet.",
        "我没能把“{term}”对应到我能检查的食材或过敏原，所以暂时没有用上。",
    ),
    "unmatched_options": (
        " Did you mean one of these: {names}? Pick one, or tell me in other words.",
        "你指的是其中一个吗：{names}？选一个，或者换个说法告诉我。",
    ),
    "unmatched_open": (" Which ingredient do you mean?", "你指的是哪种食材？"),
    "ask_quantity": (
        "How much {name} do you already have? Reply “unknown” to use it only as a ranking preference.",
        "家里的{name}还有多少？回复“不知道”的话，我只在排序时优先用它。",
    ),
    "unknown_quantity": ("I don't know", "不知道"),
    "medical": (
        "MealCraft does not provide disease-specific or medical dietary advice. I can still apply general, "
        "explicit constraints such as allergens, lower sodium, lower sugar or user-supplied nutrition targets.",
        "MealCraft 不提供针对疾病的饮食或医疗建议。"
        "我仍然可以按明确的一般限制来安排，比如过敏原、少盐、少糖，或你给出的营养目标。",
    ),
    "ready": (
        "That's everything I need. Check the details below and plan your week when you're ready.",
        "我需要的信息都齐了。看看下面的细节，准备好了就开始规划这一周吧。",
    ),
    # Summary details.
    "weekly_detail": ("S${amount:g} for the week", "一周 S${amount:g}"),
    "meal_detail": ("S${amount:g} a dinner", "每餐 S${amount:g}"),
    "time_detail": ("up to {minutes} minutes of cooking", "做饭不超过 {minutes} 分钟"),
    "allergy_detail": ("nothing with {words} (allergy)", "不含{words}（过敏）"),
    "exclusion_detail": ("no {words}", "不要{words}"),
    "pantry_detail": ("{words} at home", "家里有{words}"),
    "no_repeats_detail": ("no dish twice", "菜不重样"),
    "cap_detail": ("no dish more than {count} times", "每道菜最多 {count} 次"),
    # The composer's hint while a question is open; the question itself is the reply above it.
    "pick_or_type": ("Pick an option or type your answer", "选一个，或者直接输入"),
    "type_answer": ("Type your answer", "直接输入你的回答"),
    # Options the household can tap; the second of each pair is what it sends.
    "plan_week": ("Plan a week of meals", "规划一周的饭菜"),
    "plan_week_say": ("Plan a week of meals for us", "帮我们规划一周的饭菜"),
    "plan_varied": ("A week with no dish twice", "一周菜不重样"),
    "plan_varied_say": ("Plan a week with no dish twice", "帮我们规划一周，菜不要重复"),
    "swap_tonight": ("Swap tonight's dinner", "换掉今晚的晚餐"),
    "replan_varied": ("Plan a new week with different dishes", "重新规划一周，换一批菜"),
    "replan_varied_say": ("Plan a new week with different dishes", "重新规划一周，换一批菜"),
    "swap_repeat": ("Swap the {title} on {day}", "换掉{day}的{title}"),
    "swap_repeat_say": ("Swap the {title} on day {index}", "把第{index}天的{title}换掉"),
    "swap_other": ("Swap a dish on another day", "换别的日子的菜"),
    "swap_say": ("Swap a dish", "替换一道菜"),
    "skip": ("Skip a meal", "跳过一顿"),
    "lock": ("Keep a meal as it is", "保留一顿不变"),
    "lock_say": ("Lock a meal", "锁定一顿"),
    "unavailable": ("An ingredient is out of stock", "有食材买不到"),
    "unavailable_say": ("I can't buy an ingredient", "有食材买不到"),
    "day_say": ("Day {index}", "第{index}天"),
    "dish_say": ("The {title}", "就是{title}这道"),
    "people_say": ("{count} people", "{count}人"),
    "keep_usual": ("Keep it as our usual", "保存为常用安排"),
    "keep_usual_say": ("Keep it as our usual", "保存为我们的常用安排"),
    "just_this_week": ("Just this week", "只改这一周"),
    "exclude_say": ("Exclude {value} (that is what I meant by “{term}”).", "不要{value}（我说的“{term}”就是它）。"),
    "have_say": ("I have {value} (that is what I meant by “{term}”).", "家里有{value}（我说的“{term}”就是它）。"),
    # Changing a saved week (services/agent.py, agent/replanning.py).
    "ask_event": (
        "Should I replace, cancel, lock a meal, or handle an unavailable ingredient?",
        "你希望替换、取消、锁定某餐，还是处理缺货食材？",
    ),
    "ask_dish": (
        "That day has {count} dishes ({titles}); which one should I adjust?",
        "那天有 {count} 道菜（{titles}），你想调整哪一道？",
    ),
    "ask_day": ("Which day should I adjust?", "你想调整哪一天的餐食？"),
    "every_dish": (
        "I change one dish at a time, and nothing changes until you confirm. Which day should I start with?",
        "我一次换一道菜，确认之前什么都不会改。先从哪一天开始？",
    ),
    "ask_ingredient": ("Which ingredient is unavailable?", "哪一种食材买不到？"),
    "preview_lock": ("Keep {title} as it is?", "保留{title}不变？"),
    # "Don't change Monday's dinner": every dish of that meal, in one preview.
    "preview_lock_meal": ("Keep the {meal} on {day} as it is ({titles})?", "保留{day}的{meal}不变（{titles}）？"),
    "preview_skip": ("Skip {title}?", "跳过{title}？"),
    # What a skip does to the shopping: whole packages other dishes still need stay on the list.
    "skip_saves": (" That takes S${amount:.2f} off the groceries.", "买菜少花 S${amount:.2f}。"),
    "skip_same": (" Groceries stay the same.", "买菜不变。"),
    "skip_still_used": (
        " Groceries stay the same: {items} {verb} still used by {titles}.",
        "买菜不变：{items}还要用在{titles}里。",
    ),
    # A dish of a kind the meal already has (services/agent.py _change_shape): asked before a second one.
    "already_has": (
        "{Meal} {when} already has {titles}: add another {dish}, or swap it?",
        "{when}的{meal}已经有{titles}了：再加一道{dish}，还是换掉它？",
    ),
    "already_has_many": (
        "{Meal} {when} already has a {dish} ({titles}): add another {dish} anyway?",
        "{when}的{meal}已经有{dish}了（{titles}）：还要再加一道{dish}吗？",
    ),
    "add_another": ("Add another {dish}", "再加一道{dish}"),
    "swap_dish": ("Swap the {title}", "换掉{title}"),
    "preview_swap": ("How about {after} instead of {before}?", "把{before}换成{after}怎么样？"),
    "until_confirm": (" Nothing changes until you confirm.", "确认之前什么都不会改。"),
    "prepare_failed": ("I could not prepare that change: {error}", "我没法准备这个调整：{error}"),
    "change_failed": ("I could not make that change: {error}", "我没法做这个调整：{error}"),
    "shape_summary": ("{summary}.", "{summary}。"),
    "shape_only": ("{Meal} as one {dish} {when}", "{when}{meal}只做一道{dish}"),
    "shape_one_dish": ("{Meal} as one dish {when}", "{when}{meal}只做一道菜"),
    "shape_no_meal": ("No {meal} {when}", "{when}不安排{meal}"),
    "shape_add_meal": ("{Meal} added {when}", "{when}加上{meal}"),
    "shape_without": ("{Meal} without the {dish} {when}", "{when}{meal}不要{dish}"),
    "shape_with": ("{Meal} with a {dish} {when}", "{when}{meal}加一道{dish}"),
    "shape_with_another": ("{Meal} with another {dish} {when}", "{when}{meal}再加一道{dish}"),
    "when_rest": ("for the rest of this week", "本周余下几天"),
    "when_day": ("that day", "那天"),
    "when_days": ("those days", "那几天"),
    "when_weekdays": ("on weekdays", "工作日"),
    "shape_new": ("New: {titles}{more}.", "新加：{titles}{more}。"),
    "shape_more": (" and {count} more", " 等 {count} 道"),
    "shape_removed_one": ("1 dish comes off the week.", "这周少了 1 道菜。"),
    "shape_removed": ("{count} dishes come off the week.", "这周少了 {count} 道菜。"),
    "shape_groceries": (
        "Groceries {sign}S${amount:.2f}.{over} Nothing changes until you confirm.",
        "买菜 {sign}S${amount:.2f}。{over}确认之前什么都不会改。",
    ),
    "shape_groceries_same": (
        "Groceries stay the same. Nothing changes until you confirm.",
        "买菜不变。确认之前什么都不会改。",
    ),
    "shape_over": (
        " That makes the week S${total:.2f}, S${over:.2f} over the S${budget:g} weekly budget.",
        "这样这周要 S${total:.2f}，超出每周 S${budget:g} 的预算 S${over:.2f}。",
    ),
    "ask_keep": ("Should new weeks plan meals this way too?", "以后每周也这样安排吗？"),
    "kept": (
        "Saved. New weeks will plan these meals too; you can change them any time in your profile.",
        "已保存。以后每周也会这样安排；你随时可以在家庭资料里修改。",
    ),
    "keep_failed": (
        "I couldn't save that to your household, so only this week changed.",
        "没能保存到你的家庭资料，所以只改了这一周。",
    ),
    "week_only": (
        "OK, only this week changes. Your usual meals stay as they are.",
        "好的，只改这一周。你平常的安排保持不变。",
    ),
    "replanned": ("Done. Your week and shopping list are updated.", "好了，这周的计划和购物清单都更新了。"),
    "discarded": ("OK, your week stays as it is.", "好的，这周保持原样。"),
    "planned": (
        "Here's your week. Tap a dinner for the recipe, or ask me to swap anything.",
        "这是你这一周的安排。点一道菜看食谱，想换什么都可以告诉我。",
    ),
    # Limits a week cannot meet (agent/limits.py).
    "floor_meal": (
        "S${budget:g} a meal is not enough: the cheapest {meal} I can plan costs at least S${floor:.2f}.",
        "每餐 S${budget:g} 不够：我能安排的最便宜的{meal}也至少要 S${floor:.2f}。",
    ),
    "no_dish": (
        "No {role} I can plan for {meal} fits {limit}, so I can't plan this week yet.",
        "没有一道能排进{meal}的{role}符合{limit}，所以这周还排不出来。",
    ),
    "limit_time": (
        "a {minutes}-minute cooking limit (the quickest takes {needed} minutes)",
        "{minutes} 分钟以内的做饭时间（最快的也要 {needed} 分钟）",
    ),
    "limit_meal_budget": (
        "S${budget:g} a meal (the cheapest costs S${needed:.2f})",
        "每餐 S${budget:g} 的预算（最便宜的也要 S${needed:.2f}）",
    ),
    "limit_diet": ("a {diet} diet", "{diet}饮食"),
    "limit_sodium": (
        "a {mg} mg sodium limit (the lowest has {needed} mg)",
        "每餐 {mg} 毫克的钠上限（最低的也有 {needed} 毫克）",
    ),
    "raise_sodium": ("Allow up to {mg} mg sodium", "钠放宽到 {mg} 毫克"),
    "raise_sodium_say": ("Allow up to {mg} mg sodium a meal", "每餐钠不超过 {mg}"),
    "no_role": (
        "I have no {role} I can plan for {meal}, so I can't plan this week yet.",
        "我这里没有能排进{meal}的{role}，所以这周还排不出来。",
    ),
    "limit_safety": ("your allergies and the foods you avoid", "你的过敏原和忌口"),
    "limit_together": ("your limits together ({limits})", "你所有的限制（{limits}）"),
    "too_few": (
        "{rule} needs {needed} different {role} for {meal} this week, and only {count} fit your other limits, "
        "so I can't plan it.",
        "{rule}的话，这周的{meal}需要 {needed} 道不同的{role}，但符合其他限制的只有 {count} 道，所以排不出来。",
    ),
    "no_repeats_rule": ("No dish twice", "菜不重样"),
    "cap_rule": ("Each dish at most {count} times", "每道菜最多 {count} 次"),
    # A budget under the floor, for meals too big to search for the cheapest week within a reply (agent/limits.py).
    "floor_week": (
        "S${budget:g} for {people} is S${each:.2f} a person a meal over {meals} meals: what this week's dishes "
        "use costs at least S${floor:.2f}, before buying whole packages.",
        "{people}一周 S${budget:g}，相当于每人每餐 S${each:.2f}（共 {meals} 餐）：这周的菜光是用到的食材就至少要 "
        "S${floor:.2f}，还没算整包购买。",
    ),
    # A budget under the cheapest week the planner's search found (agent/limits.py).
    "budget_short": (
        "S${budget:g} a week for {people} comes to about S${each:.2f} a person a meal ({meals} meals). "
        "The cheapest week I could find costs S${cost:.2f}.",
        "{people}一周 S${budget:g}，每人每餐大约只有 S${each:.2f}（一周 {meals} 餐）。"
        "我能找到的最便宜的一周要 S${cost:.2f}。",
    ),
    "use_weekly": ("Use S${amount} for the week", "一周用 S${amount}"),
    "use_weekly_say": ("Make the weekly budget S${amount}", "每周预算 {amount} 新币"),
    "raise_meal": ("Raise the per-meal budget to S${amount}", "把每餐预算提高到 S${amount}"),
    "raise_meal_say": ("Make it S${amount} per meal", "每餐预算 {amount} 新币"),
    "fewer_people": ("Plan for {people}", "改成 {people}"),
    "fewer_people_say": ("Plan for {people}", "改成{count}个人"),
    "fewer_people_at": ("{people} at S${amount} a week", "{people}，一周 S${amount}"),
    "fewer_people_at_say": ("{people}, S${amount} for the week", "{count}个人，一周{amount}新币"),
    "raise_time": ("Allow up to {minutes} minutes", "放宽到 {minutes} 分钟"),
    "raise_time_say": ("Allow up to {minutes} minutes of cooking", "做饭 {minutes} 分钟以内"),
    # A week the planner could not find (services/agent.py confirm).
    "search_failed": (
        "I couldn't plan this week: the search found no week that meets {limit}. "
        "That is the limit it kept running into.",
        "这周没排出来：搜索没有找到符合{limit}的一周。卡住它的就是这个限制。",
    ),
    "not_planned": ("I couldn't plan this week: {reason}", "这周没排出来：{reason}"),
    "search_failed_generic": (
        "I couldn't plan this week: the search found no week that meets every limit together ({limits}).",
        "这周没排出来：搜索没有找到同时满足所有限制的一周（{limits}）。",
    ),
    "slow": (
        "Planning took longer than it should this time. Please try again.",
        "这次规划花的时间太长了，请再试一次。",
    ),
    "weekly_limit": ("the S${amount:g} weekly budget", "每周 S${amount:g} 预算"),
    "meal_limit": ("the S${amount:.2f} a meal budget", "每餐 S${amount:.2f} 的预算"),
    "time_limit": ("the {minutes}-minute cooking limit", "{minutes} 分钟的做饭时间"),
    "repeat_limit": ("your rule of no dish twice", "菜不重样的要求"),
    "nutrition_limit": ("your nutrition targets", "你的营养目标"),
    "request_limit": ("your request for a particular dish", "你点名要的菜"),
}
