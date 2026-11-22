#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.analogart.gamesirbridge.plist"
pkill -f "GameSir Bridge" 2>/dev/null || true
pkill -f "menubar_app.py" 2>/dev/null || true
pkill -f "config_ui.py" 2>/dev/null || true
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST" /tmp/gamesir_bridge.* /tmp/gamesir_live.json
rm -rf "/Applications/GameSir Bridge.app"
echo "GameSir Bridge desinstalado completamente!"