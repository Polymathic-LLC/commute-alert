#!/usr/bin/env bash
# Sync recorder code (not data, not the local dev venv) to the S1 container
# and (re)install the systemd unit. Safe to re-run — idempotent.
#
# Usage: ./deploy/deploy.sh
# Requires: SSH access to `commute-alert-s1` (see ~/.ssh/config).

set -euo pipefail
cd "$(dirname "$0")/.."   # prototypes/s1-transit-capture/

HOST=commute-alert-s1
REMOTE_DIR=/opt/commute-alert/s1-transit-capture

echo "==> Syncing code to ${HOST}:${REMOTE_DIR}"
rsync -az --delete \
  --exclude '.venv-local' \
  --exclude '.venv' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude '.git' \
  recorder.py requirements.txt deploy \
  "${HOST}:${REMOTE_DIR}/"

if [ -f .secrets/mbta.env ]; then
  echo "==> Syncing MBTA API key"
  ssh "${HOST}" "mkdir -p ${REMOTE_DIR}/.secrets && chmod 700 ${REMOTE_DIR}/.secrets"
  rsync -az .secrets/mbta.env "${HOST}:${REMOTE_DIR}/.secrets/mbta.env"
  ssh "${HOST}" "chmod 600 ${REMOTE_DIR}/.secrets/mbta.env"
else
  echo "==> No .secrets/mbta.env found locally — deploying without a key (SSE will 406 until one is added)."
fi

echo "==> Ensuring venv + deps on remote"
ssh "${HOST}" "
  set -e
  cd ${REMOTE_DIR}
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
  mkdir -p /var/lib/commute-alert-s1/data /var/log/commute-alert-s1
"

echo "==> Installing systemd unit"
ssh "${HOST}" "
  cp ${REMOTE_DIR}/deploy/commute-alert-s1.service /etc/systemd/system/commute-alert-s1.service
  systemctl daemon-reload
  systemctl enable commute-alert-s1
"

echo "==> Restarting service"
ssh "${HOST}" "systemctl restart commute-alert-s1 && sleep 2 && systemctl status commute-alert-s1 --no-pager -l | head -20"

echo "==> Done. Tail logs with: ssh ${HOST} 'tail -f /var/log/commute-alert-s1/recorder.log'"
