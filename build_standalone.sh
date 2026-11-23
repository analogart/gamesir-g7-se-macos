#!/bin/bash
set -e

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="$(command -v python3)"
"$PYTHON_BIN" -m pip install --break-system-packages --quiet pyinstaller -r requirements.txt

LIBUSB_DYLIB=""
for candidate in "/opt/homebrew/lib/libusb-1.0.dylib" "/usr/local/lib/libusb-1.0.dylib"; do
    if [ -f "$candidate" ]; then
        LIBUSB_DYLIB="$candidate"
        break
    fi
done

if [ -z "$LIBUSB_DYLIB" ]; then
    echo "Erro: libusb-1.0.dylib não encontrado. Rode: brew install libusb"
    exit 1
fi

ARCH="$(uname -m)"
rm -rf build dist

"$PYTHON_BIN" -m PyInstaller \
    --noconfirm \
    --windowed \
    --name "GameSir Bridge" \
    --icon "AppIcon.icns" \
    --osx-bundle-identifier "com.analogart.gamesirbridge" \
    --add-data "profiles.json:." --add-data "assets:assets" \
    --add-data "AppIcon.icns:." \
    --add-binary "$LIBUSB_DYLIB:." \
    --hidden-import "usb.backend.libusb1" \
    --hidden-import "WebKit" \
    menubar_app.py

PLIST="dist/GameSir Bridge.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 12.0" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string 6.4.0" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 6.4.0" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 6.4.0" "$PLIST" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion 6.4.0" "$PLIST"

codesign --force --deep --sign - "dist/GameSir Bridge.app"
ditto -c -k --sequesterRsrc --keepParent "dist/GameSir Bridge.app" "dist/GameSir-Bridge-v6.4.0-macOS-${ARCH}.zip"

echo "Build standalone pronto em: dist/GameSir-Bridge-v6.4.0-macOS-${ARCH}.zip"
