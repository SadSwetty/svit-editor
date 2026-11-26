#!/bin/bash
# Збирає Svit Film для Мака на Linux (без Мака): компілятор Zig робить Mach-O для arm64 і x86_64,
# llvm-lipo склеює їх в один універсальний файл. Zig сам ставить ad-hoc підпис (обов'язковий для arm64).
set -euo pipefail
cd "$(dirname "$0")"
VER="$(tr -d '[:space:]' < VERSION)"
ZIG="${ZIG:-python3 -m ziglang}"
LIPO="${LIPO:-$(ls /usr/bin/llvm-lipo* 2>/dev/null | head -1)}"
python3 gen_metal_src.py
[ -d openfx/include ] || git clone -q --depth 1 https://github.com/AcademySoftwareFoundation/openfx openfx
B="build/SvitFilm.ofx.bundle"
rm -rf build && mkdir -p "$B/Contents/MacOS" "$B/Contents/Resources" build/obj
for T in aarch64 x86_64; do
  $ZIG c++ -target $T-macos.11.0 -std=c++17 -O3 -ffast-math -fno-finite-math-only -fvisibility=hidden -shared \
    -DSVIT_VERSION="\"$VER\"" -Iopenfx/include -Isrc src/SvitFilm.cpp -Wl,-install_name,@rpath/SvitFilm.ofx -o build/obj/SvitFilm-$T.ofx
done
"$LIPO" -create build/obj/SvitFilm-aarch64.ofx build/obj/SvitFilm-x86_64.ofx -output "$B/Contents/MacOS/SvitFilm.ofx"
"$LIPO" -info "$B/Contents/MacOS/SvitFilm.ofx"
cp res/update.sh "$B/Contents/Resources/" && chmod +x "$B/Contents/Resources/update.sh"
cp ../logo/svit-film-icon-256.png "$B/Contents/Resources/com.sadsvit.SvitFilm.png"
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
echo "OK: $B"
