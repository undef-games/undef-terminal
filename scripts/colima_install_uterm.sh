#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# colima_install_uterm.sh
#
# Build and install pam_uterm.so + libuterm_capture.so into the running Colima VM,
# then wire up /etc/pam.d/sshd so PAM events are forwarded to PamNotifyListener.
#
# Usage (from repo root, with Colima running):
#   bash scripts/colima_install_uterm.sh
#
# What it does:
#   1. Installs build deps (gcc, make, libpam0g-dev) inside Colima
#   2. Builds libuterm_capture.so from native/capture/
#   3. Builds pam_uterm.so from native/pam_uterm/
#   4. Installs both .so files to /usr/local/lib/ and /lib/security/
#   5. Adds a session line to /etc/pam.d/sshd (idempotent)
#   6. Prints verification instructions
#
# After running, start the undef-terminal server on the host and SSH in
# to see PamNotifyListener receive the open/close events.

set -euo pipefail

PTY_PKG="/Users/tim/code/gh/undef-games/undef-terminal/packages/undef-terminal-pty"
CAPTURE_SRC="$PTY_PKG/native/capture"
PAM_SRC="$PTY_PKG/native/pam_uterm"
NOTIFY_SOCKET="/run/uterm-notify.sock"
CAP_LIB="/usr/local/lib/libuterm_capture.so"
PAM_MODULE="/lib/security/pam_uterm.so"
PAM_LINE="session  optional  pam_uterm.so socket=${NOTIFY_SOCKET} mode=capture lib=${CAP_LIB} cap_dir=/run"

_run() {
    colima ssh -- sh -c "$1"
}

echo "==> Checking Colima is running..."
colima status --profile default 2>&1 | grep -q "is running" || {
    echo "ERROR: Colima is not running. Start it with: colima start"
    exit 1
}

echo "==> Installing build dependencies..."
_run "DEBIAN_FRONTEND=noninteractive sudo apt-get update -qq && sudo apt-get install -y -qq gcc make libpam0g-dev"

echo "==> Building libuterm_capture.so (Linux aarch64)..."
_run "make -C $CAPTURE_SRC clean && make -C $CAPTURE_SRC"

echo "==> Installing libuterm_capture.so to ${CAP_LIB}..."
_run "sudo install -m 0755 $CAPTURE_SRC/libuterm_capture.so $CAP_LIB && sudo ldconfig"

echo "==> Building pam_uterm.so (Linux aarch64)..."
_run "make -C $PAM_SRC clean && make -C $PAM_SRC"

echo "==> Installing pam_uterm.so to ${PAM_MODULE}..."
_run "sudo mkdir -p /lib/security && sudo install -m 0755 $PAM_SRC/pam_uterm.so $PAM_MODULE"

echo "==> Verifying .so files are valid ELF..."
_run "readelf -h $CAP_LIB | grep 'Type:' && readelf -h $PAM_MODULE | grep 'Type:'"

echo "==> Wiring up /etc/pam.d/sshd (idempotent)..."
_run "grep -qF 'pam_uterm.so' /etc/pam.d/sshd || printf '\n# undef-terminal session capture\n${PAM_LINE}\n' | sudo tee -a /etc/pam.d/sshd > /dev/null"

echo "==> Current pam_uterm lines in /etc/pam.d/sshd:"
_run "grep pam_uterm /etc/pam.d/sshd || echo '  (none found — check above step)'"

echo ""
echo "==> Done."
echo ""
echo "Next steps to verify end-to-end:"
echo "  1. Start the undef-terminal server on your Mac (with PamNotifyListener"
echo "     bound to a socket accessible from Colima, or use a forwarded path)."
echo "  2. SSH into Colima: colima ssh"
echo "  3. In a second terminal, watch server logs for PamEvent{event='open', ...}"
echo "  4. Exit Colima SSH — watch for PamEvent{event='close', ...}"
echo ""
echo "Note: The notify socket ${NOTIFY_SOCKET} is inside the Colima VM."
echo "The undef-terminal server must either run inside Colima, or the socket"
echo "path must be on a virtiofs mount accessible from both sides."
