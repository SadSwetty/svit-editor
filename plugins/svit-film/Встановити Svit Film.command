#!/bin/bash
# Кладе Svit Film у папку ефектів DaVinci Resolve (LUT → Svit).
cd "$(dirname "$0")"
DST="/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit"
SRC="$(pwd)/Svit Film.dctl"
if mkdir -p "$DST" 2>/dev/null && cp "$SRC" "$DST/" 2>/dev/null; then
  OK=1
else
  osascript -e 'on run argv
    do shell script "mkdir -p " & quoted form of item 2 of argv & " && cp " & quoted form of item 1 of argv & " " & quoted form of item 2 of argv with administrator privileges with prompt "Svit Film хоче додати свій ефект у папку DaVinci."
  end run' "$SRC" "$DST" && OK=1
fi
if [ "$OK" = "1" ]; then
  osascript -e 'display dialog "Svit Film встановлено.\n\nПерезапусти DaVinci → Color → Effects → DCTL → кинь на ноду → DCTL List: Svit / Svit Film." buttons {"Добре"} default button 1 with title "Svit Film"' >/dev/null
else
  osascript -e 'display dialog "Не вдалося встановити. Скопіюй файл «Svit Film.dctl» вручну в /Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/" buttons {"Добре"} default button 1 with title "Svit Film"' >/dev/null
fi
