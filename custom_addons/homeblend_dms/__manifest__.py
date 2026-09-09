{
    "name": "HomeBlend Documents",
    "version": "19.0.1.2.0",
    "category": "Productivity",
    "summary": "وثائق ومرفقات وتوقيع إلكتروني مبسط",
    "author": "HomeBlend",
    "license": "LGPL-3",
    "depends": ["homeblend_base", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "security/dms_security.xml",
        "data/document_data.xml",
        "views/document_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
}
