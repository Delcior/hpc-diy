#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MONITORING_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
DASHBOARD_DIR=${DASHBOARD_DIR:-"$MONITORING_DIR/dasboards"}
GRAFANA_URL=${GRAFANA_URL:-http://localhost:3000}
GRAFANA_USER=${GRAFANA_USER:-admin}

if [[ -f "$MONITORING_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  source "$MONITORING_DIR/.env"
fi
GRAFANA_PASSWORD=${GRAFANA_PASSWORD:-${GRAFANA_ADMIN_PASSWORD:-}}

if [[ -z "$GRAFANA_PASSWORD" ]]; then
  printf 'Set GRAFANA_PASSWORD or GRAFANA_ADMIN_PASSWORD\n' >&2
  exit 1
fi

command -v curl >/dev/null || { printf 'curl is required\n' >&2; exit 1; }
command -v jq >/dev/null || { printf 'jq is required\n' >&2; exit 1; }

for dashboard in "$DASHBOARD_DIR"/*.json; do
  [[ -e "$dashboard" ]] || continue
  payload=$(jq -c '{dashboard: (. | .id = null), folderId: 0, overwrite: true}' "$dashboard")
  curl --fail-with-body --silent --show-error \
    --user "$GRAFANA_USER:$GRAFANA_PASSWORD" \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    "$GRAFANA_URL/api/dashboards/db"
  printf '\nDeployed %s\n' "$(basename "$dashboard")"
done
