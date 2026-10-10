#!/usr/bin/env bash
# Deploy the latest code to the EC2 server. Run from your LAPTOP:
#   ./deploy/deploy.sh -h <PUBLIC-IP> -i ~/keys/mykey.pem [-u ubuntu]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

APP_NAME="sfperformance"
APP_DIR="/opt/${APP_NAME}"
HOST=""; KEY=""; REMOTE_USER="ubuntu"

usage() { echo "Usage: $0 -h <PUBLIC-IP> -i <path/to/key.pem> [-u <user>]" >&2; exit 1; }
while getopts "h:i:u:" opt; do
  case "$opt" in
    h) HOST="$OPTARG" ;;
    i) KEY="$OPTARG" ;;
    u) REMOTE_USER="$OPTARG" ;;
    *) usage ;;
  esac
done
[ -n "$HOST" ] && [ -n "$KEY" ] || usage
[ -f "$KEY" ] || { echo "ERROR: key file not found: $KEY" >&2; exit 1; }

SSH_OPTS="-i ${KEY} -o StrictHostKeyChecking=accept-new"

echo "==> Running tests locally"
[ -x ./venv/bin/python ] || { echo "ERROR: no venv found. Run ./start.sh once first." >&2; exit 1; }
./venv/bin/python manage.py test

echo "==> Copying code to ${REMOTE_USER}@${HOST}:${APP_DIR}"
rsync -az --delete \
  --exclude '.git' --exclude 'venv' --exclude '.env' --exclude '*.pem' \
  --exclude '__pycache__' --exclude '*.pyc' \
  -e "ssh ${SSH_OPTS}" ./ "${REMOTE_USER}@${HOST}:${APP_DIR}/"

echo "==> Installing dependencies, migrating, restarting service"
ssh ${SSH_OPTS} "${REMOTE_USER}@${HOST}" bash -s <<REMOTE
set -euo pipefail
cd ${APP_DIR}
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --quiet -r requirements.txt
./venv/bin/python manage.py migrate --noinput
sudo systemctl restart ${APP_NAME}
REMOTE

echo "==> Checking http://${HOST}/api/health"
for i in $(seq 1 10); do
  if curl -fsS -o /dev/null "http://${HOST}/api/health"; then
    echo "Deploy OK: http://${HOST}/"
    exit 0
  fi
  sleep 2
done
echo "ERROR: health check failed after deploy." >&2
echo "Debug with: ssh ${SSH_OPTS} ${REMOTE_USER}@${HOST} 'sudo journalctl -u ${APP_NAME} -n 50'" >&2
exit 1
