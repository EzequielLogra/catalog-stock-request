{
    "name": "HOS - Supervisor en la entrega",
    "summary": "Supervisor de la obra que recibe el material y firma el remito",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "author": "Logra",
    "category": "Warehouse Management",
    "website": "https://github.com/EzequielLogra/catalog-stock-request",
    "depends": [
        "stock_request_portal",
        "l10n_ar_stock_ux",
    ],
    "data": [
        "views/stock_picking_views.xml",
        "report/report_deliveryslip.xml",
    ],
    "installable": True,
    "application": False,
}
