{
    "name": "Egyptian Payroll (HomeBlend)",
    "version": "19.0.1.1.0",
    "category": "Human Resources",
    "summary": "قسائم رواتب مصرية: حضور، إجازة، سلف، تأمينات وضريبة دخل",
    "author": "HomeBlend",
    "license": "LGPL-3",
    "depends": ["homeblend_base", "hr", "hr_attendance", "hr_holidays", "account", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/payslip_data.xml",
        "views/res_company_views.xml",
        "views/advance_views.xml",
        "views/payslip_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
}
