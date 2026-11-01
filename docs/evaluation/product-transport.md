# Product transport for the held-out conversation harness

This is apparatus, **not run admission, a freeze, a scored evaluation or a result**. It connects the product to the
[conversation harness](conversation-adapter-phase1.md) so that the product receives the same chat messages as every
other system (`ADR-0092` item 2, `ADR-0098`).

`backend/app/evaluation/product_transport.py` gives `ProductTransport(client).responder()`, a harness responder for
one case.

- **Chat only.** The first turn opens a product session with the user's message; later turns send further messages
  to that session. The fixed confirmation message is one of those messages: the product's chat entry recognises it
  while a plan card or a change preview waits (`ADR-0098`). The transport never calls a confirm or discard action.
- **Only the message.** The product receives `{"message": ...}`. The shared instructions are for model arms and are
  not sent; the clock reaches the product through the harness's injected clock.
- **Actual answers.** Each answer is read into the common output by `normalize_product`, with the session's saved
  plan fetched from the plans endpoint when there is one.
- **One responder, one case.** A second first turn on the same responder is an error, so a session never carries
  over to the next case.
- **Change previews wait like plan cards.** In `normalize_product` a change preview that the session links and has
  not applied marks the turn as awaiting confirmation, so a change to a saved week gets the same one confirmation
  message as a new plan. An applied preview, or one left over from an earlier turn, does not.
- **Failures are errors.** A non-success status raises `ProductTransportError`; it is never reported as a refusal or
  an infeasible request.

Not covered: creating a household or profile and authenticating the client (the caller prepares the run), sealed
file loading, scoring, mapping the product's native constraint echoes to the neutral field dictionary, catalog
ID matching, the neutrality review and registration of the confirmation bytes, run
admission and the freeze.

```text
PYTHONPATH=backend python -m pytest backend/tests/test_product_transport.py -p no:cacheprovider --basetemp <new-temporary-directory>
```
