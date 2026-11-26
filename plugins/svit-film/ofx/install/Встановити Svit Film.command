#!/bin/bash
# Встановлює Svit Film у DaVinci Resolve: /Library/OFX/Plugins (потрібен пароль адміністратора).
cd "$(dirname "$0")"
SRC="$(pwd)/SvitFilm.ofx.bundle"
DST="/Library/OFX/Plugins"
if [ ! -d "$SRC" ]; then
  osascript -e 'display dialog "Поруч не знайдено SvitFilm.ofx.bundle. Розпакуй архів повністю і запусти ще раз." buttons {"Добре"} with title "Svit Film"' >/dev/null; exit 1
fi
osascript -e 'on run argv
  set s to quoted form of item 1 of argv
  set d to quoted form of item 2 of argv
  do shell script "mkdir -p " & d & " && rm -rf " & d & "/SvitFilm.ofx.bundle && cp -R " & s & " " & d & "/ && xattr -dr com.apple.quarantine " & d & "/SvitFilm.ofx.bundle; codesign --force --deep -s - " & d & "/SvitFilm.ofx.bundle; true" with administrator privileges with prompt "Svit Film хоче встановити свій ефект для DaVinci Resolve."
end run' "$SRC" "$DST" >/dev/null 2>&1 \
  && osascript -e 'display dialog "Svit Film встановлено.\n\nПерезапусти DaVinci Resolve → Effects → OpenFX → Svit → Svit Film." buttons {"Добре"} default button 1 with title "Svit Film"' >/dev/null \
  || osascript -e 'display dialog "Не вдалося встановити Svit Film." buttons {"Добре"} with title "Svit Film"' >/dev/null
