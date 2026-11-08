#!/bin/bash
# Збірка підписаного релізу на GitHub Actions (див. .github/workflows/build-release.yml).
# Потрібно: секрет SVIT_SIGN_KEY_HEX (вміст svit-signing/ed25519.key), python3 з Pillow, gh.
# Шрифт Zvin Serif у репозиторії не лежить (trial-ліцензія) — беремо його з попереднього релізу.
set -euo pipefail
cd "$(dirname "$0")/.."
VER="$(tr -d '[:space:]' < VERSION)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- 1. ключ підпису: має збігатися з публічним ключем, вшитим у програму
[ -n "${SVIT_SIGN_KEY_HEX:-}" ] || { echo "::error::Немає секрету SVIT_SIGN_KEY_HEX"; exit 1; }
printf '%s' "$SVIT_SIGN_KEY_HEX" | tr -d '[:space:]' > "$WORK/ed25519.key"
chmod 600 "$WORK/ed25519.key"
python3 - "$WORK/ed25519.key" <<'PY'
import sys
sys.path.insert(0, "app")
import sigcheck
try:
    secret = bytes.fromhex(open(sys.argv[1]).read().strip())
except ValueError:
    sys.exit("::error::SVIT_SIGN_KEY_HEX — не hex. Встав вміст файлу ed25519.key повністю.")
if len(secret) != 32 or sigcheck.public_key(secret).hex() != sigcheck.PUBLIC_KEY_HEX:
    sys.exit("::error::Ключ у SVIT_SIGN_KEY_HEX не відповідає ключу перевірки в програмі.")
print("ключ підпису: OK")
PY

# ---- 2. шрифти з попереднього релізу (або з release/ у репозиторії)
if [ ! -d app/web/fonts ] || [ -z "$(ls -A app/web/fonts 2>/dev/null)" ]; then
  SRC=""
  if [ -n "${GH_TOKEN:-}" ]; then
    for TAG in $(gh release list --limit 20 --json tagName --jq '.[].tagName' 2>/dev/null); do
      if gh release download "$TAG" --pattern '*.zip' --dir "$WORK/prev" --clobber >/dev/null 2>&1; then
        SRC="$(ls "$WORK"/prev/*.zip | head -1)"; break
      fi
    done
  fi
  [ -n "$SRC" ] || SRC="$(ls release/*.zip 2>/dev/null | sort -V | tail -1 || true)"
  [ -n "$SRC" ] || { echo "::error::Не знайшов попереднього релізу, звідки взяти шрифти"; exit 1; }
  unzip -q "$SRC" "*/payload/app/web/fonts/*" -d "$WORK/fonts_src"
  mkdir -p app/web/fonts
  find "$WORK/fonts_src" -path "*/payload/app/web/fonts/*" -type f -exec cp {} app/web/fonts/ \;
  echo "шрифти: $(ls app/web/fonts | wc -l) файлів з $(basename "$SRC")"
fi

# ---- 3. збірка з підписом
SVIT_SIGN_KEY="$WORK/ed25519.key" bash build.sh
ZIP="dist/Svit Editor $VER.zip"
test -f "$ZIP"
test -f "dist/Svit Editor Installer.app/Contents/Resources/manifest.sig" || { echo "::error::Збірка не підписана"; exit 1; }

# ---- 4. запобіжники: ніяких кодів доступу і ключів у публічному архіві
if unzip -l "$ZIP" | grep -q "payload/access_code"; then echo "::error::У архіві код доступу"; exit 1; fi
if unzip -p "$ZIP" | grep -aqE "sk-ant-[A-Za-z0-9_-]{20,}"; then echo "::error::У архіві ключ Claude"; exit 1; fi
if unzip -l "$ZIP" | grep -qiE "ed25519\.key|\.key$"; then echo "::error::У архіві файл ключа"; exit 1; fi

# ---- 5. нотатки до релізу: розділ поточної версії з app/whatsnew.md
python3 - "$VER" > dist/notes.md <<'PY'
import sys
ver = sys.argv[1]
lines = open("app/whatsnew.md", encoding="utf-8").read().splitlines()
out, on = [], False
for l in lines:
    if l.startswith("Svit Editor "):
        if on:
            break
        on = l.strip() == f"Svit Editor {ver}"
        if on:
            out.append(f"## {l.strip()}")
        continue
    if on:
        out.append(l)
print("\n".join(out).strip() or f"## Svit Editor {ver}")
PY
cp "$ZIP" "dist/Svit.Editor.$VER.zip"
echo "готово: dist/Svit.Editor.$VER.zip"
