"""Dated public API token rates used for estimates shown in Agent run reports (USD per million tokens)."""

from decimal import Decimal

# Source checked 2026-10-21 against the OpenAI model/pricing pages. Unknown models intentionally have no rate.
CHAT_RATES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "gpt-5.4-mini": (Decimal("0.75"), Decimal("0.075"), Decimal("4.50")),
}
EMBEDDING_RATES: dict[str, Decimal] = {
    "text-embedding-3-small": Decimal("0.02"),
    "text-embedding-3-large": Decimal("0.13"),
}


def model_name(vector_meta: str | None) -> str | None:
    return vector_meta.split("@", maxsplit=1)[0] if vector_meta else None
