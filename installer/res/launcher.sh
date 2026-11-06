#!/bin/bash
# Svit Editor Installer — запуск. Готує Python для вікна і відкриває гарне вікно інсталятора.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
DIR="$HOME/.svit-editor"
LOG="$DIR/install.log"
VPY="$DIR/venv/bin/python3"
PY_PKG="https://www.python.org/ftp/python/3.11.9/python-3.11.9-macos11.pkg"
mkdir -p "$DIR"
echo "=== $(date) launcher" >> "$LOG"

find_python() {
  local c v
  for v in 3.13 3.12 3.11 3.10 3.9; do
    for c in "/Library/Frameworks/Python.framework/Versions/$v/bin/python3" \
             "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v"; do
      [ -x "$c" ] && { echo "$c"; return 0; }
    done
  done
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && { echo "$c"; return 0; }
  done
  if xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo /usr/bin/python3; return 0
  fi
  return 1
}

# запасний шлях: встановлення в Терміналі з поясненням
fallback() {
  local why="$(echo "$1" | tr -d '"`$\\')"
  local d; d="$(mktemp -d "${TMPDIR:-/tmp}/svit-install.XXXXXX")" || exit 1
  local f="$d/Svit Editor install.command"
  printf '#!/bin/bash\necho "%s"\necho "Встановлюю тут, у Терміналі:"\necho\nbash %q cli %q %q\n' \
    "$why" "$RES/worker.sh" "$RES" "$d/progress.txt" > "$f"
  chmod +x "$f"; open "$f"; exit 0
}

if ! "$VPY" -c "import webview" >/dev/null 2>&1; then
  PYB="$(find_python)"
  if [ -z "$PYB" ]; then
    ANS=$(osascript -e 'button returned of (display dialog "Для Svit Editor потрібен Python — безкоштовна програма з python.org.\n\nЗавантажити його зараз? Після встановлення Python відкрий Svit Editor Installer ще раз." buttons {"Скасувати", "Завантажити"} default button "Завантажити" with title "Svit Editor" with icon note)' 2>/dev/null)
    [ "$ANS" = "Завантажити" ] && open "$PY_PKG"
    exit 0
  fi
  osascript -e 'display notification "Готую інсталятор — це до хвилини" with title "Svit Editor"' >/dev/null 2>&1
  if ! "$VPY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    rm -rf "$DIR/venv"
    "$PYB" -m venv "$DIR/venv" >> "$LOG" 2>&1 || fallback "Не вдалося підготувати Python."
  fi
  "$VPY" -m pip install --quiet --upgrade pip >> "$LOG" 2>&1
  "$VPY" -m pip install --quiet pywebview >> "$LOG" 2>&1 || fallback "Не вдалося підготувати вікно інсталятора (перевір інтернет)."
fi

"$VPY" "$RES/installer_ui.py" "$RES" >> "$LOG" 2>&1 || fallback "Вікно інсталятора не відкрилось: $(tail -1 "$LOG")"
