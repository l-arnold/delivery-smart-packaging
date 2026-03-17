{
    'name': 'Delivery Smart Packaging',
    'version': '14.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Auto-select packaging based on product dimensions and weight',
    'description': '''
Intelligent Packaging Selection for Shipping
=============================================

Automatically filters shipping methods based on:
- Product dimensions (length × width × height)
- Packaging capacity (max_weight)
- Dimensional fit validation
- Packaging weight calculation (product weight + box weight)

Features:
- Hides shipping methods with incompatible packaging
- Auto-selects appropriate box size per product
- Adds packaging weight to total shipping weight for accurate quotes
- Prevents shipping errors from oversized items
- Supports multi-product orders with mixed dimensions

Fixes:
- FedEx quotes now include box weight (was only product weight)
- Dimensional validation prevents impossible shipments
    ''',
    'author': 'Nomadic Inc.',
    'website': 'https://nomadic.net',
    'depends': [
        'delivery',
        'product_dimension',
        'product_packaging_dimension',
    ],
    'data': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
