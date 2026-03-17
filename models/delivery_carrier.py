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
            _logger.warning(f"Product {product.id} ({product.name}) missing dimensions - cannot validate packaging fit")
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
                f"Product {product.id} ({product.product_length}x{product.product_width}x{product.product_height}) "
                f"does NOT fit in packaging {packaging.id} ({packaging.packaging_length}x{packaging.width}x{packaging.height})"
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
        # Calculate product weight
        product_weight = sum([
            (line.product_id.weight * line.product_uom_qty) 
            for line in order.order_line 
            if not line.is_delivery
        ]) or 0.0
        
        # Add packaging weight
        packaging_weight = packaging.weight or 0.0
        total_weight = product_weight + packaging_weight
        
        # Check against capacity
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
        Get list of packagings that fit ALL products in the order.
        
        Args:
            order: sale.order recordset
            
        Returns:
            product.packaging recordset of compatible packagings
        """
        # Get all products in order
        products = order.order_line.mapped('product_id').filtered(lambda p: p.type == 'product')
        
        if not products:
            return self.env['product.packaging']
        
        # Get all available packagings
        all_packagings = self.env['product.packaging'].search([
            ('shipper_package_code', '!=', False)
        ])
        
        compatible_packagings = self.env['product.packaging']
        
        for packaging in all_packagings:
            # Check if ALL products fit in this packaging
            all_fit = all([self._check_product_fits_packaging(p, packaging) for p in products])
            
            if all_fit:
                # Also check weight capacity
                fits_weight, total_weight = self._check_weight_capacity(order, packaging)
                if fits_weight:
                    compatible_packagings |= packaging
        
        _logger.info(
            f"Order {order.id}: Found {len(compatible_packagings)} compatible packagings: "
            f"{compatible_packagings.mapped('name')}"
        )
        
        return compatible_packagings

    def available_carriers(self, partner):
        """
        Override to filter carriers by compatible packaging.
        """
        carriers = super().available_carriers(partner)
        
        # Get the order from context (if available)
        order = self.env.context.get('order_id')
        if not order and isinstance(partner, models.Model):
            # Try to find draft order for this partner
            order = self.env['sale.order'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'draft')
            ], limit=1)
        
        if not order:
            return carriers
        
        # Get compatible packagings for this order
        compatible_packagings = self._get_compatible_packagings(order)
        
        if not compatible_packagings:
            _logger.warning(f"No compatible packagings found for order {order.id}")
            return carriers
        
        # Filter carriers to only those using compatible packaging
        compatible_carriers = carriers.filtered(
            lambda c: c.fedex_default_product_packaging_id in compatible_packagings
        )
        
        _logger.info(
            f"Order {order.id}: Filtered {len(carriers)} carriers to {len(compatible_carriers)} "
            f"with compatible packaging"
        )
        
        return compatible_carriers
