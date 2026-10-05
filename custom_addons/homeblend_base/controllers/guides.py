from pathlib import Path

from odoo import http
from odoo.http import request

GUIDES = {
    "homeblend": {
        "file": "شرح_مستأجري_Home_Blend.html",
        "title": "دليل مستأجري Home Blend",
    },
    "artcasa": {
        "file": "شرح_تشغيل_Art_Casa.html",
        "title": "دليل تشغيل Art Casa",
    },
}


class OperatingGuides(http.Controller):
    def _docs_dir(self):
        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "docs",
            Path("/opt/odoo_homeblend/docs"),
        ]
        for path in candidates:
            if path.is_dir():
                return path
        return candidates[0]

    @http.route(["/guides", "/guides/"], type="http", auth="public", csrf=False)
    def guides_index(self, **_kwargs):
        items = "".join(
            f'<li><a href="/guides/{slug}">{meta["title"]}</a></li>'
            for slug, meta in GUIDES.items()
        )
        html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>صفحات الشرح</title>
  <style>
    body {{
      font-family: sans-serif;
      background: #f6f0e6;
      color: #1c1612;
      max-width: 40rem;
      margin: 3rem auto;
      padding: 0 1.25rem;
      line-height: 1.7;
    }}
    a {{ color: #b85c38; }}
  </style>
</head>
<body>
  <h1>صفحات الشرح</h1>
  <ul>{items}</ul>
</body>
</html>
"""
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        ["/guides/<string:slug>", "/guides/<string:slug>.html"],
        type="http",
        auth="public",
        csrf=False,
    )
    def guide_page(self, slug, **_kwargs):
        meta = GUIDES.get(slug)
        if not meta:
            return request.not_found()
        path = self._docs_dir() / meta["file"]
        if not path.is_file():
            return request.not_found()
        return request.make_response(
            path.read_bytes(),
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "public, max-age=300"),
            ],
        )
