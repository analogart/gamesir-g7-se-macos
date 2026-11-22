#!/bin/bash
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/Applications/GameSir Bridge.app"
RES_DIR="$APP_DIR/Contents/Resources"
PLIST_PATH="$HOME/Library/LaunchAgents/com.analogart.gamesirbridge.plist"

if command -v brew >/dev/null 2>&1; then
    if ! brew list libusb >/dev/null 2>&1; then
        echo "Instalando libusb via Homebrew..."
        brew install libusb
    fi
fi

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Erro: Python 3 não encontrado. Instale via Homebrew (brew install python)."
    exit 1
fi

echo "Instalando dependências Python em $PYTHON_BIN..."
"$PYTHON_BIN" -m pip install --break-system-packages --quiet -r "$PROJECT_DIR/requirements.txt"

echo "Criando bundle nativo em $APP_DIR..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$RES_DIR"

cp "$PROJECT_DIR"/*.py "$RES_DIR/"
[ -f "$PROJECT_DIR/profiles.json" ] && cp "$PROJECT_DIR/profiles.json" "$RES_DIR/profiles.json"
[ -f "$PROJECT_DIR/AppIcon.icns" ] && cp "$PROJECT_DIR/AppIcon.icns" "$RES_DIR/AppIcon.icns"
ln -sf "$PYTHON_BIN" "$APP_DIR/Contents/MacOS/python_bin"

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
    <key>CFBundleShortVersionString</key>
    <string>6.1.0</string>
    <key>CFBundleVersion</key>
    <string>6.1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
INFO

cat << 'EXEC' > "$APP_DIR/Contents/MacOS/GameSir Bridge"
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
APP_CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_CONTENTS/Resources"
exec "$APP_CONTENTS/MacOS/python_bin" -u "$APP_CONTENTS/Resources/menubar_app.py" > /tmp/gamesir_bridge.log 2>&1
EXEC

chmod +x "$APP_DIR/Contents/MacOS/GameSir Bridge"
codesign --force --deep --sign - "$APP_DIR"

echo "Configurando inicialização automática em segundo plano (LaunchAgent)..."
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
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "Instalação concluída! Abrindo GameSir Bridge v6.1.0..."
open -a "$APP_DIR"
