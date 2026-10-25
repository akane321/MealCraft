"""Fail-closed rights metadata for recipes acquired outside the curated catalog."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

AcquisitionMethod = Literal["web_search", "user_supplied"]
POLICY_VERSION = "external-source-policy-v1"
UNVERIFIED_LICENSE = "Unverified; structured facts only; source steps paraphrased"


@dataclass(frozen=True)
class SourcePolicyDecision:
    tier: Literal[2]
    license_status: Literal["unverified"]
    license_note: str
    policy_id: str
    policy_reference: str | None


# TheMealDB's terms apply to API-returned content and disallow website scraping.
# Web-search pages (and client-supplied provenance) do not prove API provenance or
# third-party rights, so this entry records the restriction without promoting it.
_DOMAIN_POLICY_REFERENCES = {
    "themealdb.com": "https://www.themealdb.com/terms_of_use.php",
}


def _host_matches(host: str, registered_domain: str) -> bool:
    return host == registered_domain or host.endswith(f".{registered_domain}")


def resolve_external_source_policy(source_url: str, *, acquisition_method: AcquisitionMethod) -> SourcePolicyDecision:
    """Ignore caller-provided tier/licence claims until page-specific rights are reviewed."""
    host = (urlsplit(source_url).hostname or "").casefold().rstrip(".")
    reference = next(
        (url for domain, url in _DOMAIN_POLICY_REFERENCES.items() if _host_matches(host, domain)),
        None,
    )
    policy_id = (
        "themealdb-web-search-tier2" if reference and acquisition_method == "web_search" else "unverified-source-tier2"
    )
    return SourcePolicyDecision(
        tier=2,
        license_status="unverified",
        license_note=UNVERIFIED_LICENSE,
        policy_id=policy_id,
        policy_reference=reference,
    )
