#!/usr/bin/env bash
# تثبيت خطوط تقارير أودو على نظام التشغيل.
#
# wkhtmltopdf 0.12.6 لا يستطيع تحميل الخطوط عبر @font-face، ويخرج النص فارغاً
# إذا كان اسم الخط في CSS معرّفاً كـ webfont فقط. لذلك يستثني موديول
# homeblend_fonts ملف خطوط أودو من حزمة التقارير، ويُقرأ الخط من fontconfig.
# شغّل هذا السكربت مرة واحدة على كل جهاز يولّد ملفات PDF.
set -euo pipefail

ODOO_FONTS="$(cd "$(dirname "$0")/.." && pwd)/odoo/addons/web/static/fonts"
DEST="${HOME}/.local/share/fonts/odoo-report-fonts"

mkdir -p "$DEST"
find "$ODOO_FONTS/google" "$ODOO_FONTS/lato" -type f \( -iname '*.ttf' -o -iname '*.otf' \) \
    -exec cp -f {} "$DEST/" \;
fc-cache -f "${HOME}/.local/share/fonts" >/dev/null

echo "تم تثبيت $(ls -1 "$DEST" | wc -l) ملف خط في $DEST"
echo "Tajawal: $(fc-match 'Tajawal') | عريض: $(fc-match 'Tajawal:weight=bold')"
