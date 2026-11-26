#!/bin/bash
# Збирає Svit Film як OFX-плагін для DaVinci Resolve на Маку (Apple Silicon + Intel в одному файлі).
# Потрібно: інструменти розробника Xcode (xcode-select --install). Результат: build/SvitFilm.ofx.bundle
set -euo pipefail
cd "$(dirname "$0")"
VER="$(tr -d '[:space:]' < VERSION)"
[ -d openfx/include ] || git clone -q --depth 1 https://github.com/AcademySoftwareFoundation/openfx openfx
B="build/SvitFilm.ofx.bundle"
rm -rf build && mkdir -p "$B/Contents/MacOS" "$B/Contents/Resources"
clang++ -std=c++17 -O3 -ffast-math -fvisibility=hidden -bundle \
  -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 \
  -DSVIT_VERSION="\"$VER\"" -Iopenfx/include -Isrc src/SvitFilm.cpp -o "$B/Contents/MacOS/SvitFilm.ofx"
cp res/update.sh "$B/Contents/Resources/" && chmod +x "$B/Contents/Resources/update.sh"
cat > "$B/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleDevelopmentRegion</key><string>en</string>
  <key>CFBundleExecutable</key><string>SvitFilm.ofx</string>
  <key>CFBundleIdentifier</key><string>com.sadsvit.SvitFilm</string>
  <key>CFBundleName</key><string>Svit Film</string>
  <key>CFBundlePackageType</key><string>BNDL</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundleVersion</key><string>$VER</string>
</dict></plist>
PLIST
codesign --force --deep -s - "$B"
lipo -info "$B/Contents/MacOS/SvitFilm.ofx"
echo "OK: $B"
