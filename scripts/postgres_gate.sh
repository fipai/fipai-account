#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/venv/bin/python}"

usage() {
  printf 'Usage: %s [--full]\n' "$0"
  printf 'Runs the PostgreSQL-only release gate. --full runs the complete Account test suite.\n'
}

FULL=false
case "${1:-}" in
  "") ;;
  --full) FULL=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ "${USE_POSTGRES:-}" != "true" ]]; then
  printf 'ERROR: USE_POSTGRES must be exactly true; SQLite cannot satisfy this gate.\n' >&2
  exit 2
fi

required=(DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'ERROR: required PostgreSQL variable %s is not set.\n' "$name" >&2
    exit 2
  fi
done

if [[ "${DB_NAME}" == *.db || "${DB_NAME}" == *.sqlite || "${DB_NAME}" == *.sqlite3 ]]; then
  printf 'ERROR: DB_NAME appears to select SQLite, not PostgreSQL.\n' >&2
  exit 2
fi
if [[ "${DB_PASSWORD}" == "your_postgres_password" || "${DB_PASSWORD}" == "REPLACE_"* ]]; then
  printf 'ERROR: DB_PASSWORD is still a placeholder.\n' >&2
  exit 2
fi
if [[ ! "${DB_PORT}" =~ ^[0-9]+$ ]] || (( DB_PORT < 1 || DB_PORT > 65535 )); then
  printf 'ERROR: DB_PORT must be an integer from 1 to 65535.\n' >&2
  exit 2
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  printf 'ERROR: Python executable is unavailable; set PYTHON_BIN or create ./venv.\n' >&2
  exit 2
fi

cd "${ROOT_DIR}"
printf '[gate] Django system checks\n'
"${PYTHON_BIN}" manage.py check
printf '[gate] Migration drift check\n'
"${PYTHON_BIN}" manage.py makemigrations --check --dry-run

if [[ "${FULL}" == true ]]; then
  printf '[gate] Full Account test suite on PostgreSQL\n'
  "${PYTHON_BIN}" manage.py test tests/ -v 1 --noinput
else
  printf '[gate] PostgreSQL concurrency and migration tests\n'
  "${PYTHON_BIN}" manage.py test \
    tests.test_auth_concurrency \
    tests.test_payment_concurrency \
    tests.test_payment_migration \
    -v 1 --noinput
fi

printf 'PASS: Account PostgreSQL release gate succeeded.\n'
