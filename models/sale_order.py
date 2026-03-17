from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_delivery_methods(self):
        """
        Override to pass order context for packaging filtering.
        """
        # Add order to context so delivery_carrier can access it
        self = self.with_context(order_id=self)
        return super()._get_delivery_methods()

    def _calculate_total_shipping_weight(self, packaging=None):
        """
        Calculate total shipping weight including packaging.
        
        Args:
            packaging: product.packaging recordset (optional)
            
        Returns:
            float: Total weight in lbs (product weight + packaging weight)
        """
        # Calculate product weight
        product_weight = sum([
            (line.product_id.weight * line.product_uom_qty) 
            for line in self.order_line 
            if not line.is_delivery and line.product_id.type == 'product'
        ]) or 0.0
        
        # Add packaging weight if provided
        packaging_weight = 0.0
        if packaging:
            packaging_weight = packaging.weight or 0.0
        
        total_weight = product_weight + packaging_weight
        
        _logger.info(
            f"Order {self.id} shipping weight: "
            f"products={product_weight} lbs + packaging={packaging_weight} lbs = {total_weight} lbs"
        )
        
        return total_weight

    def _get_optimal_packaging(self):
        """
        Select the smallest packaging that fits all products.
        
        Returns:
            product.packaging recordset or False
        """
        # Get compatible packagings
        DeliveryCarrier = self.env['delivery.carrier']
        compatible_packagings = DeliveryCarrier._get_compatible_packagings(self)
        
        if not compatible_packagings:
            return False
        
        # Sort by volume (length * width * height) to get smallest that fits
        packagings_with_volume = []
        for pkg in compatible_packagings:
            volume = (pkg.packaging_length or 0) * (pkg.width or 0) * (pkg.height or 0)
            packagings_with_volume.append((pkg, volume))
        
        # Sort by volume ascending (smallest first)
        packagings_with_volume.sort(key=lambda x: x[1])
        
        optimal = packagings_with_volume[0][0]
        
        _logger.info(
            f"Order {self.id}: Selected optimal packaging: {optimal.name} "
            f"({optimal.packaging_length}x{optimal.width}x{optimal.height})"
        )
        
        return optimal
