# Svit Editor — готове середовище (Python 3.11 + усі компоненти), без pip.
# Підключається з launcher.sh і worker.sh. Потрібні змінні: RES, DIR, LOG; функція p (прогрес).
# Середовище лежить у ~/.svit-editor/runtime/python, а ~/.svit-editor/venv — посилання на нього
# (так його бачать DaVinci-частина і сама програма).

RT_REPO="SadSwetty/svit-editor"
type p >/dev/null 2>&1 || p() { :; }

rt_arch() { if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then echo arm64; else echo x86_64; fi; }
rt_wanted() { RT_WANT="$( { tr -d "[:space:]" < "$RES/payload/RUNTIME"; } 2>/dev/null)"; [ -n "$RT_WANT" ]; }
rt_have() { { tr -d "[:space:]" < "$DIR/runtime/python/SVIT_RUNTIME"; } 2>/dev/null; }
rt_check() { "$1/bin/python3" -c "import webview, faster_whisper, anthropic, av, numpy, PIL" >> "$LOG" 2>&1; }
rt_ok() { [ -n "$RT_WANT" ] && [ "$(rt_have)" = "$RT_WANT" ] && rt_check "$DIR/runtime/python"; }

rt_link() {
  if [ -L "$DIR/venv" ] && [ "$(readlink "$DIR/venv")" = "$DIR/runtime/python" ]; then return 0; fi
  rm -rf "$DIR/venv-old"
  [ -e "$DIR/venv" ] || [ -L "$DIR/venv" ] && mv "$DIR/venv" "$DIR/venv-old"
  ln -s "$DIR/runtime/python" "$DIR/venv"
  rm -rf "$DIR/venv-old" "$DIR/venv-new"
}

# rt_install <від %> <до %> — ставить середовище з інсталятора або завантажує з GitHub. 0 — готово.
rt_install() {
  local from=$1 to=$2 arch tgz tmp url total sz pct pid
  rt_wanted || return 1
  arch="$(rt_arch)"
  if rt_ok; then rt_link; p "$to" env "Середовище вже на місці"; return 0; fi
  tgz="$RES/runtime/svit-runtime-$RT_WANT-$arch.tar.gz"
  tmp="$DIR/runtime-download.tar.gz"
  if [ ! -f "$tgz" ]; then
    url="https://github.com/$RT_REPO/releases/download/runtime-$RT_WANT/svit-runtime-$RT_WANT-$arch.tar.gz"
    echo "середовище: завантажую $url" >> "$LOG"
    total=$(curl -sIL --connect-timeout 15 "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:"{v=$2} END{print v+0}')
    rm -f "$tmp"
    curl -fsSL --retry 3 --connect-timeout 20 "$url" -o "$tmp" >> "$LOG" 2>&1 &
    pid=$!
    while kill -0 $pid 2>/dev/null; do
      sz=$(stat -f%z "$tmp" 2>/dev/null || echo 0)
      if [ "${total:-0}" -gt 0 ]; then
        pct=$(( from + sz * (to - from - 4) / total )); [ $pct -gt $(( to - 4 )) ] && pct=$(( to - 4 ))
        p $pct env "Завантажую готове середовище · $(( sz / 1048576 )) з $(( total / 1048576 )) МБ"
      else
        p "$from" env "Завантажую готове середовище · $(( sz / 1048576 )) МБ"
      fi
      sleep 0.5
    done
    wait $pid || { echo "середовище: не завантажилось" >> "$LOG"; rm -f "$tmp"; return 1; }
    tgz="$tmp"
  fi
  p $(( to - 3 )) env "Розпаковую середовище"
  rm -rf "$DIR/runtime-new"; mkdir -p "$DIR/runtime-new"
  tar -xzf "$tgz" -C "$DIR/runtime-new" >> "$LOG" 2>&1 || { echo "середовище: архів пошкоджений" >> "$LOG"; rm -rf "$DIR/runtime-new" "$tmp"; return 1; }
  # файли з інтернету macOS позначає «на карантині» — інакше може не дати завантажити бібліотеки
  xattr -dr com.apple.quarantine "$DIR/runtime-new" 2>/dev/null
  p $(( to - 1 )) env "Перевіряю середовище"
  if ! rt_check "$DIR/runtime-new/python"; then
    echo "середовище: не запустилось на цьому Маку" >> "$LOG"; rm -rf "$DIR/runtime-new" "$tmp"; return 1
  fi
  rm -rf "$DIR/runtime-old"
  [ -d "$DIR/runtime" ] && mv "$DIR/runtime" "$DIR/runtime-old"
  mv "$DIR/runtime-new" "$DIR/runtime"
  rm -rf "$DIR/runtime-old" "$tmp"
  rt_link
  echo "середовище $RT_WANT ($arch): OK" >> "$LOG"
  p "$to" env "Середовище готове"
  return 0
}
