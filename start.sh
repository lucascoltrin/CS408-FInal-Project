#!/usr/bin/env bash
# start.sh - install everything and start SF Performance. Works on Linux (Ubuntu) and macOS (Homebrew).
# Safe to run repeatedly. Optional overrides: APP_HOST (default 127.0.0.1), APP_PORT (default 8000).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
OS="$(uname -s)"

fail() { echo "ERROR: $1" >&2; exit 1; }

if [ "$OS" = "Darwin" ]; then
  PY_HINT="brew install python"
  PG_HINT="brew install postgresql@16 && brew services start postgresql@16"
  START_HINT="brew services start postgresql@16"
  # Homebrew PostgreSQL is keg-only, so psql may not be on PATH yet.
  if ! command -v psql >/dev/null 2>&1 && command -v brew >/dev/null 2>&1; then
    for d in "$(brew --prefix)"/opt/postgresql*/bin; do
      if [ -x "$d/psql" ]; then PATH="$d:$PATH"; break; fi
    done
  fi
else
  PY_HINT="sudo apt install python3 python3-venv"
  PG_HINT="sudo apt install postgresql"
  START_HINT="sudo systemctl start postgresql"
fi

# ---- 1. Check required tools -------------------------------------------------
echo "==> Checking required tools"
command -v python3 >/dev/null 2>&1 \
  || fail "python3 is not installed. (${PY_HINT})"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "Python 3.10 or newer is required (found $(python3 --version 2>&1)). (${PY_HINT})"
python3 -c 'import venv, ensurepip' >/dev/null 2>&1 \
  || fail "python3-venv is missing. (${PY_HINT})"
command -v psql >/dev/null 2>&1 \
  || fail "PostgreSQL is not installed. (${PG_HINT})"
if [ "$OS" != "Darwin" ]; then
  command -v sudo >/dev/null 2>&1 \
    || fail "sudo is required to create the database user."
fi
pg_isready -q \
  || fail "PostgreSQL is not running. (${START_HINT})"

# ---- 2. Create .env on first run ---------------------------------------------
if [ ! -f .env ]; then
  echo "==> Creating .env with generated secrets"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  DBPASS="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  cat > .env <<ENVEOF
DJANGO_SECRET_KEY=${SECRET}
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=sfperformance
DB_USER=sfperformance
DB_PASSWORD=${DBPASS}
DB_HOST=localhost
DB_PORT=5432
ENVEOF
  chmod 600 .env
fi
set -a; . ./.env; set +a

# ---- 3. Create the database role and database (idempotent) -------------------
echo "==> Setting up PostgreSQL database"
if [ "$OS" = "Darwin" ]; then
  # Homebrew PostgreSQL: your macOS user is the database superuser.
  pg_admin() { psql -d postgres -v ON_ERROR_STOP=1 "$@"; }
  pg_admin -tAc "SELECT 1" >/dev/null 2>&1 \
    || fail "Could not connect to PostgreSQL as your user. (${START_HINT})"
else
  pg_admin() { (cd / && sudo -u postgres psql -v ON_ERROR_STOP=1 "$@"); }
fi

if [ "$(pg_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'")" != "1" ]; then
  pg_admin -qc "CREATE ROLE ${DB_USER} LOGIN CREATEDB PASSWORD '${DB_PASSWORD}'"
else
  pg_admin -qc "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}'"
fi
if [ "$(pg_admin -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")" != "1" ]; then
  pg_admin -qc "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}"
fi

# ---- 4. Install dependencies and migrate -------------------------------------
echo "==> Installing Python dependencies"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet -r requirements.txt

echo "==> Running database migrations"
./venv/bin/python manage.py migrate --noinput

# ---- 5. Start the app --------------------------------------------------------
echo "==> Starting SF Performance at http://${APP_HOST}:${APP_PORT}/  (Ctrl+C to stop)"
exec ./venv/bin/gunicorn --bind "${APP_HOST}:${APP_PORT}" sfperformance.wsgi:application
