"""The code-audit report, readable by one account only.

Renders `docs/AUDIT.md` the same way `panel.views.help_page` renders
`docs/GUIDE.md` — the markdown file is the single source of truth, so editing
it changes the page on the next request.

Access is *not* the panel's usual `@login_required`. The report is a
step-by-step map of unfixed authorization holes in this deployment, so it is
restricted to the addresses in `AUDIT_REPORT_EMAILS` (default: the one address
that asked for it). Superusers deliberately get **no** break-glass here — the
point of the page is that it is narrower than staff.

Everyone else gets 404, not 403: a 403 would tell a logged-in salesperson that
a document about the system's weaknesses exists and is worth hunting for.

Neither file lives under `static/` or `media/`, which nginx serves to the
public. `docs/` is only ever read through a view, so the PDF cannot leak by
someone guessing a URL.
"""
import logging
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render

import markdown as _md

logger = logging.getLogger(__name__)

DEFAULT_READERS = ["admin@garagelions.com"]

MD_PATH = os.path.join(settings.BASE_DIR, "docs", "AUDIT.md")
PDF_PATH = os.path.join(settings.BASE_DIR, "docs", "garagelions-audit.pdf")


def _may_read(user):
    readers = [
        e.strip().lower()
        for e in getattr(settings, "AUDIT_REPORT_EMAILS", DEFAULT_READERS)
        if e and e.strip()
    ]
    email = (getattr(user, "email", "") or "").strip().lower()
    return bool(email) and email in readers


@login_required
def audit_report(request):
    if not _may_read(request.user):
        raise Http404

    try:
        with open(MD_PATH, encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        # Deliberately NOT a 404. The reader is authorised, so an unreadable
        # file is a server fault, and returning 404 here made it look identical
        # to "you may not read this" — which cost real debugging time once
        # already, when an editor recreated the file and dropped its www-data
        # group. Say what actually broke, and log it.
        logger.error("Audit report unreadable at %s: %s", MD_PATH, exc)
        return HttpResponse(
            "<h1>Audit report unavailable</h1>"
            f"<p>The server could not read <code>{MD_PATH}</code>.</p>"
            f"<p><code>{exc.__class__.__name__}: {exc}</code></p>"
            "<p>Usually this is file ownership: the gunicorn user "
            "(<code>www-data</code>) needs read access.</p>",
            status=500,
        )

    md = _md.Markdown(extensions=["extra", "tables", "fenced_code", "toc"])
    body_html = md.convert(source)

    return render(request, "report.html", {
        "body_html": body_html,
        "toc_html": md.toc,
        "has_pdf": os.path.exists(PDF_PATH),
    })


@login_required
def audit_report_pdf(request):
    """Serve the PDF through the same gate rather than from a public path."""
    if not _may_read(request.user):
        raise Http404
    if not os.path.exists(PDF_PATH):
        raise Http404("Audit PDF not found.")
    return FileResponse(
        open(PDF_PATH, "rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename="garagelions-audit.pdf",
    )
