"""Markdown review sheet for YouTube tutorial labels, and the reader that turns a filled sheet back into labels.

    python scripts/tutorial_review_sheet.py sheet                 # writes the blank sheet
    python scripts/tutorial_review_sheet.py read FILLED.md NAME   # writes labels-v1/<NAME>.json
    PYTHONPATH="backend;scripts" python scripts/tutorial_review_sheet.py heldout   # person review, held-out

Each reviewer fills their own copy; nobody sees the other's copy. The sheet never shows which dishes are
held-out or YouTube's own order, so neither can steer a score.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path("data/evaluation/tutorials")
CANDIDATES = ROOT / "candidates-v1.json"
SHEET = ROOT / "review-sheet-v1.md"
HELDOUT_SHEET = ROOT / "heldout-review-v1.md"
LABELS = ROOT / "labels-v1"

RULES = """# YouTube 教程标注 · candidates-v1

审核人：（填你的名字）
是否用 agent 辅助：（是 / 否；是的话写用了什么，以及你自己核对了多少）

## 规则

在每一行的「分数」一栏填 **2、1 或 0**：

- **2 · 就是这道菜的做法**：跟着它能把这道菜做出来。叫法不同但是同一道菜也算。
- **1 · 相关，但不理想**：明显的变体或换了主料；吃播、测评、探店；没有完整做法；太短学不会。
- **0 · 不相关**：别的菜、广告、合集里一闪而过。

- 每个人独立判断：不要看别人的表，也不要讨论具体某一行。
- 拿不准就点链接看视频，不要只看标题猜。
- 用 agent 辅助可以，但每一行的分数都要你自己认可；agent 不能是调排序的那一个（Claude Code 这个会话）。
- 行的顺序是打乱的，和 YouTube 的排名无关。
- 填完把文件交回，不要改表格结构和链接。
"""


HELDOUT_RULES = """# YouTube 教程 held-out 人工复核 · candidates-v1

审核人：（填你的名字，必须是人）
复核日期：

## 这张表是做什么的

排序 v2 只在 developer 的 20 道菜上开发过。这张表是另外 19 道 held-out 菜，用来得到可以写进报告的数字。
每道菜只列出需要确认的几个视频：各个排序方案选中的视频，以及用来确认「这道菜有没有合适视频」的少数候选。
表里**不显示**之前的评分，也不显示哪个方案选了哪个视频，所以请只按视频本身判断。

## 规则

- **每个视频都要打开看**：至少看开头、做法部分，确认它真的是在教这道菜。只看标题不算。
- 在「分数」一栏填 **2、1 或 0**（和之前的评分表同一套标准）：
  - **2 · 就是这道菜的做法**：跟着它能把这道菜做出来。叫法不同但是同一道菜也算。
  - **1 · 相关，但不理想**：明显的变体或换了主料；吃播、测评、探店；没有完整做法；太短学不会。
  - **0 · 不相关**：别的菜、广告、合集里一闪而过；视频打不开也填 0，并在「备注」写明。
