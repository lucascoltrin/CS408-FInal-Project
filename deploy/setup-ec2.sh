#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu EC2 server. Run ON THE SERVER:
#   sudo bash deploy/setup-ec2.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: run with sudo: sudo bash deploy/setup-ec2.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="sfperformance"
APP_DIR="/opt/${APP_NAME}"
APP_USER="${SUDO_USER:-ubuntu}"

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip postgresql nginx rsync curl

echo "==> Creating ${APP_DIR}"
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Writing ${APP_DIR}/.env (first run only)"
if [ ! -f "${APP_DIR}/.env" ]; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  DBPASS="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
  cat > "${APP_DIR}/.env" <<ENVEOF
DJANGO_SECRET_KEY=${SECRET}
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=*
DB_NAME=${APP_NAME}
DB_USER=${APP_NAME}
DB_PASSWORD=${DBPASS}
DB_HOST=localhost
DB_PORT=5432
ENVEOF
  chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi
set -a; . "${APP_DIR}/.env"; set +a

echo "==> Creating PostgreSQL role and database"
systemctl enable --now postgresql
pg_admin() { (cd / && sudo -u postgres psql -v ON_ERROR_STOP=1 "$@"); }
if [ "$(pg_admin -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'")" != "1" ]; then
  pg_admin -qc "CREATE ROLE ${DB_USER} LOGIN CREATEDB PASSWORD '${DB_PASSWORD}'"
else
  pg_admin -qc "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}'"
fi
if [ "$(pg_admin -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")" != "1" ]; then
  pg_admin -qc "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}"
fi

echo "==> Installing systemd service (starts on boot)"
sed "s/__APP_USER__/${APP_USER}/g" "${SCRIPT_DIR}/${APP_NAME}.service" \
  > "/etc/systemd/system/${APP_NAME}.service"
systemctl daemon-reload
systemctl enable "${APP_NAME}"

echo "==> Configuring nginx (port 80 -> app on 127.0.0.1:8000)"
cp "${SCRIPT_DIR}/nginx-${APP_NAME}.conf" "/etc/nginx/sites-available/${APP_NAME}"
ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo
echo "Server is ready. Next, from your laptop run:"
echo "  ./deploy/deploy.sh -h <PUBLIC-IP> -i ~/keys/mykey.pem"
