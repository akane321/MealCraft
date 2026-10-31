"""One-off capture of FairPrice's "Halal" dietary attribute for the release snapshot's meat products.

    uv run --project backend python -m app.data.capture_fairprice_halal      # from the repository root

The snapshot (`data/products/fairprice-v2-snapshot.json`) carries no dietary attribute. For its products of
`needs_certification` ingredients this reads FairPrice's public product listing, the same GET the app's provider
makes, and records whether the listing's `metaData["Dietary Attributes"]` contains "Halal". Writes
`data/ingredients/fairprice-halal-v1.json`: `{external_id: {"halal_certified": true | null, "observed_at": ...}}`
under `products`. A product listed without the attribute is `null` (unknown), never `false`; one the listing no
longer returns is named under `not_found` and has no entry.

Public GETs only: no login, at most one request a second, at most `MAX_REQUESTS` in all. A response that is not
200, or a page without the listing data (a bot check), stops the run without writing anything.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.paths import data_root
from app.data.halal import CERTIFICATION_FILE, halal_labels
from app.planning.grocery_estimator import release_snapshot
from app.products.provider import NEXT_DATA_PATTERN, normalize_search_text

BASE_URL = "https://www.fairprice.com.sg"
MAX_REQUESTS = 400
SECONDS_BETWEEN_REQUESTS = 1.0
TIMEOUT_SECONDS = 20


class CaptureStopped(RuntimeError):
    """A response that is not a plain listing: stop and report, never work around it."""


def snapshot_products() -> dict[str, dict]:
    """external_id -> the snapshot product, for the ingredients that need a certified product."""
    products: dict[str, dict] = {}
    for name, entry in sorted(release_snapshot().items()):
        label = halal_labels().get(name)
        if label and label["needs_certification"]:
            for product in entry.get("products", []):
                products.setdefault(product["external_id"], product)
    return products


def fetch_listing(query: str, base_url: str) -> list[dict]:
    """The listing records of one search page; anything but a 200 page with its data raises CaptureStopped."""
    url = f"{base_url}/product-listing?{urlencode({'pageType': 'search', 'url': normalize_search_text(query)})}"
    request = Request(
        url, headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "MealCraft/0.1 academic prototype"}
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            if response.status != 200:
                raise CaptureStopped(f"{url}: HTTP {response.status}")
            html = response.read().decode("utf-8")
    except URLError as error:  # HTTPError (any non-200) is a URLError
        raise CaptureStopped(f"{url}: {error}") from error
    match = NEXT_DATA_PATTERN.search(html)
    if match is None:
        raise CaptureStopped(f"{url}: no __NEXT_DATA__ in the page (a bot check or a changed site)")
    try:
        data = json.loads(match.group(1))["props"]["pageProps"]["data"]["data"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise CaptureStopped(f"{url}: listing data not recognised") from error
    return (data.get("product") or []) if isinstance(data, dict) else []


def halal_facts(records: list[dict]) -> dict[str, bool | None]:
    """external_id -> True when the record's Dietary Attributes contain "Halal", else None."""
    facts: dict[str, bool | None] = {}
    for record in records:
        dietary = (record.get("metaData") or {}).get("Dietary Attributes") or []
        facts[str(record.get("clientItemId") or record.get("id"))] = True if "Halal" in dietary else None
    return facts


def capture(base_url: str, *, sleep=time.sleep) -> dict:
    wanted = snapshot_products()
    found: dict[str, bool | None] = {}
    requests = 0

    def search(query: str) -> None:
        nonlocal requests
        if requests >= MAX_REQUESTS:
            raise CaptureStopped(f"request budget of {MAX_REQUESTS} spent")
        if requests:
            sleep(SECONDS_BETWEEN_REQUESTS)
        requests += 1
        for external_id, fact in halal_facts(fetch_listing(query, base_url)).items():
            if external_id in wanted:
                found[external_id] = fact if found.get(external_id) is None else found[external_id]

    for query in sorted({product["query"] for product in wanted.values()}):
        search(query)
    for external_id, product in sorted(wanted.items()):  # not on the page of its own query: search it by name
        if external_id not in found:
            search(product["name"])

    observed_at = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        "schema_version": "fairprice-halal-v1",
        "source": "FairPrice public product listing, metaData['Dietary Attributes'] contains 'Halal'",
        "observed_at": observed_at,
        "requests": requests,
        "products": {
            external_id: {"halal_certified": fact, "observed_at": observed_at}
            for external_id, fact in sorted(found.items())
        },
        "not_found": sorted(set(wanted) - set(found)),
    }


def main() -> None:
    try:
        result = capture(BASE_URL)
    except CaptureStopped as stop:
        raise SystemExit(f"stopped, nothing written: {stop}") from stop
    path = data_root() / CERTIFICATION_FILE
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    certified = sum(1 for fact in result["products"].values() if fact["halal_certified"])
    print(
        f"{result['requests']} requests; {len(result['products'])} products observed, {certified} halal, "
        f"{len(result['not_found'])} not found -> {path}"
    )


if __name__ == "__main__":
    main()
