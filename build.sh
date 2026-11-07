#!/bin/bash
# Збирає "Svit Editor Installer.app" і архів для роздачі: bash build.sh
set -e
cd "$(dirname "$0")"
VER="$(cat VERSION)"
APP="dist/Svit Editor Installer.app"
rm -rf dist && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/payload"
R="$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Svit Editor Installer</string>
  <key>CFBundleDisplayName</key><string>Svit Editor Installer</string>
  <key>CFBundleIdentifier</key><string>com.sadsvit.svit-editor.installer</string>
  <key>CFBundleVersion</key><string>$VER</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>SvitInstaller</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

cp installer/res/launcher.sh "$APP/Contents/MacOS/SvitInstaller"
chmod +x "$APP/Contents/MacOS/SvitInstaller"

cp installer/res/installer_ui.py installer/res/installer.html installer/res/header.png \
   installer/res/AppIcon.icns installer/res/worker.sh installer/res/uninstall.command "$R/"
python3 -c "from PIL import Image; im=Image.open('installer/res/icon.png'); im.thumbnail((256,256)); im.save('$R/icon.png')"
chmod +x "$R/worker.sh" "$R/uninstall.command"

mkdir -p "$R/payload/app/web" "$R/payload/resolve"
cp app/engine.py app/ui.py app/music.py app/refs.py app/svlog.py app/sigcheck.py app/textfx.py app/whatsnew.md "$R/payload/app/"
[ -f requirements.lock ] && cp requirements.lock "$R/payload/requirements.lock"
cp app/web/index.html app/web/i18n.js app/web/header.png app/web/style.css "$R/payload/app/web/"
cp -R app/web/fonts "$R/payload/app/web/fonts"
cp app/web/style.css "$R/style.css"
cp -R app/web/fonts "$R/fonts"
python3 -c "from PIL import Image; im=Image.open('app/web/icon.png'); im.thumbnail((512,512)); im.save('$R/payload/app/web/icon.png')"
cp "resolve/Svit Editor.py" "$R/payload/resolve/"
cp VERSION "$R/payload/VERSION"

# Особиста збірка для конкретної людини: SVIT_ACCESS_CODE=svit-… bash build.sh
# Код доступу потрапляє лише в цей zip і НІКОЛИ не має йти в release/ чи на GitHub.
PRIVATE=0
if [ -n "$SVIT_ACCESS_CODE" ]; then
  case "$SVIT_ACCESS_CODE" in svit-?*) ;; *) echo "SVIT_ACCESS_CODE має починатися з svit-"; exit 1;; esac
  printf '%s' "$SVIT_ACCESS_CODE" > "$R/payload/access_code"
  chmod 600 "$R/payload/access_code"
  PRIVATE=1
fi

# цифровий підпис: маніфест sha256 усіх файлів + підпис Ed25519 приватним ключем автора
KEY="${SVIT_SIGN_KEY:-$(cd "$(dirname "$0")/.." && pwd)/svit-signing/ed25519.key}"
if [ -f "$KEY" ]; then
  python3 -c "import sys; sys.path.insert(0,'app'); import sigcheck; sigcheck.make_manifest(sys.argv[1], sys.argv[2], bytes.fromhex(open(sys.argv[3]).read().strip())); ok,why=sigcheck.check_app(sys.argv[1], sys.argv[2]); print('підпис:', 'OK' if ok else why); sys.exit(0 if ok else 1)" \
    "dist/Svit Editor Installer.app" "$VER" "$KEY" || exit 1
else
  echo "УВАГА: немає ключа підпису ($KEY) — збірка НЕ підписана, автооновлення її не прийме"
fi
if [ "$PRIVATE" = "1" ]; then
  OUT="Svit Editor $VER (особиста — не публікувати).zip"
  (cd dist && zip -qry "$OUT" "Svit Editor Installer.app")
  echo "dist/$OUT"
  echo "УВАГА: у цьому архіві код доступу. Передай його людині особисто, НЕ клади в release/ і не комміть."
else
  (cd dist && zip -qry "Svit Editor $VER.zip" "Svit Editor Installer.app")
  echo "dist/Svit Editor $VER.zip"
fi
