# Role rules and the reviewer table: owner decisions of 2026-10-23

This dated packet implements the owner's 2026-10-23 role decisions (staple
vocabulary, protein-less tuber mains, bean-led sides, condiment-type protein
sides) and the human reviewer's wider role options. It is not an acceptance
tool: no row here is a human label, and the failed model batch stays gated
with its values, provenance and review marks unchanged. No model was called.

## Files

- [review.md](review.md) and its JSON:
  - counts of the frozen batch (consistent, grey, blocked, incomplete)
    before and after, with the model prompt's options and with the
    reviewer's options;
  - every frozen row with its stored role, the rule's suggestion, the
    reviewer's roles, its status before and after, and whether a rule newer
    than the batch (ADR-0082/0085, or the 2026-10-23 decisions) changed its
    suggestion. A disagreement on such a row is not a model error by itself;
  - every catalog rule change against the base, and a fixed-seed sample of
    them pending human review.

The reviewer's roles add `staple` and `one_bowl` when the rule's staple share
is 0, because the rules' starch vocabulary may not know the dish's starch.
A tuber or plantain dish whose sweeteners make 8% or more of it (candied
yams, Šúľance s Makom) is not a staple and is not offered these roles.
The roles the model prompt offers do not change
(`backend/app/data/recipe_tags.py`, `review_roles`).

## Reproduction

From `backend`, offline and without a `.env`:

```text
python -m app.data.recipe_tags
python ../data-engineering/scripts/role_review_table.py --base <base>
```

`<base>` is the revision recorded in `review.json`. The script reads the rules
of `<base>` and of the revision before ADR-0082 (`--pre-0082`) from git; it
never writes tags. Release data is unchanged by this packet; unit-weight fixes
(pizza crust, lasagna sheets and similar) are a separate release rebuild and
will move some rows again.
