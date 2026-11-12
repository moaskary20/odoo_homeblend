import base64
import io

import xlsxwriter

from odoo import models, _
from odoo.exceptions import UserError

HB_XLSX_LEGEND = (
    "أزرق=عنوان · كهرماني=إجمالي · أخضر/أحمر=نتيجة · "
    "أخضر مزرق=مدين/وارد · بنفسجي=دائن/صادر · أحمر=رقم سالب (−)"
)


class HomeblendXlsxExportMixin(models.AbstractModel):
    _name = "homeblend.xlsx.export.mixin"
    _description = "تصدير Excel مشترك"

    def _hb_xlsx_download(self, filename, sheets):
        """sheets: list of dicts {name, title?, meta?, headers, rows, notes?, legend?}

        rows: list of list values, أو dict:
          {"values": [...], "kind": "header"|"total"|"result"|"alert"|None}
        numbers تُكتب كأرقام مع تمييز مدين/دائن والسالب.
        """
        if not self:
            raise UserError(_("لا توجد بيانات للتصدير."))
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})

        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "align": "right"})
        col_header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "align": "right", "border": 1})
        debit_header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#D1F2EB", "font_color": "#0E6655", "align": "right", "border": 1,
        })
        credit_header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#E8DAEF", "font_color": "#6C3483", "align": "right", "border": 1,
        })
        text_fmt = workbook.add_format({"align": "right", "border": 1})
        header_row_fmt = workbook.add_format({"bold": True, "bg_color": "#D6EAF8", "align": "right", "border": 1})
        total_row_fmt = workbook.add_format({"bold": True, "bg_color": "#FCF3CF", "align": "right", "border": 1})
        result_ok_fmt = workbook.add_format({"bold": True, "bg_color": "#D5F5E3", "align": "right", "border": 1})
        result_bad_fmt = workbook.add_format({"bold": True, "bg_color": "#FADBD8", "align": "right", "border": 1})
        alert_row_fmt = workbook.add_format({"bold": True, "bg_color": "#FADBD8", "align": "right", "border": 1})
        money_base = {"num_format": "#,##0.00;[Red]-#,##0.00", "align": "left", "border": 1}
        money_fmt = workbook.add_format(dict(money_base))
        money_debit_fmt = workbook.add_format({**money_base, "bg_color": "#D1F2EB", "font_color": "#0E6655"})
        money_credit_fmt = workbook.add_format({**money_base, "bg_color": "#E8DAEF", "font_color": "#6C3483"})
        money_header_fmt = workbook.add_format({**money_base, "bold": True, "bg_color": "#D6EAF8"})
        money_total_fmt = workbook.add_format({**money_base, "bold": True, "bg_color": "#FCF3CF"})
        money_ok_fmt = workbook.add_format({**money_base, "bold": True, "bg_color": "#D5F5E3"})
        money_bad_fmt = workbook.add_format({**money_base, "bold": True, "bg_color": "#FADBD8", "font_color": "#C0392B"})
        money_neg_fmt = workbook.add_format({**money_base, "font_color": "#C0392B", "bold": True})
        money_debit_neg_fmt = workbook.add_format({
            **money_base, "bg_color": "#D1F2EB", "font_color": "#C0392B", "bold": True,
        })
        money_credit_neg_fmt = workbook.add_format({
            **money_base, "bg_color": "#E8DAEF", "font_color": "#C0392B", "bold": True,
        })

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
            if sheet_data.get("legend", True):
                sheet.write(row, 0, sheet_data.get("legend_text") or HB_XLSX_LEGEND, text_fmt)
                row += 1
            if title or sheet_data.get("meta") or sheet_data.get("legend", True):
                row += 1
            headers = sheet_data.get("headers") or []
            debit_cols = set()
            credit_cols = set()
            for col, header in enumerate(headers):
                header_s = header or ""
                if any(token in header_s for token in ("مدين", "وارد", "المخطط", "تكلفة")):
                    sheet.write(row, col, header, debit_header_fmt)
                    debit_cols.add(col)
                elif any(token in header_s for token in ("دائن", "صادر", "الانحراف", "إهلاك")):
                    sheet.write(row, col, header, credit_header_fmt)
                    credit_cols.add(col)
                else:
                    sheet.write(row, col, header, col_header_fmt)
                sheet.set_column(col, col, 18 if col else 36)
            row += 1

            for raw in sheet_data.get("rows") or []:
                if isinstance(raw, dict):
                    values = raw.get("values") or []
                    kind = raw.get("kind")
                else:
                    values = raw
                    kind = None

                if kind == "header":
                    line_fmt, amount_fmt = header_row_fmt, money_header_fmt
                elif kind == "total":
                    line_fmt, amount_fmt = total_row_fmt, money_total_fmt
                elif kind == "result":
                    # يُحدَّد لاحقاً حسب الإشارة إن وُجد رقم سالب في الصف
                    line_fmt, amount_fmt = result_ok_fmt, money_ok_fmt
                elif kind == "alert":
                    line_fmt, amount_fmt = alert_row_fmt, money_bad_fmt
                else:
                    line_fmt, amount_fmt = text_fmt, money_fmt

                if kind == "result":
                    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
                    if any(v < 0 for v in nums):
                        line_fmt, amount_fmt = result_bad_fmt, money_bad_fmt

                for col, value in enumerate(values):
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        neg = value < 0
                        if col in debit_cols and kind not in ("header", "total", "result", "alert"):
                            cell_fmt = money_debit_neg_fmt if neg else money_debit_fmt
                        elif col in credit_cols and kind not in ("header", "total", "result", "alert"):
                            cell_fmt = money_credit_neg_fmt if neg else money_credit_fmt
                        elif neg and kind not in ("header", "total", "result", "alert"):
                            cell_fmt = money_neg_fmt
                        else:
                            cell_fmt = amount_fmt
                        sheet.write_number(row, col, value, cell_fmt)
                    else:
                        sheet.write(row, col, value if value is not None else "", line_fmt)
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
