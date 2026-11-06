"""Check and export the prices a person recorded by hand (`docs/design/manual-prices.md`).

    python scripts/manual_prices.py validate SHEET   # name every problem by rank
    python scripts/manual_prices.py export SHEET     # write data/products/manual-v1-snapshot.json

The sheet is `data/enrichment/manual/v1/price-sheet.csv` (UTF-8 with BOM, so that Excel reads it). A row with none of
the filled fields is blank and skipped; several filled rows may share one ingredient. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, Overflow
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data" / "release" / "v2.2" / "ingredients.jsonl"
RUNTIME = ROOT.parent / "data" / "products" / "manual-v1-snapshot.json"
SINGAPORE = timezone(timedelta(hours=8))

FILLED = (
    "platform",
    "product_name",
    "product_url",
    "price_sgd",
    "package_size",
    "package_unit",
    "in_stock",
    "observed_date",
)
HOSTS = {  # a URL host is the domain or one of its subdomains
    "shopee": ("shopee.sg",),
    "lazada": ("lazada.sg",),
    "amazon": ("amazon.sg",),
    "redmart": ("redmart.lazada.sg", "lazada.sg"),  # RedMart's own pages are www.lazada.sg/products/...
    "other": None,
}
UNITS = {"g", "kg", "ml", "l", "count"}
STOCK = {"y": True, "yes": True, "n": False, "no": False}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# The planner buys whole listings, so a multi-pack would charge a recipe for all of it.
MULTI_PACK = re.compile(r"\bpack of \d|\b\d+[ -]pack\b|\b\d+\s*x\s*\d", re.I)
AI_LOOKUP = "claude-ai web lookup"  # in a row's note: an AI read the price and no person has checked it yet
MONEY = re.compile(r"^(?:s?\$|sgd)?\s*([\d,]*\.?\d+)$", re.IGNORECASE)
THOUSANDS = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?")


def _decimal(text: str, *, thousands: bool = True) -> Decimal | None:
    """A number; a comma only as a thousands separator ("1,234.50"), never a decimal comma ("4,5" is refused)."""
    text = text.strip()
    if "," in text:
        if not thousands or not THOUSANDS.fullmatch(text):
            return None
        text = text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _whole_cents(value: Decimal) -> bool:
    try:
        return value == value.quantize(Decimal("0.01"))
    except (InvalidOperation, Overflow):  # more digits than a Decimal carries: listed as a problem, not a crash
        return False


def release_grams(path: Path = RELEASE) -> dict[str, dict]:
    """Per ingredient: `per_ml` (its own grams per millilitre, if a record carries one) and `per_item` (its grams
    per piece). The v2.2 records give grams per cup, which is a volume of chopped or sliced food and not a density,
    so in practice only `per_item` is known; ml and l fall back to 1.0 g/ml."""
    grams = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        info = {"per_ml": record.get("grams_per_ml"), "per_item": None}
        for form in record.get("forms", {}).values():
            info["per_ml"] = info["per_ml"] or form.get("grams_per_ml")
            for unit in form.get("unit_grams", []):
                if unit.get("unit") == "piece" and info["per_item"] is None:
                    info["per_item"] = unit["grams"]
        grams[record["ingredient_id"]] = info
    return grams


def read_sheet(path: Path) -> list[dict]:
    """The filled rows, each with its sheet line (`line`). `utf-8-sig` drops the BOM; `newline=""` handles CRLF."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"rank", "ingredient_id", *FILLED} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path}: missing columns {sorted(missing)}")
        rows = []
        for row in reader:
            row = {key: (value or "").strip() for key, value in row.items() if key}
            if any(row[key] for key in FILLED):
                rows.append(dict(row, line=reader.line_num))
    return rows


