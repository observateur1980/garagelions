#!/usr/bin/env bash
#
# Deploy the follow-up reminder feature on the production server.
#
# Run this script ONCE on the prod server (or anytime you want to re-sync —
# every step is idempotent). It will:
#   1) Pull latest code
#   2) Install/upgrade Python deps if requirements.txt changed
#   3) Apply Django migrations
#   4) Collect static files (no-op if nothing new)
#   5) Restart the app server
#   6) Install the cron job for send_followup_reminders (every minute)
#
# Before first run, edit the CONFIG section below to match your server.

set -euo pipefail

# ─── CONFIG — edit these to match your production server ────────────────────

# Absolute path to the project root on the server (the dir that contains manage.py)
PROJECT_DIR="/var/www/garagelions"

# Path to the Python interpreter inside your virtualenv on the server
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"

# Django settings module used in production
DJANGO_SETTINGS_MODULE="garagelions.settings.production"

# Command that restarts your app server — pick ONE matching your stack:
#   systemd:     "sudo systemctl restart gunicorn"
#   supervisor:  "sudo supervisorctl restart garagelions"
#   uwsgi touch: "touch ${PROJECT_DIR}/uwsgi.reload"
#   passenger:   "touch ${PROJECT_DIR}/tmp/restart.txt"
#   docker:      "docker compose -f /path/to/docker-compose.yml restart web"
RESTART_CMD="sudo systemctl restart gunicorn"

# Where cron should write its log
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/followups.log"

# Git branch to deploy (usually main)
GIT_BRANCH="main"

# ─── END CONFIG ─────────────────────────────────────────────────────────────


say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
ok()  { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
die() { printf "\n\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ─── Sanity checks ──────────────────────────────────────────────────────────
say "Checking prerequisites"

[ -d "$PROJECT_DIR" ]      || die "PROJECT_DIR does not exist: $PROJECT_DIR"
[ -f "$PROJECT_DIR/manage.py" ] || die "manage.py not found in $PROJECT_DIR"
[ -x "$VENV_PYTHON" ]      || die "Python not executable: $VENV_PYTHON"
command -v crontab >/dev/null 2>&1 || die "crontab command not found"
ok "Project: $PROJECT_DIR"
ok "Python:  $VENV_PYTHON"

cd "$PROJECT_DIR"

# ─── 1. Pull latest code ────────────────────────────────────────────────────
say "Pulling latest code from git"
git fetch --quiet origin
git checkout "$GIT_BRANCH" --quiet
git pull --ff-only origin "$GIT_BRANCH"
ok "On $(git rev-parse --short HEAD)"

# ─── 2. Update Python deps (only if requirements.txt changed in last pull) ──
if git diff --name-only HEAD@{1} HEAD 2>/dev/null | grep -qx "requirements.txt"; then
    say "requirements.txt changed — installing"
    "$VENV_PYTHON" -m pip install -r requirements.txt
    ok "Dependencies up to date"
else
    ok "requirements.txt unchanged — skipping pip install"
fi

# ─── 3. Migrations ──────────────────────────────────────────────────────────
say "Applying Django migrations"
DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" \
    "$VENV_PYTHON" manage.py migrate --noinput
ok "Migrations applied"

# ─── 4. Collect static ──────────────────────────────────────────────────────
say "Collecting static files"
DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" \
    "$VENV_PYTHON" manage.py collectstatic --noinput >/dev/null
ok "Static files collected"

# ─── 5. Restart app server ──────────────────────────────────────────────────
say "Restarting app server"
echo "  Running: $RESTART_CMD"
eval "$RESTART_CMD"
ok "App server restarted"

# ─── 6. Smoke-test the management command ───────────────────────────────────
say "Smoke-testing send_followup_reminders"
DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" \
    "$VENV_PYTHON" manage.py send_followup_reminders --dry-run
ok "Command runs cleanly"

# ─── 7. Install cron job ────────────────────────────────────────────────────
say "Installing cron job (every minute)"

mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

CRON_TAG="# garagelions-followup-reminders"
CRON_LINE="* * * * * cd ${PROJECT_DIR} && DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE} ${VENV_PYTHON} ${PROJECT_DIR}/manage.py send_followup_reminders >> ${LOG_FILE} 2>&1 ${CRON_TAG}"

# Take current crontab (empty if none), strip any previous version of OUR line
# (matched by the tag), then append the fresh line.
EXISTING="$(crontab -l 2>/dev/null || true)"
NEW_CRON="$(printf '%s\n' "$EXISTING" | grep -v -F "$CRON_TAG" || true)"
{
    [ -n "$NEW_CRON" ] && printf '%s\n' "$NEW_CRON"
    printf '%s\n' "$CRON_LINE"
} | crontab -

ok "Cron installed. Current crontab:"
crontab -l | sed 's/^/    /'

# ─── Done ───────────────────────────────────────────────────────────────────
say "Deploy complete"
cat <<EOF

Next steps:
  • Watch the cron log:    tail -f ${LOG_FILE}
  • Test in the panel:     set a lead to "Follow Up", click the calendar
                           icon, schedule a reminder 2 minutes from now,
                           and watch the log.
  • Remove cron later:     crontab -e   (delete the line tagged
                           "${CRON_TAG}")

EOF
