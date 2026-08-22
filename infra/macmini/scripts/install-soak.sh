#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BURNIN_ROOT=${FABOPS_BURNIN_ROOT:-"$HOME/Services/fabops-decision-lab-data/burnin"}
BIN_DIR="$BURNIN_ROOT/bin"
SAMPLES_DIR="$BURNIN_ROOT/samples"
PLIST="$HOME/Library/LaunchAgents/com.oosu.fabops-burnin.plist"
LABEL="com.oosu.fabops-burnin"
GUI_DOMAIN="gui/$(id -u)"
COLLECTOR_SOURCE="$REPO_ROOT/infra/macmini/soak_collector.py"
COLLECTOR_TARGET="$BIN_DIR/soak_collector.py"
SAMPLE_FILENAME="soak.jsonl"

mkdir -p "$BIN_DIR" "$SAMPLES_DIR" "$HOME/Library/LaunchAgents"
cp "$COLLECTOR_SOURCE" "$COLLECTOR_TARGET"
chmod 0700 "$COLLECTOR_TARGET"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$COLLECTOR_TARGET</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>/dev/null</string>
  <key>StandardErrorPath</key>
  <string>/dev/null</string>
</dict>
</plist>
EOF
chmod 0600 "$PLIST"

launchctl bootout "$GUI_DOMAIN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST"
launchctl enable "$GUI_DOMAIN/$LABEL"
launchctl kickstart -k "$GUI_DOMAIN/$LABEL"

printf 'label=%s\n' "$LABEL"
printf 'plist=%s\n' "$PLIST"
printf 'collector=%s\n' "$COLLECTOR_TARGET"
printf 'samples=%s\n' "$SAMPLES_DIR/$SAMPLE_FILENAME"
