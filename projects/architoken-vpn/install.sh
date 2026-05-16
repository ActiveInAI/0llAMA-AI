#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${HOME}/.local/share/architoken-vpn"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"
mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$AUTOSTART_DIR"
cp src/*.py "$APP_DIR/"
cp web/webrtc-check.html "$APP_DIR/"
cp examples/mode.example.json "$APP_DIR/mode.json"
if [ ! -f "$APP_DIR/nodes.json" ]; then
  cp examples/nodes.example.json "$APP_DIR/nodes.json"
fi
cp bin/vpn-mode "$BIN_DIR/vpn-mode"
cp bin/vpn-status "$BIN_DIR/vpn-status"
chmod +x "$APP_DIR"/*.py "$BIN_DIR/vpn-mode" "$BIN_DIR/vpn-status"
sed "s#\${HOME}#$HOME#g" desktop/architoken-vpn-tray.desktop > "$DESKTOP_DIR/architoken-vpn-tray.desktop"
cp "$DESKTOP_DIR/architoken-vpn-tray.desktop" "$AUTOSTART_DIR/architoken-vpn-tray.desktop"
echo "ArchIToken-VPN user files installed. Configure Xray/sing-box system services separately."
