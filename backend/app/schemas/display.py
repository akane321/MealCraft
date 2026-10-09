"""How a catalog title or ingredient line reads to the household, cleaned when it is shown (owner, 2026-10-04).

The catalog keeps what the source sites wrote, ids and all; search and matching read that. Only what the
product API and the assistant's replies show goes through here, so the same dish reads the same on a card,
in a sheet and in a sentence:

- "Chinese Egg Flower Soup (Ww)", "Pork Tortillas Adobo - Ww" -> "Chinese Egg Flower Soup", "Pork Tortillas
  Adobo": a recipe site's tag (Weight Watchers, once-a-month cooking, America's Test Kitchen, Taste of Home,
  ...) is not part of the dish's name, nor is a trailing comma or full stop;
- "Dinner Tonight: Kimchi Chahan (Fried Rice) Recipe" -> "Kimchi Chahan (Fried Rice)": a recipe site's column
  ("Dinner Tonight:", "Seriously Asian:", ...) and its closing "Recipe" are not part of the dish's name either;
- "Pot Pie(Square Dumplings)" -> "Pot Pie (Square Dumplings)" ("Morgan'S" -> "Morgan's" is the import's,
  `app.data.release_v2.display_title`);
- "Tsukemono – Japanese Pickles", "Berbere -- Ethiopian Spice Paste" -> "Tsukemono (Japanese Pickles)",
  "Berbere (Ethiopian Spice Paste)": in "Cannelloni · Tsukemono – Japanese Pickles · Pot Pie" a dash reads as
  one more dish;
- an ingredient's preparation "light; thinly sliced; white and green parts only" (fragments the release
  split "2 green onions, white and light green parts only, thinly sliced" into, sorted, with "light" cut out
  of its phrase) -> "white and light green parts only, thinly sliced".

A title is cleaned one ", "-separated part at a time, so a list of titles joined with ", " (or "、") cleans
to the same text as the titles cleaned one by one.
"""

import html
import re
from typing import Annotated

from pydantic import PlainSerializer

TAGS = r"(?:ww|oamc|omac|atk|scd|sbd|toh)"
# "(Ww)", or "- Ww" at the end.
SCRAPER_TAG = re.compile(rf"\s*\({TAGS}\)|\s*[-–—]+\s*{TAGS}$", re.IGNORECASE)
# Serious Eats' columns, as the catalog has them (2026-10-09 rehearsal: "Dinner Tonight: Kimchi Chahan (Fried Rice)
# Recipe"), and the "Recipe" its titles end with ("Mongolian Beef For 4: $10 Recipe!" keeps both).
COLUMN = re.compile(
    r"^(?:dinner tonight|seriously asian|serious (?:salads|heat)|breakfast flash|cook the book"
    r"|the secret ingredient \([^)]*\))\s*:\s*|\s+recipe$",
    re.IGNORECASE,
)
GLUED_OPEN = re.compile(r"(?<=[^\s(])\(")
GLUED_CLOSE = re.compile(r"\)(?=\w)")
DASH_BEFORE_PAREN = re.compile(r"\s*[-–—]\s*(?=\()")
# A dash (or "--") a space sets apart; "Na-Mool" and "Korean-Style" keep theirs.
DASH = re.compile(r"\s*[-–—]+\s+|\s+[-–—]+\s*")
# "Thai Fried Bananas,", "Tempura Avocado." (not "Korean B.B.Q.").
TRAILING = re.compile(r"[\s,;:]+$|(?<=[a-z])\.$")
PARTS = re.compile(r"(, |、)")
# Fragments the release parser left on their own: connectives, and the "None" of "4 None bread rolls".
NOT_PREPARATION = {"and", "or", "none", "more"}


def _part(text: str) -> str:
    text = html.unescape(text)
    text = COLUMN.sub("", SCRAPER_TAG.sub("", text).strip())
    text = GLUED_CLOSE.sub(") ", GLUED_OPEN.sub(" (", DASH_BEFORE_PAREN.sub(" ", text)))
    pieces = DASH.split(text)
    if len(pieces) == 2 and "(" not in text and all(piece.strip() for piece in pieces):
        text = f"{pieces[0]} ({pieces[1]})"
    else:
        text = " – ".join(pieces)
    return TRAILING.sub("", " ".join(text.split()))


def shown_title(title: str) -> str:
    return "".join(part if index % 2 else _part(part) for index, part in enumerate(PARTS.split(title)))


def shown_preparation(preparation: str | None, original_text: str | None = None) -> str | None:
    """The preparation as the recipe wrote it, in its order, without fragments that are not one."""
    if not preparation:
        return preparation
    source = (original_text or "").lower()
    parts = [part.strip() for part in preparation.split(";") if part.strip().lower() not in NOT_PREPARATION]
    for word in [part for part in parts if " " not in part]:
        # A word cut out of another fragment goes back in: "light" into "white and light green parts only".
        for index, phrase in enumerate(parts):
            words = phrase.split()
            whole = [" ".join([*words[:at], word, *words[at:]]) for at in range(1, len(words))]
            found = next((text for text in whole if text.lower() in source), None)
            if found:
                parts[index] = found
                parts.remove(word)
                break

    def position(part: str) -> int:
        at = source.find(part.lower())
        return at if at >= 0 else len(source)

    return ", ".join(sorted(parts, key=position)) or None


ShownTitle = Annotated[str, PlainSerializer(shown_title, return_type=str, when_used="json")]
