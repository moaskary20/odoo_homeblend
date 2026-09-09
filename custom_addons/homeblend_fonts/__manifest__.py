{
    "name": "HomeBlend Tajawal Font",
    "version": "19.0.1.1.0",
    "category": "Theme",
    "summary": "خط Tajawal من Google Fonts في كل واجهات النظام والتقارير",
    "author": "HomeBlend",
    "license": "LGPL-3",
    "depends": ["web"],
    "post_init_hook": "post_init_hook",
    "assets": {
        # قبل متغيّرات أودو حتى تتفرّع منه كل متغيّرات الخطوط
        "web._assets_primary_variables": [
            ("prepend", "homeblend_fonts/static/src/scss/tajawal_variables.scss"),
        ],
        "web.assets_backend": [
            "homeblend_fonts/static/src/scss/tajawal_face.scss",
        ],
        "web.assets_frontend": [
            "homeblend_fonts/static/src/scss/tajawal_face.scss",
        ],
        # wkhtmltopdf 0.12.6 يفشل في تحميل أي خط معرّف بـ @font-face، وحين
        # يكون اسم الخط في CSS معرّفاً كـ webfont فقط يخرج النص فارغاً تماماً.
        # لذلك نُخرج ملف خطوط أودو من حزمة التقارير ليُقرأ الخط من fontconfig،
        # فيظهر Tajawal بأوزانه الحقيقية. يتطلب تشغيل:
        # scripts/install_report_fonts.sh
        "web.report_assets_common": [
            ("remove", "web/static/fonts/fonts.scss"),
        ],
    },
    "installable": True,
    "auto_install": True,
}
