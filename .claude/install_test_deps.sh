#!/usr/bin/env bash
# Installs all system + Python deps needed to run the qtile test suite.
# Invoked from a Claude Code SessionStart hook. Idempotent: skips work
# that has already been done.

set -euo pipefail

STAMP_DIR="${HOME}/.cache/qtile-deps"
APT_STAMP="${STAMP_DIR}/apt.done"
WAYLAND_STAMP="${STAMP_DIR}/wayland.done"
UV_STAMP="${STAMP_DIR}/uv-sync.done"
LOG="${STAMP_DIR}/install.log"

mkdir -p "${STAMP_DIR}"
cd "$(dirname "$0")/.."

exec > >(tee -a "${LOG}") 2>&1
echo "=== qtile dep install $(date -Iseconds) ==="

# --- apt packages from .readthedocs.yaml -----------------------------------
APT_PKGS=(
  libdbus-1-dev libgirepository-2.0-dev gir1.2-gtk-3.0 gir1.2-notify-0.7
  gir1.2-gudev-1.0 graphviz imagemagick xserver-xephyr xvfb dbus-x11
  libnotify-bin libxcb-composite0-dev libxcb-icccm4-dev libxcb-res0-dev
  libxcb-render0-dev libxcb-xfixes0-dev libxkbcommon-dev python-gi-dev
  libcairo2-dev gir1.2-gdkpixbuf-2.0 librsvg2-dev libxcb-cursor0 git
  xterm libpulse0
)

if [ ! -f "${APT_STAMP}" ]; then
  echo "--- apt install (base) ---"
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "${APT_PKGS[@]}"
  touch "${APT_STAMP}"
else
  echo "apt packages already installed (remove ${APT_STAMP} to reinstall)"
fi

# --- wayland stack (builds wlroots etc. from source) -----------------------
if [ ! -f "${WAYLAND_STAMP}" ]; then
  echo "--- wayland setup (builds from source, takes a while) ---"
  bash -x ./scripts/ubuntu_wayland_setup
  sudo ldconfig
  touch "${WAYLAND_STAMP}"
else
  echo "wayland stack already built (remove ${WAYLAND_STAMP} to rebuild)"
fi

# --- Python env via uv with ALL extras -------------------------------------
# pyproject.toml has these optional-dependencies groups:
#   dev, optional_core, widgets, docs
EXTRAS=(--extra dev --extra optional_core --extra widgets --extra docs)

if [ ! -f "${UV_STAMP}" ] || [ pyproject.toml -nt "${UV_STAMP}" ]; then
  echo "--- uv sync with all extras ---"
  uv sync "${EXTRAS[@]}"
  touch "${UV_STAMP}"
else
  echo "uv env already in sync (pyproject.toml unchanged)"
fi

echo "=== done ==="
