"""Markdown review sheet for YouTube tutorial labels, and the reader that turns a filled sheet back into labels.

    python scripts/tutorial_review_sheet.py sheet                 # writes the blank sheet
    python scripts/tutorial_review_sheet.py read FILLED.md NAME   # writes labels-v1/<NAME>.json

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
    elif sys.argv[1:2] == ["read"] and len(sys.argv) == 4:
        read_sheet(Path(sys.argv[2]), sys.argv[3])
    else:
        sys.exit(__doc__)
