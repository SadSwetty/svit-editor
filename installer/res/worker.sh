#!/bin/bash
# Svit Editor — робоча частина інсталятора.
# worker.sh <install|python|cli> <папка Resources> <файл прогресу>
# Пише в файл прогресу рядки:  P|відсоток|крок|повідомлення   E|код|текст   D|версія|режим

MODE="$1"; RES="$2"; PF="$3"
DIR="$HOME/.svit-editor"
SCRIPTS="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
LOG="$DIR/install.log"
PKGS="${SVIT_PKGS:-faster-whisper anthropic pillow numpy av pywebview>=5.1 yt-dlp certifi}"
MODEL_DIR="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-medium"
MODEL_BYTES=1530000000
PY_URL="https://www.python.org/ftp/python/3.13.3/python-3.13.3-macos11.pkg"
VERSION="$(cat "$RES/payload/VERSION" 2>/dev/null || echo "?")"

mkdir -p "$DIR"
chmod 700 "$DIR" 2>/dev/null   # журнали, запити й ключ — лише для власника Мака
: > "$PF"
echo "=== $(date) $MODE $VERSION" >> "$LOG"

p()    { echo "P|$1|$2|$3" >> "$PF"; [ "$MODE" = "cli" ] && echo "[$1%] $3"; return 0; }
fail() { echo "E|$1|$2" >> "$PF"; echo "ПОМИЛКА: $2" >> "$LOG"; [ "$MODE" = "cli" ] && echo "Помилка: $2"; exit 1; }

find_python() {
  local c v
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    for v in 3.13 3.12 3.11 3.10 3.9; do
      for c in "/Library/Frameworks/Python.framework/Versions/$v/bin/python3" "/opt/homebrew/bin/python$v"; do
        [ -x "$c" ] && file -L "$c" 2>/dev/null | grep -q arm64 && { echo "$c"; return 0; }
      done
    done
  fi
  for v in 3.13 3.12 3.11 3.10 3.9; do
    for c in "/Library/Frameworks/Python.framework/Versions/$v/bin/python3" \
             "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v"; do
      [ -x "$c" ] && { echo "$c"; return 0; }
    done
  done
  for c in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      echo "$c"; return 0
    fi
  done
  if xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ] && \
     /usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo /usr/bin/python3; return 0
  fi
  return 1
}

# ---------------------------------------------------------------- завантаження Python
if [ "$MODE" = "python" ]; then
  PKG="$DIR/python-installer.pkg"
  p 2 python "Завантажую Python"
  curl -fsSL "$PY_URL" -o "$PKG" >> "$LOG" 2>&1 &
  CP=$!
  while kill -0 $CP 2>/dev/null; do
    SZ=$(stat -f%z "$PKG" 2>/dev/null || echo 0)
    PCT=$(( SZ * 95 / 72000000 )); [ $PCT -gt 95 ] && PCT=95
    p $PCT python "Завантажую Python · $(( SZ / 1048576 )) МБ"
    sleep 0.5
  done
  wait $CP || { open "https://www.python.org/downloads/macos/"; fail download "Не вдалося завантажити Python. Відкрив сторінку завантаження — встанови звідти й натисни «Спробувати ще раз»."; }
  p 100 python "Відкриваю встановлення Python"
  open "$PKG"
  echo "D|$VERSION|python" >> "$PF"
  exit 0
fi

# ---------------------------------------------------------------- встановлення / оновлення
p 2 check "Перевіряю систему"
sleep 0.4

WAS_INSTALLED=0
[ -f "$DIR/VERSION" ] && [ -f "$DIR/app/ui.py" ] && WAS_INSTALLED=1
UPDATE=0
if [ -x "$DIR/venv/bin/python3" ] && "$DIR/venv/bin/python3" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  UPDATE=1
fi

