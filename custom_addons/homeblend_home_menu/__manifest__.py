{
    "name": "HomeBlend Home Menu",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "قائمة تطبيقات بملء الشاشة بأسلوب Odoo Enterprise",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "homeblend_home_menu/static/src/home_menu/home_menu_service.js",
            "homeblend_home_menu/static/src/home_menu/app_icons.js",
            "homeblend_home_menu/static/src/home_menu/home_menu.js",
            "homeblend_home_menu/static/src/home_menu/home_menu.xml",
            "homeblend_home_menu/static/src/home_menu/home_menu.scss",
            "homeblend_home_menu/static/src/navbar/navbar.js",
            "homeblend_home_menu/static/src/navbar/navbar.xml",
            "homeblend_home_menu/static/src/navbar/navbar.scss",
            "homeblend_home_menu/static/src/webclient/webclient.js",
            "homeblend_home_menu/static/src/webclient/webclient.xml",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
    "application": False,
}
