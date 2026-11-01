import base64
import io

import xlsxwriter

from odoo import models, _
from odoo.exceptions import UserError


class HomeblendXlsxExportMixin(models.AbstractModel):
    _name = "homeblend.xlsx.export.mixin"
    _description = "تصدير Excel مشترك"

    def _hb_xlsx_download(self, filename, sheets):
        """sheets: list of dicts {name, headers, rows, notes?}
        rows: list of list values; numbers written as numbers.
        """
        if not self:
            raise UserError(_("لا توجد بيانات للتصدير."))
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "align": "right"})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "align": "right", "border": 1})
        text_fmt = workbook.add_format({"align": "right", "border": 1})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "align": "left", "border": 1})
        for sheet_data in sheets:
            sheet = workbook.add_worksheet((sheet_data.get("name") or "تقرير")[:31])
            sheet.right_to_left()
            row = 0
            title = sheet_data.get("title")
            if title:
                sheet.write(row, 0, title, title_fmt)
                row += 1
            for meta in sheet_data.get("meta") or []:
                sheet.write(row, 0, meta, text_fmt)
                row += 1
            if title or sheet_data.get("meta"):
                row += 1
            headers = sheet_data.get("headers") or []
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_fmt)
                sheet.set_column(col, col, 18 if col else 36)
            row += 1
            for values in sheet_data.get("rows") or []:
                for col, value in enumerate(values):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        sheet.write_number(row, col, value, money_fmt)
                    else:
                        sheet.write(row, col, value if value is not None else "", text_fmt)
                row += 1
            for note in sheet_data.get("notes") or []:
                row += 1
                sheet.write(row, 0, note, text_fmt)
        workbook.close()
        safe_name = (filename or "homeblend_report.xlsx").replace("/", "-")
        if not safe_name.lower().endswith(".xlsx"):
            safe_name = "%s.xlsx" % safe_name
        attachment = self.env["ir.attachment"].create({
            "name": safe_name,
            "type": "binary",
            "datas": base64.b64encode(output.getvalue()),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