# Мак на Apple Silicon, а середовище зібране на Python тільки для Intel (працює через Rosetta, повільно):
# якщо є сучасний Python — перебудовуємо середовище на рідне
has_arm() { file -L "$1" 2>/dev/null | grep -q arm64; }
if [ "$UPDATE" = "1" ] && [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && ! has_arm "$DIR/venv/bin/python3"; then
  NEWPY="$(find_python)"
  if [ -n "$NEWPY" ] && has_arm "$NEWPY"; then
    p 4 env "Переходжу на швидку версію Python для Apple Silicon"
    UPDATE=0
  fi
fi

VENV="$DIR/venv"
if [ "$UPDATE" = "0" ]; then
  PYB="$(find_python)" || { echo "E|nopython|Потрібен Python 3.9 або новіший." >> "$PF"; exit 2; }
  p 6 env "Готую середовище"
  # нове середовище будуємо поруч і підміняємо в кінці, щоб не зламати те, що зараз працює
  if [ -x "$DIR/venv/bin/python3" ]; then VENV="$DIR/venv-new"; else VENV="$DIR/venv"; fi
  rm -rf "$VENV"
  "$PYB" -m venv "$VENV" >> "$LOG" 2>&1 || fail venv "Не вдалося створити середовище Python."
  "$VENV/bin/python3" -m pip install --quiet --upgrade pip >> "$LOG" 2>&1
fi

# компоненти: прогрес рахуємо за кількістю пакетів у лозі pip
p 12 deps "Ставлю компоненти"
PIPLOG="$DIR/pip.log"
: > "$PIPLOG"
# перевірені версії компонентів (requirements.lock), якщо є в пакеті; інакше — найновіші
LOCK="$RES/payload/requirements.lock"
if [ -z "$SVIT_PKGS" ] && [ -f "$LOCK" ]; then
  "$VENV/bin/python3" -m pip install --progress-bar off -r "$LOCK" > "$PIPLOG" 2>&1 &
else
  "$VENV/bin/python3" -m pip install --progress-bar off $PKGS > "$PIPLOG" 2>&1 &
fi
PIPPID=$!
EXPECT=45; [ "$UPDATE" = "1" ] && EXPECT=8
while kill -0 $PIPPID 2>/dev/null; do
  N=$(grep -c -E "^(Collecting|Requirement already satisfied)" "$PIPLOG" 2>/dev/null); N=${N:-0}
  NAME=$(grep -E "^(Collecting|Downloading)" "$PIPLOG" | tail -1 | awk '{print $2}' | sed 's/[<>=!].*//; s/-[0-9].*//; s/\.whl$//')
  PCT=$(( 12 + N * 40 / EXPECT )); [ $PCT -gt 52 ] && PCT=52
  p $PCT deps "Ставлю компоненти${NAME:+ · $NAME}"
  sleep 0.5
done
wait $PIPPID || { cat "$PIPLOG" >> "$LOG"; fail deps "Не вдалося встановити компоненти. Перевір інтернет і спробуй ще раз."; }
cat "$PIPLOG" >> "$LOG"
# свіжий yt-dlp (сайти часто ламають старі версії) і маскування під браузер для TikTok — необов'язково
if [ -z "$SVIT_PKGS" ] && [ ! -f "$LOCK" ]; then
  p 53 deps "Оновлюю завантажувач референсів"
  "$VENV/bin/python3" -m pip install --quiet --upgrade "yt-dlp[default]" >> "$LOG" 2>&1 || echo "yt-dlp upgrade failed" >> "$LOG"
  "$VENV/bin/python3" -m pip install --quiet "curl_cffi" >> "$LOG" 2>&1 || echo "curl_cffi failed (не критично)" >> "$LOG"
fi

# модель розпізнавання мови: справжній прогрес за розміром завантаженого
if [ -n "$SVIT_SKIP_MODEL" ] || [ -f "$MODEL_DIR/refs/main" ] && ! ls "$MODEL_DIR/blobs/"*.incomplete >/dev/null 2>&1; then
  p 92 model "Модель мови вже на місці"
else
  p 54 model "Завантажую модель мови"
  HF_HUB_DISABLE_PROGRESS_BARS=1 "$VENV/bin/python3" -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')" >> "$LOG" 2>&1 &
  MPID=$!
  while kill -0 $MPID 2>/dev/null; do
    KB=$(du -sk "$MODEL_DIR" 2>/dev/null | awk '{print $1}'); KB=${KB:-0}
    B=$(( KB * 1024 ))
    PCT=$(( 54 + B * 38 / MODEL_BYTES )); [ $PCT -gt 92 ] && PCT=92
    p $PCT model "Завантажую модель мови · $(( B / 1048576 )) з $(( MODEL_BYTES / 1048576 )) МБ"
    sleep 0.5
  done
  wait $MPID || fail model "Не вдалося завантажити модель мови. Перевір інтернет і спробуй ще раз."
fi

# список встановлених версій — щоб автор міг зафіксувати перевірений набір
"$VENV/bin/python3" -m pip freeze > "$DIR/installed-versions.txt" 2>/dev/null
# підміняємо середовище на нове
if [ "$VENV" = "$DIR/venv-new" ]; then
  rm -rf "$DIR/venv-old"; mv "$DIR/venv" "$DIR/venv-old" && mv "$DIR/venv-new" "$DIR/venv" && rm -rf "$DIR/venv-old"
fi

# файли програми
p 95 files "Додаю Svit Editor у DaVinci"
mkdir -p "$DIR/app" "$SCRIPTS" || fail files "Не вдалося створити папку скриптів DaVinci."
rm -rf "$DIR/app"
cp -R "$RES/payload/app" "$DIR/app" || fail files "Не вдалося скопіювати файли програми."
cp "$RES/payload/VERSION" "$DIR/app/VERSION"
cp "$RES/payload/VERSION" "$DIR/VERSION"
SRC_PY="$RES/payload/resolve/Svit Editor.py"
DST_PY="$SCRIPTS/Svit Editor.py"
rm -f "$DST_PY" 2>/dev/null
if ! cp "$SRC_PY" "$DST_PY" 2>>"$LOG"; then
  # файл заблокований (наприклад, доданий раніше вручну) — просимо пароль у звичайному вікні macOS
  # шляхи передаємо аргументами і беремо в лапки через quoted form — без ризику підставити команду
  osascript -e 'on run argv
    set s to quoted form of item 1 of argv
    set d to quoted form of item 2 of argv
    set u to quoted form of item 3 of argv
    do shell script "rm -f " & d & "; cp " & s & " " & d & "; chown " & u & " " & d with administrator privileges with prompt "Svit Editor хоче оновити свій файл у папці скриптів DaVinci."
  end run' "$SRC_PY" "$DST_PY" "$USER" >> "$LOG" 2>&1 \
    || fail files "Не вдалося додати програму в DaVinci (немає дозволу)."
fi

# прибрати старі версії
rm -f "$SCRIPTS/TikTok Editor.py" "$DIR/brain.py" "$DIR/header.png"
if [ -d "$HOME/.tiktok-editor" ]; then
  [ -f "$HOME/.tiktok-editor/config.json" ] && [ ! -f "$DIR/config.json" ] && cp "$HOME/.tiktok-editor/config.json" "$DIR/config.json"
  rm -rf "$HOME/.tiktok-editor"
fi
[ -f "$DIR/config.json" ] || echo '{"api_key": ""}' > "$DIR/config.json"
chmod 600 "$DIR/config.json"

# деінсталятор поруч з програмою
cp "$RES/uninstall.command" "$DIR/Видалити Svit Editor.command" 2>/dev/null && chmod +x "$DIR/Видалити Svit Editor.command"

sleep 0.3
p 100 done "Готово"
echo "D|$VERSION|$([ "$WAS_INSTALLED" = "1" ] && echo update || echo install)" >> "$PF"
[ "$MODE" = "cli" ] && echo "✅ Svit Editor $VERSION готовий. Перезапусти DaVinci: Workspace → Scripts → Svit Editor"
exit 0