def check_row(row: dict, grams: dict[str, dict], today: date) -> tuple[list[str], dict | None]:
    """The problems of one filled row, and its product (without `external_id`) when there are none."""
    issues = []
    for key in (
        "ingredient_id",
        "platform",
        "product_name",
        "product_url",
        "price_sgd",
        "package_size",
        "package_unit",
    ):
        if not row[key]:
            issues.append(f"{key} is empty")
    if not re.fullmatch(r"\d+", row["rank"]):
        issues.append(f"rank {row['rank']!r} is not a whole number")
    if row["ingredient_id"] and row["ingredient_id"] not in grams:
        issues.append(f"ingredient_id {row['ingredient_id']!r} is not in the release")

    if MULTI_PACK.search(row["product_name"]):
        issues.append(f"product_name {row['product_name']!r} is a multi-pack: record one single unit")

    platform = row["platform"].lower()
    if row["platform"] and platform not in HOSTS:
        issues.append(f"platform {row['platform']!r} is not one of {', '.join(HOSTS)}")
    elif row["product_url"] and platform in HOSTS:
        url = urlparse(row["product_url"])
        host = (url.hostname or "").lower()
        domains = HOSTS[platform]
        if url.scheme not in ("http", "https") or not host:
            issues.append(f"product_url {row['product_url']!r} is not a web address")
        elif domains and not any(host == d or host.endswith("." + d) for d in domains):
            issues.append(f"product_url host {host!r} does not belong to {platform} ({' or '.join(domains)})")

    price = None
    if row["price_sgd"]:
        match = MONEY.match(row["price_sgd"])
        price = _decimal(match.group(1)) if match else None
        if price is None or price <= 0 or not _whole_cents(price):
            issues.append(f"price_sgd {row['price_sgd']!r} is not a positive price in whole cents")
            price = None

    size = _decimal(row["package_size"], thousands=False) if row["package_size"] else None
    if row["package_size"] and (size is None or not size.is_finite() or size <= 0):
        issues.append(f"package_size {row['package_size']!r} is not a positive number")
        size = None
    unit = row["package_unit"].lower()
    if row["package_unit"] and unit not in UNITS:
        issues.append(f"package_unit {row['package_unit']!r} is not one of {', '.join(sorted(UNITS))}")
        unit = ""

    in_stock = STOCK.get(row["in_stock"].lower())
    if in_stock is None:
        issues.append(f"in_stock {row['in_stock']!r} is not y or n")

    observed = None
    if not DATE.fullmatch(row["observed_date"]):
        issues.append(f"observed_date {row['observed_date']!r} is not YYYY-MM-DD")
    else:
        try:
            observed = date.fromisoformat(row["observed_date"])
        except ValueError:
            issues.append(f"observed_date {row['observed_date']!r} is not a real date")
        else:
            if observed > today:
                issues.append(f"observed_date {row['observed_date']} is in the future")

    package = None
    if size is not None and unit and row["ingredient_id"] in grams:
        try:
            package = package_grams(size, unit, grams[row["ingredient_id"]])
        except (InvalidOperation, Overflow):
            issues.append(f"package_size {row['package_size']!r} is too large")
        else:
            if package is None:
                issues.append(
                    f"{size} count has no known weight: the release has no grams per item for this ingredient"
                )
            elif not math.isfinite(package[0]):  # 1e400 g is a float infinity
                issues.append(f"package_size {row['package_size']!r} is too large")
            elif package[0] < 0.01:  # 0 g would divide by zero where the planner prices a package
                issues.append(f"package_size {row['package_size']!r} {unit} is less than 0.01 g")
    if issues:
        return issues, None
    grams_value, basis = package
    return [], {
        "name": row["product_name"],
        "brand": None,
        "category": None,
        "package_grams": grams_value,
        "package_grams_basis": basis,
        "price_sgd": float(price),
        "product_url": row["product_url"],
        "in_stock": in_stock,
        "retailer": platform,
        "fetched_at": f"{observed.isoformat()}T00:00:00+08:00",
    }


def package_grams(size: Decimal, unit: str, info: dict) -> tuple[float, str] | None:
    """The package in grams of this ingredient and how that was worked out, or None for a count of unknown weight."""
    shown = f"{size.normalize():f} {unit}"
    if unit == "g":
        return float(size), f"printed {shown}"
    if unit == "kg":
        return float(size * 1000), f"printed {shown} = {float(size * 1000):g} g"
    if unit == "count":
        if not info["per_item"]:
            return None
        return float(size * Decimal(str(info["per_item"]))), f"{shown} x {info['per_item']} g per item (release record)"
    per_ml = info["per_ml"]
    source = "release record" if per_ml else "assumed, no density in the release"
    density = Decimal(str(per_ml or 1.0))
    millilitres = size * (1000 if unit == "l" else 1)
    return (
        float((millilitres * density).quantize(Decimal("0.01"))),
        f"printed {shown} = {millilitres.normalize():f} ml x {density} g/ml ({source})",
    )


def check_sheet(
    path: Path, release: Path = RELEASE, today: date | None = None
) -> tuple[list[str], list[tuple[dict, dict]]]:
    today = today or datetime.now(SINGAPORE).date()
    grams = release_grams(release)
    problems, good, ingredient_of_rank = [], [], {}
    for row in read_sheet(path):
        issues, product = check_row(row, grams, today)
        if ingredient_of_rank.setdefault(row["rank"], row["ingredient_id"]) != row["ingredient_id"]:
            issues.append(f"rank is already used by {ingredient_of_rank[row['rank']]}")
            product = None
        problems += [f"rank {row['rank']} (line {row['line']}): {issue}" for issue in issues]
        if product:
            good.append((row, product))
    return problems, good


def export(path: Path, release: Path = RELEASE, out: Path = RUNTIME, today: date | None = None) -> dict | None:
    problems, good = check_sheet(path, release, today)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"{len(problems)} problems; nothing written", file=sys.stderr)
        return None
    ingredients, counts = {}, {}
    for row, product in good:
        n = counts[row["rank"]] = counts.get(row["rank"], 0) + 1
        product = {"external_id": f"mn-{row['rank']}-{n}", **product}
        key = row["ingredient_id"][4:].lower()
        entry = ingredients.setdefault(key, {"status": "mapped", "review_status": "owner_recorded", "products": []})
        entry["products"].append(product)
        if AI_LOOKUP in row.get("note", ""):
            entry["review_status"] = "ai_lookup_unreviewed"
    seen = sorted(product["fetched_at"] for _, product in good)
    snapshot = {
        "snapshot_version": "manual-v1",
        "source": "manual",
        "fetched_from": seen[0] if seen else None,
        "fetched_to": seen[-1] if seen else None,
        "ingredients": dict(sorted(ingredients.items())),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(good)} products for {len(ingredients)} ingredients exported to {out}")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("validate", "export"))
    parser.add_argument("sheet", type=Path)
    args = parser.parse_args()
    if args.command == "export":
        sys.exit(0 if export(args.sheet) is not None else 1)
    problems, good = check_sheet(args.sheet)
    print("\n".join(problems))
    print(f"{len(good)} rows ok, {len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
