# Product observations as Planning inputs

`app.planning.product_input.product_input` converts an existing `ProductResponse`
into a `PlanningProductOption` using an explicitly supplied canonical ingredient
ID and required unit. It does not search, rank mappings, normalize units or infer
ingredients from display names. Mapping accuracy remains upstream responsibility
under the [product grounding contract](fairprice-product-grounding.md).

```python
from app.planning.product_input import product_input

result = product_input(observation, ingredient_id="rice", required_unit="g")
if result.option is not None:
    options.append(result.option)
```

The returned observation is a detached copy retaining the source, URL, timestamp
and other original fields. The projection carries only package arithmetic and
availability. A caller must retain the observation together with RetrievalTrace,
mapping evidence and the enclosing snapshot version. This adapter does not
certify source authenticity, freshness, mapping accuracy or catalog completeness.

Missing package quantity or unit, incompatible units, nonpositive or nonfinite
package size, invalid or sub-cent prices, missing identity/URL and naive
timestamps produce sorted issue codes with no arithmetic option. Values are not
guessed or rounded. A kilogram observation requested in grams is rejected until
an upstream canonical conversion supplies matching units.

An unavailable product with otherwise complete facts produces an option with
`available=False`. The existing package optimizer excludes it. Valid zero-price
observations remain zero; the adapter does not infer promotion conditions.

This is a single-observation projection. The caller must check duplicate product
identities across the complete packet and preserve rejected observations as
diagnostics rather than treating a reduced candidate list as complete. An empty
issue tuple only means these projection checks passed.

Rejected observations may retain invalid numeric source values for local
diagnosis. Use issue codes for error responses; do not serialize raw malformed
observations as valid JSON or present them as usable prices.

No product API, Retrieval implementation, persistence or shared schema changes.
Recipe serving bases, meal-type mapping, nutrition scope and legacy budget
conversion are separate integration concerns.
