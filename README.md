# delivery_smart_packaging

Odoo 14 module that intelligently filters shipping carrier options at checkout
based on product dimensions and packaging fit. Prevents both undersized and
oversized box options from being presented to the customer.

## What It Does

### Lower-bound filter (original)
Removes carriers whose assigned box is too small to fit the products in the
order. A 79" paddle will never be offered shipping in a 10" box.

### Upper-bound filter (added March 2026)
Removes carriers whose assigned box is unnecessarily large for the order.
A drain plug will not be offered paddle box shipping rates.

The filter keeps the **minimum viable box** plus a configurable number of
additional size steps ("upsell tiers") — useful for encouraging customers
to order multiples for nearly the same shipping cost.

### Non-FedEx carrier passthrough
Carriers without a `fedex_default_product_packaging_id` (Fixed Price, USPS,
flat rate, etc.) always pass through the filter unaffected.

### Zero-dimension package handling
Packages missing any dimension are sorted to the end of the size ranking
rather than the front, preventing them from being incorrectly treated as
the "best fit" for every order.

## Configuration

### System Parameter
Add this key in Settings → Technical → Parameters → System Parameters:

| Key | Default | Effect |
|-----|---------|--------|
| `smart_packaging.upsell_steps` | `1` | Number of box sizes above minimum to show |

- `0` = best-fit box only
- `1` = best fit + one size up (default — good for "buy two paddles" upsell)
- `2` = best fit + two sizes up

If the parameter does not exist, the system defaults to `1`.

## Dependencies

- Odoo 14 `delivery` module
- `website_delivery_website_filter` — **required** for order context to be
  passed correctly to the packaging filter. The two modules coordinate through
  a shared `order_id` context variable. If `website_delivery_website_filter`
  is not installed, the packaging filter will fall back to a partner-based
  order search which may select the wrong order in multi-website sessions.

## Module Coordination

This module overrides `delivery.carrier.available_carriers()`. The order
context (`order_id`) is injected by `website_delivery_website_filter`'s
`_get_delivery_methods()` override and consumed here. The MRO (Method
Resolution Order) between these two modules is intentional — do not add
a `_get_delivery_methods()` override in this module as it will conflict.

## Package Type Data Requirements

For the filter to work correctly, all `product.packaging` records used as
carrier default package types should have all three dimensions set
(length × width × height). Records with missing dimensions are allowed
through with a warning log entry.

## Repositories

- This module: https://github.com/l-arnold/delivery-smart-packaging
- Companion module: https://github.com/l-arnold/website-delivery-multisite-tuning

## License

LGPL-3