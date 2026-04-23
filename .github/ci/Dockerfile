# CI image for qtile.
#
# Builds from the current Ubuntu LTS and installs the exact same packages,
# wayland stack, and uv toolchain the GitHub Actions runner used to install
# step-by-step. The image is intentionally built fresh (no caching) each CI
# run; the only source files copied in are those needed to install system
# dependencies. The qtile source tree itself is bind-mounted at run time so
# the same image works for both GitHub Actions and local developers.

FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH="/root/.local/bin:${PATH}"

# Base tools needed to drive the rest of the install (sudo is required because
# scripts/ubuntu_wayland_setup uses it; inside the container we run as root so
# sudo becomes a no-op passthrough). The build toolchain (build-essential,
# cmake, pkg-config, libxml2-dev, libffi-dev, libexpat1-dev, libssl-dev) is
# pre-installed on GitHub's ubuntu-24.04 runner but not in a fresh ubuntu
# image; the wayland and xwayland meson builds need it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        libexpat1-dev \
        libffi-dev \
        libssl-dev \
        libxml2-dev \
        pkg-config \
        sudo \
        wget \
        yq \
    && rm -rf /var/lib/apt/lists/*

# Install the apt packages declared in .readthedocs.yaml, matching the
# "Install dependencies" step from the old GitHub Actions workflow.
COPY .readthedocs.yaml /tmp/.readthedocs.yaml
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        $(yq -r '.build.apt_packages | join(" ")' /tmp/.readthedocs.yaml) \
    && rm -rf /var/lib/apt/lists/* /tmp/.readthedocs.yaml

# Build and install the wayland stack (wayland, wayland-protocols, libdrm,
# seatd, pixman, hwdata, xwayland, wlroots) using the same script the CI used
# before. Scratch build artefacts are removed afterwards so they don't bloat
# the image.
COPY scripts/ubuntu_wayland_setup /tmp/ubuntu_wayland_setup
RUN cd /tmp \
    && bash -x ubuntu_wayland_setup \
    && cd / \
    && rm -rf /tmp/ubuntu_wayland_setup /tmp/cache \
        /tmp/wayland-* /tmp/wlroots-* /tmp/libdrm-* /tmp/seatd-* \
        /tmp/pixman-* /tmp/hwdata-* /tmp/xserver-*

# Install uv (replaces the astral-sh/setup-uv GitHub Action). Individual
# python toolchains are fetched on demand by uv when `make check` runs.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# The qtile source tree is mounted here at run time.
WORKDIR /qtile
