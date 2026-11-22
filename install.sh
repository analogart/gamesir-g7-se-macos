#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/Applications/GameSir Bridge.app"
PLIST_PATH="$HOME/Library/LaunchAgents/com.analogart.gamesirbridge.plist"
PYTHON_BIN="$(command -v python3)"

echo "Instalando dependências Python..."
"$PYTHON_BIN" -m pip install --break-system-packages --quiet pyusb pynput rumps pyobjc-framework-Cocoa

echo "Criando bundle nativo em $APP_DIR..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
[ -f "$PROJECT_DIR/AppIcon.icns" ] && cp "$PROJECT_DIR/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"

cat << INFO > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>GameSir Bridge</string>
    <key>CFBundleIdentifier</key>
    <string>com.analogart.gamesirbridge</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleName</key>
    <string>GameSir Bridge</string>
    <key>CFBundleVersion</key>
    <string>5.0.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
INFO

cat << EXEC > "$APP_DIR/Contents/MacOS/GameSir Bridge"
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -u "$PROJECT_DIR/menubar_app.py" >> /tmp/gamesir_bridge.log 2>&1
EXEC

chmod +x "$APP_DIR/Contents/MacOS/GameSir Bridge"
codesign --force --deep --sign - "$APP_DIR"

echo "Configurando gatilho USB plug-and-play (IOKit LaunchAgent)..."
mkdir -p "$HOME/Library/LaunchAgents"
cat << PLIST > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.analogart.gamesirbridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$APP_DIR</string>
    </array>
    <key>LaunchEvents</key>
    <dict>
        <key>com.apple.iokit.matching</key>
        <dict>
            <key>GameSirG7SE</key>
            <dict>
                <key>idVendor</key>
                <integer>13623</integer>
                <key>idProduct</key>
                <integer>4112</integer>
                <key>IOProviderClass</key>
                <string>IOUSBHostDevice</string>
                <key>IOMatchLaunchStream</key>
                <true/>
            </dict>
        </dict>
    </dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
echo "Instalação concluída! Lembre-se de autorizar GameSir Bridge e Python em Privacidade e Segurança > Controle do Dispositivo e Acesso a Dados."
