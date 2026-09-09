{
    "name": "HomeBlend Base",
    "version": "19.0.1.4.2",
    "category": "Hidden",
    "summary": "أساس شركتَي Home Blend و Art Casa",
    "author": "HomeBlend",
    "license": "LGPL-3",
    "depends": ["base", "contacts", "account", "product", "l10n_eg", "l10n_eg_edi_eta"],
    "data": [
        "security/homeblend_security.xml",
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
