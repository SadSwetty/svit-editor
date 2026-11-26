#!/bin/bash
# Оновлення Svit Film: запускається кнопкою «Update Svit Film» у самому плагіні.
# Перевіряє релізи svit-film-* на GitHub, питає, завантажує архів і ставить новий плагін
# у /Library/OFX/Plugins (пароль адміністратора). Після цього треба перезапустити DaVinci.
CUR="${1:-0}"
REPO="SadSwetty/svit-editor"
DST="/Library/OFX/Plugins"
LOCK="/tmp/svitfilm-update.lock"
mkdir "$LOCK" 2>/dev/null || exit 0          # уже перевіряє — другий раз не відкриваємо
TMP="$(mktemp -d /tmp/svitfilm.XXXXXX)"
trap 'rm -rf "$TMP" "$LOCK"' EXIT

say() { osascript -e "display dialog \"$1\" buttons {\"Добре\"} default button 1 with title \"Svit Film\"" >/dev/null 2>&1; }
ask() { osascript -e "button returned of (display dialog \"$1\" buttons {\"Пізніше\", \"Оновити\"} default button 2 with title \"Svit Film\")" 2>/dev/null; }
vsort() { sort -t. -k1,1n -k2,2n -k3,3n; }

JSON="$(curl -fsSL --max-time 20 -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO/releases?per_page=100")" \
  || { say "Не вдалося зв'язатися з GitHub. Перевір інтернет і спробуй ще раз."; exit 1; }
LATEST="$(printf '%s' "$JSON" | grep -o '"tag_name": *"svit-film-[0-9][0-9.]*"' \
          | sed -E 's/.*svit-film-([0-9.]+)"/\1/' | vsort | tail -1)"
[ -n "$LATEST" ] || { say "На GitHub не знайдено жодної версії Svit Film."; exit 1; }

NEWEST="$(printf '%s\n%s\n' "$CUR" "$LATEST" | vsort | tail -1)"
if [ "$LATEST" = "$CUR" ] || [ "$NEWEST" != "$LATEST" ]; then
  say "У тебе остання версія Svit Film ($CUR)."; exit 0
fi
[ "$(ask "Вийшла Svit Film $LATEST (у тебе $CUR). Оновити зараз?")" = "Оновити" ] || exit 0

URL="https://github.com/$REPO/releases/download/svit-film-$LATEST/Svit.Film.$LATEST.zip"
curl -fsSL --max-time 300 -o "$TMP/sf.zip" "$URL" && ditto -x -k "$TMP/sf.zip" "$TMP/x" \
  || { say "Не вдалося завантажити Svit Film $LATEST. Спробуй пізніше."; exit 1; }
SRC="$(find "$TMP/x" -maxdepth 3 -type d -name SvitFilm.ofx.bundle | head -1)"
[ -n "$SRC" ] && file "$SRC/Contents/MacOS/SvitFilm.ofx" | grep -q Mach-O \
  || { say "Архів Svit Film $LATEST пошкоджений. Спробуй пізніше."; exit 1; }

osascript -e 'on run argv
  set s to quoted form of item 1 of argv
  set d to quoted form of item 2 of argv
  do shell script "mkdir -p " & d & " && rm -rf " & d & "/SvitFilm.ofx.bundle && cp -R " & s & " " & d & "/ && xattr -dr com.apple.quarantine " & d & "/SvitFilm.ofx.bundle; true" with administrator privileges with prompt "Svit Film хоче оновити свій ефект для DaVinci Resolve."
end run' "$SRC" "$DST" >/dev/null 2>&1 \
  || { say "Оновлення скасовано або не вдалося."; exit 1; }
say "Svit Film оновлено до $LATEST.\n\nПерезапусти DaVinci Resolve, щоб нова версія запрацювала."
