#!/bin/bash
# Видалення Svit Editor. Подвійний клік.
DIR="$HOME/.svit-editor"
SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
ANSWER=$(osascript -e 'button returned of (display dialog "Видалити Svit Editor з цього Мака?\n\nБуде видалено програму, налаштування, ключ, модель мови і файли кольору (LUT). Змонтовані таймлайни в DaVinci і експортовані MP4 залишаться." buttons {"Скасувати", "Видалити"} default button "Скасувати" with title "Svit Editor" with icon caution)' 2>/dev/null)
[ "$ANSWER" = "Видалити" ] || exit 0
rm -f "$SCRIPTS/Svit Editor.py" "$SCRIPTS/TikTok Editor.py"
rm -rf "$DIR" "$HOME/.tiktok-editor" "$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-"*
rm -rf "$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit Editor"
if [ -d "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit Editor" ]; then
  rm -rf "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit Editor" 2>/dev/null || \
    osascript -e 'do shell script "rm -rf \"/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/Svit Editor\"" with administrator privileges' >/dev/null 2>&1
fi
osascript -e 'display dialog "Svit Editor видалено. Перезапусти DaVinci, щоб він зник з меню." buttons {"OK"} default button "OK" with title "Svit Editor"' >/dev/null 2>&1
