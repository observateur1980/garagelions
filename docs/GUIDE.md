# Garage Lions — Operator Guide

A practical guide to how this system is set up, what each piece does,
and how to use it day-to-day. Read top-to-bottom the first time; after
that use the table of contents to jump in.

## Contents

1. [System architecture at a glance](#1-system-architecture-at-a-glance)
2. [Users, profiles, and roles](#2-users-profiles-and-roles)
3. [Territory: State → Region → SalesPoint → ZipCoverage](#3-territory-state--region--salespoint--zipcoverage)
4. [Leads: lifecycle, routing, and ownership](#4-leads-lifecycle-routing-and-ownership)
5. [Notifications](#5-notifications)
6. [Estimates and parts](#6-estimates-and-parts)
7. [Calendar sync](#7-calendar-sync)
8. [The mobile / PWA panel](#8-the-mobile--pwa-panel)
9. [First-time setup checklist](#9-first-time-setup-checklist)
10. [Common admin tasks](#10-common-admin-tasks)
11. [Gotchas worth knowing](#11-gotchas-worth-knowing)

---

## 1. System architecture at a glance

There are three parallel domains that meet at the **Lead**:

```
ACCOUNT             TERRITORY                    BUSINESS
────────            ─────────                    ────────
MyUser              State                        Lead
 └ Profile          └ Region                     ├ LeadStatus
   └ ProjectManager   └ SalesPoint               ├ LeadActivity
       └ Role            └ ZipCoverage           ├ LeadFollowUp
                                                 ├ LeadTodo
                                                 └ Estimate
                                                    └ EstimateLineItem
                                                       └ Part / PartCategory
```

Two Django apps own most of this:

| App | Owns |
|---|---|
| `account/` | `MyUser`, `Profile`, `ProjectManager`, `Role` |
| `home/` | `SalesPoint`, `State`, `Region`, `ZipCoverage`, `ServiceCity`, `ZipCode`, `Lead*`, `Estimate*`, `Gallery`, `Testimonial`, `VideoReview`, `FranchiseAgreement`, `PushSubscription` |
| `panel/` | The user-facing CRM UI (everything under `/panel/...`) |

The **public website** (`home/`) collects leads. The **admin** (`/admin/`)
is for configuration. The **panel** (`/panel/`) is where staff actually
work leads and write estimates.

---

## 2. Users, profiles, and roles

### Three layers per person

| Model | Path | Holds |
|---|---|---|
| `MyUser` | `account/models.py:51` | Login credentials only (username, email, password, staff flags). |
| `Profile` | `account/models.py:128` | Personal info: full name, photo, phone, mobile, city, state, timezone, links, notification preferences. |
| `ProjectManager` | `account/models.py:295` | Business info: role, sales-point assignment, manager hierarchy, employment type, compensation, dates. |

A user can have a Profile without being a ProjectManager (e.g. a customer-facing
support account). Anyone working leads has all three.

### Roles are admin-managed

`/admin/account/role/` is the source of truth for roles. Each row has:

- **`code`** — stable identifier referenced from code (`project_manager`, `location_manager`, …). Locked on protected rows.
- **`label`** — display name shown everywhere (e.g. `Multiple Locations Manager`).
- **`allows_multiple_locations`** — when `True`, this role may have entries in `extra_sales_points`.
- **`sees_all_locations`** — when `True`, the user sees leads from **every** active SalesPoint regardless of assignment.
- **`is_protected`** — locks code edits and deletion. Set on the three seeded rows.

Three rows are seeded by migration `0012_seed_default_roles` and protected:

| code | label | multi-loc | sees-all |
|---|---|---|---|
| `project_manager` | Project Manager | no | no |
| `location_manager` | Multiple Locations Manager | yes | no |
| `territory_manager` | Territory Manager | yes | yes |

You can create new roles freely. New roles affect **lead visibility** via
their flags (driven by `ProjectManager.get_visible_sales_points()` in
`account/models.py:465`). Some legacy permission checks in panel views and
notification code still compare against the three protected codes — see
[Gotchas](#11-gotchas-worth-knowing).

### Two assignment fields, two different things

This trips people up. There are two ways a user can be tied to a SalesPoint:

| Field | Lives on | Means |
|---|---|---|
| `ProjectManager.sales_point` (+ `extra_sales_points`) | the user side | Where this employee works (home base + extras). |
| `SalesPoint.assigned_user` | the SP side | Who is the contact / lead-routing owner for this SP. |

These are independent — neither updates the other. The PM admin change
page now shows a **Managed locations** summary that unions both with
provenance tags (`primary`, `extra`, `assigned_user`) so you can see why
each SP is connected.

---

## 3. Territory: State → Region → SalesPoint → ZipCoverage

A four-level hierarchy in `home/models.py`:

1. **State** (`152`) — USPS two-letter code (`CA`, `TX`).
2. **Region** (`169`) — short code unique within a state (`NOR`, `SOU`, `CEN`). The full code displayed everywhere is `<STATE>-<REGION>` (e.g. `CA-NOR`).
3. **SalesPoint** (`195`) — the operational unit. Has a `region` FK, a short `code` unique within its region, and an `internal_code` of `<STATE>-<REGION>-<SP>` (e.g. `CA-NOR-SCL`).
4. **ZipCoverage** (`432`) — the routing record. Says "ZIP X is owned by SalesPoint Y, with backup Z".

`ServiceCity` + `ZipCode` (older marketing schema) live alongside
ZipCoverage. They drive the public-facing service-area pages but are not
the authority for lead routing — use `ZipCoverage` for that.

### Coverage tiers

`ZipCoverage.coverage_type` (`441`):

| value | meaning |
|---|---|
| `core` | Primary service area. |
| `extended` | Will service, longer drive. |
| `edge` | Edge-case ZIPs we'll consider. |
| `future` | Planned but not yet servicing. |

### Looking up a ZIP

```python
ZipCoverage.route("94089")
```

Returns the active routing record with `sales_point` and `backup_sales_point`
preloaded, or `None` (`home/models.py:485`).

### The SalesPoint admin page

`/admin/home/salespoint/` is the changelist. Columns include:
state, region, location type, base city, **# ZIPs** (primary), **# Backup**,
**# Cities**, assigned user, and a **Manage Territory** button.

The **Manage Territory** view (`home/admin.py:584`) is a per-SP page where
you can assign/unassign `ServiceCity` rows or paste a textarea like:

```
Santa Clara, CA: 94089 95054 95110
San Jose, CA: 95123 95124
```

…to bulk-create cities + ZIPs. (This is for the older
ServiceCity/ZipCode system. Use the ZipCoverage admin for the new
operational routing.)

---

## 4. Leads: lifecycle, routing, and ownership

### The Lead model

`LeadModel` (`home/models.py:809`) is the single source of truth. Key fields:

- `first_name`, `last_name`, `email`, `phone`, `address`, `zip_code`
- `sales_point` (FK), `service_city` (FK)
- `assigned_user` (FK to `MyUser`)
- `consultation_types` (multi-select) — what services they're asking about
- `message`, `internal_notes`
- `source_page` — where the lead came from (e.g. `google_calendar:<event_id>`)
- `status` — free-form code governed by the `LeadStatus` table

### Statuses are admin-managed

`/admin/home/leadstatus/` controls the dropdown options. Each row has
`code`, `label`, `order`, `color`, `is_protected`, `is_quick_filter`.
The `LeadModel.status` field is a free CharField — there are NO
hardcoded `choices=` on it (`home/models.py:876` for the why). This is
the same pattern used by `Role` in the account app.

### How a new lead gets created

| Source | Entry point | What it sets |
|---|---|---|
| **Public website form** | `home/views.py` (form posts) | `sales_point` looked up via service-city/ZIP, status `new`. |
| **Manual entry** | `/panel/leads/new/` | Filled by staff. Salespeople have their fields locked to their location; staff can pick anywhere (`home/forms.py:240`). |
| **Google Calendar** | `/panel/calendar/sync/` | Parses event guests and description for name/phone/zip/email; prefills the manual form with `source_page="google_calendar:<event_id>"` (`panel/views.py:2629`). |

### Working a lead in the panel

`/panel/leads/` is the list. `/panel/leads/<id>/` is the detail page.
From the detail page you can:

- Change status (logged as a `LeadActivity`)
- Update internal notes
- Add a follow-up reminder (`LeadFollowUp`) — when the time arrives, push + email + SMS fires to the assigned user
- Add to-dos (`LeadTodo`)
- Upload attachments (`LeadAttachment`)
- View the full activity history
- "Convert to estimate" → creates a `Customer` + new `Estimate` and flips the lead to `quoted`

### Lead visibility per role

`ProjectManager.get_visible_sales_points()` decides which leads each
person sees:

| Role flags | Sees leads from |
|---|---|
| `sees_all_locations=True` | Every active SalesPoint. |
| `allows_multiple_locations=True` | Their primary `sales_point` + everything in `extra_sales_points`. |
| Both False (default Project Manager) | Their primary `sales_point` only. |

Staff/superusers always see everything regardless of role.

---

## 5. Notifications

Three channels, each independent and toggleable:

| Channel | Trigger | Backed by |
|---|---|---|
| **Email** | New lead, reassignment, follow-up due | Gmail SMTP via `home/notifications.py` |
| **SMS** | Same | Twilio (only if `.env` has Twilio credentials) |
| **Web Push** | Same | VAPID push to PWA-installed devices (`PushSubscription` model) |

Each `Profile` has `notify_new_lead_email` / `notify_new_lead_sms`
opt-in flags. `home/signals.py` wires up post-save hooks that call the
notification dispatcher. Reassignment is detected by a pre-save snapshot
of the previous `assigned_user`.

The full audit trail lives in **`LeadActivity`** rows: `created`,
`status_changed`, `notes_updated`, `assigned`, `reminder_sent`. Visible
on the lead detail page and as a standalone admin model.

For background context on env-var setup, see the
`Lead Notification System` and `PWA Web Push` notes in
`.claude/.../memory/`.

---

## 6. Estimates and parts

`Estimate` (`home/models.py:1257`) is created either:

- Standalone from `/panel/estimates/new/` after picking a customer, or
- From a lead via `/panel/lead/<lead_pk>/to-estimate/` (auto-creates a
  Customer, auto-titles from consultation types, flips lead to `quoted`).

Estimates have **components** (sections) and **line items**. Build them
on the estimate edit page using the part search.

### Parts model

- **`PartCategory`** — required. Every Part **must** belong to a category. The system enforces this; never allow creating a Part without one.
- **`Part`** — the actual catalog item (name, description, default price).
- **Global vs local parts** — admin manages global parts; each location can add local parts that show up only for that SalesPoint.
- **Templates** — bundles of parts that can be reused across estimates. **Templates are created on `/panel/parts/`** (the parts page), not on the estimate page. The estimate edit page only **applies** existing templates via "Add Template".

### Sending an estimate

`/panel/estimates/<pk>/send/` (AJAX) generates a PDF and emails it to the customer.

---

## 7. Calendar sync

There's a one-way pull from Google Calendar:

1. Operator visits `/panel/calendar/oauth/connect/` and logs in via Google OAuth.
2. Credentials are stored in `GoogleCalendarCredential` (panel-level model).
3. `/panel/calendar/sync/` lists upcoming events from a calendar named **"Leads"** (or the primary calendar if no "Leads" calendar exists).
4. For each event, the system extracts attendee name/email + parses ZIP + phone from the description.
5. Each event surfaces a "Create Lead" link that prefills `/panel/leads/new/` with the parsed fields.
6. Once converted, `Lead.source_page` records `google_calendar:<event_id>` and the event is hidden from future sync pages.

The integration is **read-only** — the system never writes back to Google Calendar.

---

## 8. The mobile / PWA panel

`/panel/m/leads/` is a mobile-first stripped-down view of the lead list
and detail pages, intended for field reps. Uses the same auth/scoping as
desktop. Web Push subscriptions registered from this PWA fire when leads
are created/reassigned (with a sound, on supported devices).

---

## 9. First-time setup checklist

Order matters — territory before sales points before users.

1. **States** — add the states you operate in (`/admin/home/state/`).
2. **Regions** — add 1+ region per state.
3. **Sales points** — create one row per location. Set `region`, short `code`, `base_city`, location type, optional address/phone/email.
4. **Working hours** — these auto-create with default Mon-Fri open / Sat-Sun closed when a SalesPoint is saved (signal in `home/models.py:347`). Tweak per-day on the SP change page.
5. **ZipCoverage** — add the ZIPs each SP services. Set `coverage_type`, primary + optional backup SalesPoint.
6. **Lead statuses** — `/admin/home/leadstatus/` is seeded with the 8 default codes. Add custom ones if your team uses different terms.
7. **Roles** — three default roles are seeded. Add new ones only if your business has roles that are genuinely different from the three.
8. **Users** — create each staff user (`/admin/account/myuser/`). On the user change page:
   - Fill in **Profile** (name, phone, photo).
   - Fill in **Business Role** (role dropdown, primary `sales_point`, optionally `extra_sales_points`, manager hierarchy, employment fields).
9. **Set `assigned_user` on each SalesPoint** — point each SP to the user who is its lead-routing contact. (This is independent from the user's role assignment — see [Gotchas](#11-gotchas-worth-knowing).)
10. **Notifications `.env`** — set Gmail SMTP, optional Twilio, VAPID keys. See `memory/project_notification_system.md` and `memory/project_pwa_push.md`.
11. **Galleries / Testimonials / VideoReviews** — for the public website, populate as needed.

---

## 10. Common admin tasks

### Add a new sales point

1. `/admin/home/salespoint/` → **Add sales point**.
2. Fill in name, slug, location type, region, code, base_city.
3. Optionally fill SEO + address + Lead Routing emails (`lead_notification_email`, `from_email`, `reply_to_email`).
4. Set `assigned_user` (the lead-routing contact).
5. Save. Working hours auto-generate. Add ZipCoverage rows separately for the ZIPs this SP services.

### Add a new ZIP

`/admin/home/zipcoverage/` → **Add ZIP coverage**. Pick state, region, primary SP, optional backup, coverage tier. The lookup `ZipCoverage.route("XXXXX")` will find it.

### Promote a user to manage multiple locations

1. `/admin/account/projectmanager/<id>/change/` (or via the User change page).
2. Change the **role** dropdown to `Multiple Locations Manager` (or `Territory Manager` for company-wide).
3. Add SalesPoints to **extra_sales_points**.
4. Save. The "Managed locations" summary box updates.

### Create a custom role

1. `/admin/account/role/` → **Add role**.
2. Pick a `code` (lower_snake_case), a `label`, and the two flags.
3. Save. The role appears in the role dropdown on PM forms.
4. Assign users to it as needed.

(Note: capability flags on custom roles only affect lead visibility.
Other in-app permission checks may still gate on the three protected
role codes. See Gotchas.)

### Disable a SalesPoint without deleting

Set `is_active = False` on its admin page. Inactive SPs are hidden from
the public site and from territory-manager visibility. Existing leads
still reference it.

### Roll back a misassigned lead

The `LeadActivity` log shows every change. Re-set the fields (status,
assigned_user, sales_point) on the lead detail page; the rollback itself
is also logged.

---

## 11. Gotchas worth knowing

- **`SalesPoint.assigned_user` ≠ `ProjectManager.sales_point`.** They model two different things and don't sync. The PM admin change page surfaces both with provenance tags so you can spot mismatches.
- **`SalesPoint.clean()` blocks single-location users from being assigned to a second SP** (`home/models.py:285`). If you hit this validation error, either pick someone else or promote the user.
- **Statuses and roles are admin-managed, but their *codes* are sometimes referenced from code.** Don't rename codes on protected rows — labels are safe to change.
- **Custom roles get correct lead-visibility but may not inherit other privileges.** Some checks in `panel/views.py`, `home/notifications.py`, and `panel/context_processors.py` still compare to the three protected role codes. If you create, say, a "Regional Lead" role, double-check the specific privilege you expected to inherit.
- **`ServiceCity`/`ZipCode` is the older marketing schema; `ZipCoverage` is the new operational one.** They coexist. The Manage Territory button on a SalesPoint manages cities/ZIPs (the legacy pair). Use `/admin/home/zipcoverage/` for routing data.
- **A `Lead.status` value not present in `LeadStatus` is preserved on save** (the form falls back to including the current code as a `<select>` option). This prevents accidental rewrites if you delete a status row that's still in use.
- **Calendar sync is read-only.** It will never write to Google. Events stay there even after you create a lead from them; the lead's `source_page` is what hides the event from the sync page.
- **Working hours auto-create on first save of a SalesPoint.** If you delete them, they don't come back automatically.
- **Web Push needs HTTPS in production.** Local dev works on `127.0.0.1` because browsers exempt loopback.

---

*Last updated: 2026-05-10. When the system changes meaningfully (new model,
new role behavior, new panel page), update the relevant section here so
this stays the source of truth.*