- 参考「原菜谱」一行判断是不是同一道菜，菜名相同但做法不同的，不算 2。
- 不要借助 AI 判分；可以用 AI 查资料（比如某道菜的传统做法），判断由你自己做。
- 不要改表格结构和链接。
"""


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def duration(seconds: int | None) -> str:
    if seconds is None:
        return "未知"
    return f"{seconds // 60}:{seconds % 60:02d}" + (" · Shorts" if seconds < 60 else "")


def write_sheet() -> None:
    dishes = json.loads(CANDIDATES.read_text(encoding="utf-8"))["dishes"]
    dishes = sorted(dishes, key=lambda d: hashlib.sha1(d["recipe_id"].encode()).hexdigest())
    lines = [RULES]
    for n, dish in enumerate(dishes, start=1):
        videos = sorted(
            dish["candidates"], key=lambda c: hashlib.sha1((dish["recipe_id"] + c["video_id"]).encode()).hexdigest()
        )
        lines += [
            f"## {n}. {dish['title']}（{dish['cuisine'].replace('_', ' ')}）",
            f"<!-- {dish['recipe_id']} -->",
            "",
            "主要食材：" + "、".join(dish["ingredients"][:5]),
            "",
            "| 分数 | 视频 | 频道 | 时长 |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"|  | [{cell(v['title'])}](https://www.youtube.com/watch?v={v['video_id']}) "
            f"| {cell(v['channel_title'])} | {duration(v['duration_seconds'])} |"
            for v in videos
        ]
        lines.append("")
    SHEET.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {SHEET}: {len(dishes)} dishes, {sum(len(d['candidates']) for d in dishes)} videos")


def write_heldout_sheet() -> None:
    """Every video a compared policy picks, plus up to three the first review scored 2 when no pick was one,
    so the person's review decides both what each policy picked and whether a right video existed."""
    from evaluate_tutorial_ranking import POLICIES

    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))["dishes"]
    first = json.loads((LABELS / "codex.json").read_text(encoding="utf-8"))["labels"]
    recipes = {
        json.loads(line)["recipe_id"]: json.loads(line)
        for line in Path("data-engineering/data/release/v2.1/recipes.jsonl").read_text(encoding="utf-8").splitlines()
    }
    dishes = sorted(
        (d for d in data if d["split"] == "heldout"), key=lambda d: hashlib.sha1(d["recipe_id"].encode()).hexdigest()
    )
    lines, total = [HELDOUT_RULES], 0
    for n, dish in enumerate(dishes, start=1):
        by_id = {c["video_id"]: c for c in dish["candidates"]}
        picked = list(dict.fromkeys(v for choose in POLICIES.values() if (v := choose(dish))))
        if not any(first[dish["recipe_id"]].get(v) == 2 for v in picked):
            twos = [c for c in dish["candidates"] if first[dish["recipe_id"]].get(c["video_id"]) == 2]
            twos.sort(key=lambda c: min(c["ranks"].values()))
            picked += [c["video_id"] for c in twos[:3] if c["video_id"] not in picked]
        picked.sort(key=lambda v: hashlib.sha1((dish["recipe_id"] + v).encode()).hexdigest())
        steps = " ".join(step["text"] for step in recipes[dish["recipe_id"]]["instructions"])[:400]
        lines += [
            f"## {n}. {dish['title']}（{dish['cuisine'].replace('_', ' ')}）",
            f"<!-- {dish['recipe_id']} -->",
            "",
            "主要食材：" + "、".join(dish["ingredients"][:8]),
            "",
            f"原菜谱：{cell(steps)}{'…' if len(steps) == 400 else ''}",
            "",
            "| 分数 | 视频 | 频道 | 时长 | 备注 |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"|  | [{cell(by_id[v]['title'])}](https://www.youtube.com/watch?v={v}) "
            f"| {cell(by_id[v]['channel_title'])} | {duration(by_id[v]['duration_seconds'])} |  |"
            for v in picked
        ]
        lines.append("")
        total += len(picked)
    HELDOUT_SHEET.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {HELDOUT_SHEET}: {len(dishes)} dishes, {total} videos to watch")


ROW = re.compile(r"^\|\s*([^|]*?)\s*\|\s*\[.*\]\(https://www\.youtube\.com/watch\?v=([\w-]+)\)")
DISH = re.compile(r"<!--\s*(RCP\w+)\s*-->")


def read_sheet(path: Path, reviewer: str) -> None:
    labels: dict[str, dict[str, int]] = {}
    recipe = None
    problems = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if match := DISH.search(line):
            recipe = match.group(1)
        elif (match := ROW.match(line)) and recipe:
            score, video = match.groups()
            if score in {"0", "1", "2"}:
                labels.setdefault(recipe, {})[video] = int(score)
            else:
                problems.append(f"line {number}: score {score!r} is not 0, 1 or 2")
    expected = sum(len(d["candidates"]) for d in json.loads(CANDIDATES.read_text(encoding="utf-8"))["dishes"])
    got = sum(len(v) for v in labels.values())
    LABELS.mkdir(parents=True, exist_ok=True)
    out = LABELS / f"{reviewer}.json"
    out.write_text(json.dumps({"reviewer": reviewer, "labels": labels}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {got}/{expected} scored")
    for problem in problems[:20]:
        print(" ", problem)


if __name__ == "__main__":
    if sys.argv[1:2] == ["sheet"]:
        write_sheet()
    elif sys.argv[1:2] == ["heldout"]:
        write_heldout_sheet()
    elif sys.argv[1:2] == ["read"] and len(sys.argv) == 4:
        read_sheet(Path(sys.argv[2]), sys.argv[3])
    else:
        sys.exit(__doc__)
