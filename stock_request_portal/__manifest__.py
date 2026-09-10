{
    "name": "Stock Request Portal",
    "summary": "Allow portal users (clients) to create stock request orders from /my",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "Logra",
    "category": "Warehouse Management",
    "website": "https://github.com/EzequielLogra/catalog-stock-request",
    "depends": ["stock_request", "catalog_stock_request", "portal", "website"],
    "data": [
        "views/res_partner_views.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "stock_request_portal/static/src/js/stock_request_form.js",
            "stock_request_portal/static/src/css/stock_request_form.css",
        ],
    },
    "installable": True,
    "application": False,
}
