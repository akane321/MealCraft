# FairPrice page fixtures

Minimal search pages, one per degradation mode the product search must name (see
`docs/design/external-retrieval-rag.md`, FairPrice robustness). Each is replayed by
`backend/tests/test_products.py::test_every_fairprice_page_mode_has_a_named_outcome`.
They are hand-written shapes of the `__NEXT_DATA__` payload, not captured pages.
