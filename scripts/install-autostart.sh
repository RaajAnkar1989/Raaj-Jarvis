#!/usr/bin/env bash
# Install macOS LaunchAgent — JARVIS starts automatically when you log in.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.raaj.jarvis.stack"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
STACK="$ROOT/scripts/jarvis-stack.sh"

chmod +x "$STACK" "$ROOT/scripts/jarvis-stack.sh" 2>/dev/null || true

mkdir -p "${HOME}/Library/LaunchAgents" "$ROOT/data/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${STACK}</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT}/data/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/data/logs/launchd.err.log</string>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

echo ""
echo "  JARVIS autostart installed."
echo "  Starts on login: PWA backend + named Cloudflare tunnel."
echo "  Logs: ${ROOT}/data/logs/"
echo ""
echo "  Uninstall: launchctl bootout gui/$(id -u)/${LABEL} && rm ${PLIST}"
echo ""
