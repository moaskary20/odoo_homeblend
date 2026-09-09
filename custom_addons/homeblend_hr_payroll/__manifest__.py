{
    "name": "Egyptian Payroll (HomeBlend)",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "قسائم رواتب مصرية مبسطة: تأمينات وضريبة دخل",
    "author": "HomeBlend",
    "license": "LGPL-3",
    "depends": ["homeblend_base", "hr", "account", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/payslip_data.xml",
        "views/payslip_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
}
