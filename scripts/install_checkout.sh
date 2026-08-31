#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ALLOW_NETWORK_INSTALL=1 ./scripts/install_checkout.sh

Initializes the current checkout for local serving on a machine that already has
system dependencies installed. Safe to re-run.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_HELPER="${ROOT_DIR}/scripts/envfile.py"
SYNC_DEPLOY_ENV="${ROOT_DIR}/scripts/sync_deploy_env.sh"
source "${ROOT_DIR}/scripts/require_explicit_approval.sh"
cd "${ROOT_DIR}"

require_any_explicit_approval \
  "create or update a virtualenv, install Python packages, and write local runtime files" \
  ALLOW_NETWORK_INSTALL ALLOW_DEPLOY_ACTIONS

if [[ ! -f "${ROOT_DIR}/.env.example" ]]; then
  echo "Missing .env.example in ${ROOT_DIR}" >&2
  exit 1
fi

if [[ ! -f "${ENV_HELPER}" ]]; then
  echo "Missing ${ENV_HELPER}" >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "Created ${ROOT_DIR}/.env from .env.example. Review the values before starting gunicorn."
fi

chmod 600 "${ROOT_DIR}/.env"

if [[ -x "${SYNC_DEPLOY_ENV}" ]]; then
  if "${SYNC_DEPLOY_ENV}"; then
    :
  else
    sync_status="$?"
    if [[ "${sync_status}" -eq 10 ]]; then
      echo "Applied git-tracked deployment settings from deploy/app.env."
    else
      exit "${sync_status}"
    fi
  fi
fi

while IFS= read -r -d '' env_entry; do
  export "${env_entry}"
done < <(python3 "${ENV_HELPER}" load "${ROOT_DIR}/.env")

mkdir -p "${ROOT_DIR}/var/data" "${ROOT_DIR}/var/log"

if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  python3 -m venv "${ROOT_DIR}/.venv"
fi

"${ROOT_DIR}/.venv/bin/pip" install --upgrade pip wheel
"${ROOT_DIR}/.venv/bin/pip" install -r "${ROOT_DIR}/server/requirements.txt"
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/server/manage.py" init-db

describe_args=()
if [[ -n "${GIZMOAPP_SHELL:-}" ]]; then
  describe_args+=(--shell "${GIZMOAPP_SHELL}")
fi
"${ROOT_DIR}/.venv/bin/python" "${ROOT_DIR}/server/manage.py" describe "${describe_args[@]}"

echo
echo "Checkout install complete for ${ROOT_DIR}."
echo "Next steps:"
echo "  1. Review ${ROOT_DIR}/.env for machine-specific values only"
echo "  2. Start or reload the gunicorn user service for this checkout"
echo "  3. Ensure nginx routes traffic to the configured GIZMOAPP_URL_PREFIX and GIZMOAPP_PORT"
