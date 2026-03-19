from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    def _check_product_fits_packaging(self, product, packaging):
        """
        Check if a product fits within packaging dimensions.

        Args:
            product: product.product recordset
            packaging: product.packaging recordset

        Returns:
            bool: True if product fits, False otherwise
        """
        # If product has no dimensions, we can't validate fit
        if not product.product_length or not product.product_width or not product.product_height:
            _logger.warning(
                f"Product {product.id} ({product.name}) missing dimensions "
                f"- cannot validate packaging fit"
            )
            return True  # Allow it through, but log warning

        # If packaging has no dimensions, we can't validate
        if not packaging.packaging_length or not packaging.width or not packaging.height:
            _logger.warning(f"Packaging {packaging.id} ({packaging.name}) missing dimensions")
            return True

        # Check if product fits in packaging (all dimensions must fit)
        fits = (
            product.product_length <= packaging.packaging_length and
            product.product_width <= packaging.width and
            product.product_height <= packaging.height
        )

        if not fits:
            _logger.info(
                f"Product {product.id} "
                f"({product.product_length}x{product.product_width}x{product.product_height}) "
                f"does NOT fit in packaging {packaging.id} "
                f"({packaging.packaging_length}x{packaging.width}x{packaging.height})"
            )

        return fits

    def _check_weight_capacity(self, order, packaging):
        """
        Check if order weight fits within packaging capacity.
        Includes both product weight AND packaging weight.

        Args:
            order: sale.order recordset
            packaging: product.packaging recordset

        Returns:
            tuple: (bool fits, float total_weight)
        """
        product_weight = sum([
            (line.product_id.weight * line.product_uom_qty)
            for line in order.order_line
            if not line.is_delivery
        ]) or 0.0

        packaging_weight = packaging.weight or 0.0
        total_weight = product_weight + packaging_weight

        max_weight = packaging.max_weight or float('inf')
        fits = total_weight <= max_weight

        if not fits:
            _logger.info(
                f"Order {order.id} total weight {total_weight} lbs "
                f"(product: {product_weight} + packaging: {packaging_weight}) "
                f"exceeds packaging capacity {max_weight} lbs"
            )

        return fits, total_weight

    @api.model
    def _get_compatible_packagings(self, order):
        """
        Get all packagings that fit ALL products in the order (dimensions + weight).

        Args:
            order: sale.order recordset

        Returns:
            product.packaging recordset of compatible packagings
        """
        products = order.order_line.mapped('product_id').filtered(
            lambda p: p.type == 'product'
        )

        if not products:
            return self.env['product.packaging']

        all_packagings = self.env['product.packaging'].search([
            ('shipper_package_code', '!=', False)
        ])

        compatible_packagings = self.env['product.packaging']

        for packaging in all_packagings:
            all_fit = all(
                self._check_product_fits_packaging(p, packaging) for p in products
            )
            if all_fit:
                fits_weight, _ = self._check_weight_capacity(order, packaging)
                if fits_weight:
                    compatible_packagings |= packaging

        _logger.info(
            f"Order {order.id}: Found {len(compatible_packagings)} compatible packagings: "
            f"{compatible_packagings.mapped('name')}"
        )

        return compatible_packagings

    @api.model
    def _get_offered_packagings(self, order):
        """
        From all compatible packagings, return only the tightest fit plus
        a configurable number of additional size steps.

        The intent is to avoid presenting the customer with a long list of
        oversized box options.  By default we show the minimum viable box
        and one size larger (useful e.g. to suggest "buy two paddles for
        nearly the same shipping cost").  The number of extra steps is
        controlled by the system parameter:

            smart_packaging.upsell_steps   (default: 1)

        Set to 0 to show only the best-fit box.
        Set to 2 or more to allow more upsell tiers.

        Args:
            order: sale.order recordset

        Returns:
            product.packaging recordset — the subset to offer
        """
        compatible_packagings = self._get_compatible_packagings(order)

        if not compatible_packagings:
            return compatible_packagings

        # Read configurable upsell steps (how many sizes above minimum to show)
        try:
            param = self.env['ir.config_parameter'].sudo().get_param(
                'smart_packaging.upsell_steps', default='1'
            )
            upsell_steps = int(param)
        except (ValueError, TypeError):
            upsell_steps = 1

        # Sort compatible packagings by volume ascending (smallest first).
        # Packages missing any dimension get float('inf') so they sort to the
        # end rather than the front (0-volume would otherwise make them appear
        # as the "best fit" for every order).
        def _volume(pkg):
            l = pkg.packaging_length or 0.0
            w = pkg.width or 0.0
            h = pkg.height or 0.0
            if not l or not w or not h:
                return float('inf')
            return l * w * h

        sorted_packagings = sorted(compatible_packagings, key=_volume)

        # Allow minimum box + upsell_steps additional tiers
        offered = sorted_packagings[: upsell_steps + 1]

        offered_set = self.env['product.packaging']
        for pkg in offered:
            offered_set |= pkg

        _logger.info(
            f"Order {order.id}: upsell_steps={upsell_steps}, "
            f"offering {len(offered_set)} of {len(compatible_packagings)} compatible packagings: "
            f"{offered_set.mapped('name')}"
        )

        return offered_set

    def available_carriers(self, partner):
        """
        Override to filter carriers by offered packaging only.

        Two-stage filter:
          1. (existing) Remove carriers whose box is too small for the order.
          2. (new)      Remove carriers whose box is larger than needed,
                        keeping only the best fit + upsell_steps extra sizes.
        """
        carriers = super().available_carriers(partner)

        # Resolve the order from context or partner fallback
        order = self.env.context.get('order_id')
        if not order and isinstance(partner, models.Model):
            order = self.env['sale.order'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'draft'),
            ], limit=1)

        if not order:
            return carriers

        # Get the narrowed set of packagings to offer
        offered_packagings = self._get_offered_packagings(order)

        if not offered_packagings:
            _logger.warning(
                f"Order {order.id}: No compatible packagings found — "
                f"returning all carriers unfiltered"
            )
            return carriers

        # Filter carriers to only those using an offered packaging.
        # Carriers with no fedex_default_product_packaging_id (e.g. Fixed Price,
        # USPS, or any non-FedEx provider) are always passed through — the
        # packaging filter only applies to carriers that explicitly declare a
        # box type.
        offered_carriers = carriers.filtered(
            lambda c: not c.fedex_default_product_packaging_id
                      or c.fedex_default_product_packaging_id in offered_packagings
        )

        _logger.info(
            f"Order {order.id}: Narrowed {len(carriers)} carriers → "
            f"{len(offered_carriers)} with offered packaging "
            f"(upsell filter applied)"
        )

        return offered_carriers