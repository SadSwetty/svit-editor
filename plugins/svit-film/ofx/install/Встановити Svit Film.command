#!/bin/bash
# Встановлює Svit Film у DaVinci Resolve: /Library/OFX/Plugins (потрібен пароль адміністратора).
# Спершу копіюємо плагін у тимчасову папку від імені користувача: адмін-процес macOS часто не пускає
# в «Завантаження» чи «Робочий стіл», і тоді копія виходить порожньою.
cd "$(dirname "$0")"
SRC="$(pwd)/SvitFilm.ofx.bundle"
DST="/Library/OFX/Plugins"
msg() { osascript -e "display dialog \"$1\" buttons {\"Добре\"} default button 1 with title \"Svit Film\"" >/dev/null 2>&1; }
if [ ! -f "$SRC/Contents/MacOS/SvitFilm.ofx" ]; then
  msg "Поруч не знайдено SvitFilm.ofx.bundle. Розпакуй архів повністю і запусти ще раз."; exit 1
fi
TMP="$(mktemp -d /tmp/svitfilm.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
cp -R "$SRC" "$TMP/" && [ -f "$TMP/SvitFilm.ofx.bundle/Contents/MacOS/SvitFilm.ofx" ] \
  || { msg "Не вдалося прочитати плагін. Перенеси папку Svit Film на Робочий стіл і запусти ще раз."; exit 1; }
chmod -R a+rX "$TMP"
osascript -e 'on run argv
  set s to quoted form of item 1 of argv
  set d to quoted form of item 2 of argv
  do shell script "mkdir -p " & d & " && rm -rf " & d & "/SvitFilm.ofx.bundle && cp -R " & s & " " & d & "/ && xattr -dr com.apple.quarantine " & d & "/SvitFilm.ofx.bundle; codesign --force --deep -s - " & d & "/SvitFilm.ofx.bundle; test -f " & d & "/SvitFilm.ofx.bundle/Contents/MacOS/SvitFilm.ofx" with administrator privileges with prompt "Svit Film хоче встановити свій ефект для DaVinci Resolve."
end run' "$TMP/SvitFilm.ofx.bundle" "$DST" >/dev/null 2>&1 \
  || { msg "Не вдалося встановити Svit Film."; exit 1; }
# скинути кеш плагінів DaVinci, щоб він перечитав Svit Film (DaVinci збудує кеш заново)
rm -f "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/OFXPluginCacheV2.xml"
msg "Svit Film встановлено.\n\nПерезапусти DaVinci Resolve → Effects → OpenFX → Svit → Svit Film.\nЯкщо не видно: Preferences → System → Video Plugins → постав галочку біля SvitFilm."
