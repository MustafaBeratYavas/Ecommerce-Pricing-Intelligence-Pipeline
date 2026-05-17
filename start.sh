#!/usr/bin/env bash

set -Eeuo pipefail

# Bootstrap the local Linux/macOS environment and run the scraping pipeline.

log() {
    printf '[%s] %s\n' "$1" "$2"
}

info() {
    log "INFO" "$1"
}

setup() {
    log "SETUP" "$1"
}

success() {
    log "SUCCESS" "$1"
}

warning() {
    log "WARNING" "$1"
}

error() {
    log "ERROR" "$1" >&2
}

on_error() {
    local line_number="$1"
    error "Unexpected failure at line ${line_number}."
}

find_python() {
    local candidate

    if [[ -n "${PYTHON_BIN:-}" ]]; then
        if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
            if "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
                command -v "$PYTHON_BIN"
                return 0
            fi
        fi

        error "PYTHON_BIN points to a Python interpreter older than 3.11 or not found: ${PYTHON_BIN}"
        return 1
    fi

    for candidate in python3.13 python3.12 python3.11 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
                command -v "$candidate"
                return 0
            fi
        fi
    done

    return 1
}

ensure_supported_platform() {
    case "$(uname -s)" in
        Linux|Darwin)
            return 0
            ;;
        *)
            warning "This launcher is intended for Linux/macOS. Continuing anyway."
            ;;
    esac
}

warn_if_chrome_missing() {
    case "$(uname -s)" in
        Darwin)
            if [[ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
                return 0
            fi

            if [[ -x "${HOME}/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
                return 0
            fi
            ;;
        *)
            if command -v google-chrome >/dev/null 2>&1; then
                return 0
            fi

            if command -v google-chrome-stable >/dev/null 2>&1; then
                return 0
            fi

            if command -v chromium >/dev/null 2>&1; then
                return 0
            fi

            if command -v chromium-browser >/dev/null 2>&1; then
                return 0
            fi
            ;;
    esac

    warning "Chrome/Chromium was not detected. SeleniumBase needs a local Chrome-compatible browser."
}

trap 'on_error "$LINENO"' ERR

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
cd "$SCRIPT_DIR"

info "Starting E-Commerce Pricing Intelligence Pipeline setup and execution..."
ensure_supported_platform
warn_if_chrome_missing

PYTHON="$(find_python)" || {
    error "Python 3.11+ is required. Install Python 3.11 or newer and try again."
    exit 1
}

PYTHON_VERSION="$("$PYTHON" -c 'import platform; print(platform.python_version())')"
setup "Using Python ${PYTHON_VERSION}: ${PYTHON}"

if [[ ! -d ".venv" || ! -x ".venv/bin/python" ]]; then
    setup "Virtual environment not found or not compatible with Linux/macOS. Creating..."
    "$PYTHON" -m venv .venv
fi

VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
    error "Failed to create a usable virtual environment at .venv."
    exit 1
fi

setup "Checking and installing dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip >/dev/null
"$VENV_PYTHON" -m pip install .

setup "Ensuring Chrome profile exists..."
"$VENV_PYTHON" -m src.tasks.create_profile

SEED_FILE="${SEED_FILE:-product_codes.txt}"
if [[ ! -f "$SEED_FILE" ]]; then
    warning "Seed file '${SEED_FILE}' not found. Creating an empty one..."
    : >"$SEED_FILE"
    warning "Please add product codes to '${SEED_FILE}' before the next run."
    exit 1
fi

setup "Seeding database with targets from '${SEED_FILE}'..."
"$VENV_PYTHON" -m src.tasks.seed_targets --file "$SEED_FILE"

printf '\n'
success "Setup completed successfully."
info "Starting E-Commerce Pricing Intelligence Pipeline..."
printf '%s\n' '======================================================================'

set +e
"$VENV_PYTHON" -m src.main
APP_EXIT_CODE=$?
set -e

printf '%s\n' '======================================================================'

if [[ "$APP_EXIT_CODE" -ne 0 ]]; then
    error "Application exited with an error code (${APP_EXIT_CODE})."
else
    success "Application completed successfully."
fi

exit "$APP_EXIT_CODE"
