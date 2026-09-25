"""Tutorial ranking v1, frozen as it shipped in #160 (f44ea43), so later policies are compared with it.

Do not edit: it is the baseline, not a live ranker.
"""

import re

from app.retrieval.tutorials import PROTEIN_WORDS, TutorialCandidate

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(value.casefold()))


def rank_v1(
    *,
    recipe_title: str,
    cuisine: str,
    ingredient_names: list[str],
    language: str,
    candidates: list[TutorialCandidate],
) -> list[tuple[float, list[str], TutorialCandidate]]:
    recipe_tokens = tokenize(recipe_title)
    cuisine_tokens = tokenize(cuisine)
    ingredient_tokens = set().union(*(tokenize(name) for name in ingredient_names[:3])) if ingredient_names else set()
    all_ingredient_tokens = set().union(*(tokenize(name) for name in ingredient_names)) if ingredient_names else set()
    language_token = language.casefold().strip()

    ranked: list[tuple[float, list[str], TutorialCandidate]] = []
    for candidate in candidates:
        if not candidate.embeddable:
            continue

        title_tokens = tokenize(candidate.title)
        if title_tokens.intersection(PROTEIN_WORDS) - recipe_tokens - all_ingredient_tokens:
            continue
        score = 0.0
        reasons: list[str] = []

        title_matches = len(recipe_tokens.intersection(title_tokens))
        if title_matches:
            score += title_matches * 10.0
            reasons.append(f"recipe title overlap: {title_matches}")

        cuisine_matches = len(cuisine_tokens.intersection(title_tokens))
        if cuisine_matches:
            score += cuisine_matches * 3.0
            reasons.append(f"cuisine overlap: {cuisine_matches}")

        ingredient_matches = len(ingredient_tokens.intersection(title_tokens))
        if ingredient_matches:
            score += ingredient_matches * 2.0
            reasons.append(f"ingredient overlap: {ingredient_matches}")

        if title_tokens.intersection({"tutorial", "recipe", "cook", "cooking"}):
            score += 4.0
            reasons.append("tutorial intent")

        if candidate.duration_seconds is not None and 120 <= candidate.duration_seconds <= 1800:
            score += 2.0
            reasons.append("practical duration")

        if language_token and candidate.language_hint == language_token:
            score += 1.0
            reasons.append("language match")

        # Generic points (intent, duration, language) never qualify a video, and
        # one shared word is not the same dish: "Lemon Chicken" is no how-to for
        # "Chicken Broccoli Rice". The video title must carry two words of the
        # dish's name (all of them for a one-word name).
        if title_matches < min(2, len(recipe_tokens)):
            continue
        ranked.append((score, reasons, candidate))

    ranked.sort(key=lambda item: (-item[0], item[2].video_id))
    return ranked
