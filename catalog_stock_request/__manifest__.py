{
    "name": "Catalog Stock Request",
    "summary": "Partial stock reservation and purchase split for stock requests",
    "version": "19.0.1.2.0",
    "license": "LGPL-3",
    "author": "Logra",
    "category": "Warehouse Management",
    "website": "https://github.com/EzequielLogra/catalog-stock-request",
    "depends": ["stock_request", "stock_request_purchase"],
    "data": [
        "views/res_partner_views.xml",
        "views/stock_request_views.xml",
        "views/stock_request_order_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
}
