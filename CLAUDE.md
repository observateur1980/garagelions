# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ This checkout *is* production

`/var/www/garagelions/` on the host that runs garagelions.com is the live deployment — there is no separate prod step. Saving a Python file changes prod after the next gunicorn restart; running `manage.py migrate` mutates the live `garagelions_db`. Treat every Edit/Write as a production change. Confirm with the user before destructive DB ops (column drops, mass UPDATE, data backfills); nullable additive columns are usually fine after approval.

Settings discovery: `garagelions/settings/__init__.py` loads `.env` first, then tries `local.py` and falls back to `production.py`. Any shell session that imports settings prints `Loaded production settings.` — that's how you know you're talking to the live DB.

## Common commands

```bash
# Always use the project venv interpreter
venv/bin/python manage.py <cmd>

# Migrations
venv/bin/python manage.py makemigrations <app>
venv/bin/python manage.py migrate            # mutates the live DB
venv/bin/python manage.py migrate --check    # no-op check

# Quick sanity check after edits (template tag errors, URL refs, etc.)
venv/bin/python manage.py check

# Reload after Python/template changes (NOPASSWD allows this)
sudo /bin/systemctl restart gunicorn_garagelions.service

# DB dump (creds in .env)
set -a; source .env; set +a
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" \
  | gzip > backups/garagelions_db_$(date +%Y-%m-%d_%H%M).sql.gz
```

Tests: `home/tests.py` and `panel/tests.py` are stubs only — there is no test suite to run.

### Operational notes
- Gunicorn unit is `gunicorn_garagelions.service`; it does **not** support `systemctl reload`, only `restart`.
- Nginx access/error logs require a password — ask the user to tail them.
- `parviz`'s NOPASSWD sudo is limited to `systemctl restart|reload|status gunicorn_*` and `systemctl reload nginx`. Anything else (cron edits, log reads, package installs) needs interactive sudo.
- `deploy_followup.sh` is a one-time installer for the follow-up reminder cron — not a general deploy script. The user typically deploys by `git pull` + restart.

## High-level architecture

Three Django apps own most of the code, plus one standalone:

| App | Owns |
|---|---|
| `account/` | `MyUser` (= `AUTH_USER_MODEL`), `Profile`, `ProjectManager`, `Role`. Three layers per person — credentials, personal info, business assignment. |
| `home/` | Public website + territory model (`State` → `Region` → `SalesPoint` → `ZipCoverage`), `LeadModel` and its satellites (`LeadStatus`, `LeadActivity`, `LeadFollowUp`, `LeadTodo`, `LeadAttachment`), `Estimate`+`EstimateLineItem`, `Gallery`, `Testimonial`, `VideoReview`, `PushSubscription`, notifications dispatcher, sitemaps. |
| `panel/` | Internal CRM at `/panel/...` — lead list/detail/edit/create, dashboards, estimates UI, customers, parts, invoices, transactions, taskboard, Google Calendar sync, mobile PWA shell at `/panel/m/`. Also owns `Customer`, `Project`, `Part`/`PartCategory`, `Unit`, `Estimate`(panel-side), `Invoice`, `Task`, `GoogleCalendarCredential`. |
| `taskboard/` | Standalone kanban-style task board at `/taskboard/`. |

`panel/views.py` is large (~2700 lines) — most CRM functionality is there, organized by `# ── Section ──` comment blocks (Leads, Estimates, Customers, Parts, Invoices, Google Calendar sync, Mobile/PWA). Skim those comments before searching.

### Critical conventions (won't be discovered from a single file read)

**Status & role codes are DB-managed, but referenced by *code* in Python.** `LeadModel.status` and `ProjectManager.role` are free CharFields — no `choices=` on the model — and valid values come from `LeadStatus` and `Role` admin tables. Labels are editable; **codes are a stable contract**. Hardcode the code (`"appointment_set"`, `"location_manager"`) when branching on status/role; never hardcode the label. `home/models.STATUS_CHOICES` is seed/reference only. `ModelForm`s exclude `status` from validation so admin-added codes aren't rejected.

**Lead visibility scoping lives in `panel/views._lead_queryset`** — single source of truth:
- superuser/staff → all leads
- `ProjectManager.role.sees_all_locations=True` (TerritoryManager) → all
- `allows_multiple_locations=True` (LocationManager) → leads where `sales_point_id IN ([primary] + extras)`
- Otherwise → `assigned_user=user`

The same scoping is duplicated in `ProjectManager.get_visible_sales_points()` for notifications; keep them in sync if either changes.

**`ManualLeadForm` disables `sales_point` widget for non-staff** (`widget.attrs['disabled']`). Disabled inputs don't submit, so `form.save()` writes `sales_point=None`, which can drop the lead out of a LocationManager's queryset and 404 the post-save redirect. `lead_edit` falls back to `lead_list` when this happens — preserve that pattern when adding edit flows.

**Google Calendar source tagging.** Leads sourced from a calendar event carry `source_page = "google_calendar:<event_id>"`. `lead_create` (a) preserves that prefix when source_page is otherwise blank, (b) redirects to `lead_list` (not detail) so the event drops off the sync page (`panel/views.py:2407-2414`). Use `panel.google_calendar.event_source_tag(event_id)` to build the value.

**Settings module structure.** `garagelions/settings/__init__.py` is the entry point. It always loads `base.py`, then prefers `local.py` (gitignored, dev-only) over `production.py`. Don't add settings to `__init__.py`.

**Two SalesPoint↔user fields, easy to confuse.** `ProjectManager.sales_point` (+ `extra_sales_points`) is "where this employee works"; `SalesPoint.assigned_user` is "who is the routing contact for this SP". They are independent and don't sync — neither updates the other.

## Authoritative references already in the repo

- **`docs/GUIDE.md`** — the operator guide. Detailed sections on architecture, territory, leads lifecycle, notifications, estimates, calendar sync, PWA, gotchas. Read this before redesigning any cross-cutting feature.
- **`/var/www/garagelions/django_errors.log`** — Django's error stream (production). First place to look after a 500.
- **`/var/www/garagelions/logs/followups.log`** — cron log for `send_followup_reminders` (runs every minute via crontab).
- **`backups/`** — gzipped `pg_dump` snapshots. **Never `git add` this directory** — dumps contain customer PII and live Google Calendar OAuth tokens. Don't `git add -A` or `git add .` from the repo root; stage paths explicitly.

## Stack

Django 4.2.16 on Python 3.12, PostgreSQL 16 (`garagelions_db`, owner `parviz`), gunicorn at `unix:/run/gunicorn/garagelions.sock` behind nginx + Cloudflare. Email via SendGrid; SMS via Twilio; web push via VAPID/pywebpush; Google Calendar via `google-auth-oauthlib` + `google-api-python-client`. `TIME_ZONE = "America/Los_Angeles"`. No frontend build step — templates use vanilla Django + Bootstrap classes, no JS framework.
