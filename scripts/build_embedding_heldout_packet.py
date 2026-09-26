"""Build the sealed authoring packet for the embedding held-out sets (tasks A and B).

    python scripts/build_embedding_heldout_packet.py OUT_DIR [PROMPT.md]

PROMPT defaults to docs/evaluation/embedding-heldout-prompt.md; the Chinese set uses
docs/evaluation/chinese-heldout-prompt.md.

The packet holds the rules, the templates, the checker and catalog facts only: no implementation, no
developer set, no model-generated aliases, so its authors cannot write to the system's known weaknesses.
"""

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from check_embedding_heldout import catalog

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = Path(sys.argv[1])
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "scripts").mkdir(exist_ok=True)
    (out / "out").mkdir(exist_ok=True)
    prompt = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs/evaluation/embedding-heldout-prompt.md"
    shutil.copy(prompt, out / "PROMPT.md")
    shutil.copy(ROOT / "scripts/check_embedding_heldout.py", out / "scripts/check_embedding_heldout.py")
    shutil.copy(ROOT / "data/evaluation/agent/TEMPLATE-ingredient-terms.json", out / "out/ingredient-terms.json")
    shutil.copy(ROOT / "data/evaluation/agent/TEMPLATE-swap-requests.json", out / "out/swap-requests.json")

    names, mains = catalog(None)
    with (out / "data/catalog-ingredients.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name"])
        writer.writerows(sorted(names.items()))
    (out / "data/catalog-mains.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mains), encoding="utf-8"
    )
    cuisines = Counter(m["cuisine"] for m in mains)
    tags = Counter(t for m in mains for t in m["dietary_tags"])
    facts = [
        "# 目录事实（主菜）",
        "",
        f"主菜共 {len(mains)} 道。任务 B 的 `check` 在这些主菜里判断。",
        "",
        "## 菜系（`cuisine`）",
        "",
        *[f"- `{c}`：{n} 道" for c, n in cuisines.most_common()],
        "",
        "## 饮食标签（`dietary_tag`）",
        "",
        *[f"- `{t}`：{n} 道" for t, n in tags.most_common()],
        "",
        "食材 id 见 `catalog-ingredients.csv`；每道主菜的食材 id、菜名、菜系、标签见 `catalog-mains.jsonl`。",
        "",
    ]
    (out / "data/catalog-facts.md").write_text("\n".join(facts), encoding="utf-8")
    print(f"packet in {out}: {len(names)} ingredients, {len(mains)} mains")


if __name__ == "__main__":
    main()
