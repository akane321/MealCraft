# Authored held-out episodes

One JSON file per episode, named `<episode_id>.json`. Start from
`../TEMPLATE-episode.json` and read
[the authoring guide](../../../../../docs/evaluation/heldout-authoring-guide.md)
before writing the first one.

Check your work at any time, from the repository root, with no container:

```bash
python scripts/check_heldout_episodes.py
```

Do not edit an episode after the set is frozen. Corrections create a new set
version, so that previously reported results stay interpretable.
