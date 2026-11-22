#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.analogart.gamesirbridge.plist"
pkill -f "GameSir Bridge" 2>/dev/null || true
pkill -f "menubar_app.py" 2>/dev/null || true
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "/Applications/GameSir Bridge.app"
echo "GameSir Bridge desinstalado completamente!"
