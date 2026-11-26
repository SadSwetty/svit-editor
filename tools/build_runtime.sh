#!/bin/bash
# Збирає готове середовище Svit Editor (Python 3.11 + усі компоненти) для обох типів Маків.
# Працює на будь-якій машині GitHub (Linux теж): Python для Мака береться готовий
# (astral-sh/python-build-standalone), компоненти — готовими пакетами саме під macOS
# (pip --platform), нічого не компілюється. На Мак-машині середовище ще й пробно запускається.
# Результат: dist-runtime/svit-runtime-<N>-arm64.tar.gz і svit-runtime-<N>-x86_64.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
RT="$(tr -d '[:space:]' < runtime/VERSION)"
OUT="dist-runtime"
WORK="$(mktemp -d)"
rm -rf "$OUT" && mkdir -p "$OUT"
REQ="runtime/requirements.txt"
PBS="astral-sh/python-build-standalone"
HOSTPY="${HOSTPY:-python3}"

# pywebview тягне pyobjc лише «якщо це Мак» — на Linux pip цю умову не бачить, тож додаємо явно
MAC_EXTRA="pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-WebKit pyobjc-framework-Security pyobjc-framework-UniformTypeIdentifiers"

assets="$(gh release view -R "$PBS" --json assets --jq '.assets[].name')"
pick() {
  echo "$assets" | grep -E "^cpython-3\.11\.[0-9]+\+[0-9]+-$1-apple-darwin-install_only_stripped\.tar\.gz$" | sort -V | tail -1
}

# пакети, що існують лише як вихідний код чистого Python, — заздалегідь у колеса
"$HOSTPY" -m pip wheel --no-cache-dir --no-deps -w "$WORK/purewheels" proxy_tools bottle >/dev/null

build() {   # build <pbs-arch> <our-arch> <pip-platform> <constraints>
  local parch=$1 arch=$2 plat=$3 cons=$4 name dir site
  name="$(pick "$parch")"
  [ -n "$name" ] || { echo "::error::Не знайшов Python 3.11 для $parch"; exit 1; }
  echo "== $arch: $name"
  gh release download -R "$PBS" -p "$name" -D "$WORK/dl" --clobber
  dir="$WORK/$arch"; mkdir -p "$dir"
  tar -xzf "$WORK/dl/$name" -C "$dir"
  site="$(ls -d "$dir"/python/lib/python3.11/site-packages)"
  printf '%s\n' $cons > "$WORK/cons-$arch.txt"
  local PIPX=("$HOSTPY" -m pip install --no-cache-dir --disable-pip-version-check --upgrade
    --target "$site" --platform "$plat" --python-version 3.11 --implementation cp --abi cp311
    --only-binary=:all: --find-links "$WORK/purewheels" -c "$WORK/cons-$arch.txt")
  "${PIPX[@]}" -r "$REQ" $MAC_EXTRA
  # необов'язкові: без них Svit працює (фільтр тиші в розпізнаванні мови, маскування під браузер для TikTok)
  for opt in onnxruntime curl_cffi; do
    "${PIPX[@]}" "$opt" || echo "::warning::$arch: $opt недоступний — середовище буде без нього"
  done
  "$HOSTPY" -m pip list --path "$site" --format freeze > "$OUT/requirements-$arch.lock"
  # прибираємо зайве
  find "$dir" -type d \( -name __pycache__ -o -name tests -o -name test \) -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$dir/python/include" "$dir/python/share" "$site/bin" 2>/dev/null || true
  echo "$RT" > "$dir/python/SVIT_RUNTIME"
  # пробний запуск, якщо ця машина — Мак потрібної архітектури
  if [ "$(uname -s)" = "Darwin" ] && { [ "$(uname -m)" = "$arch" ] || [ "$arch" = "x86_64" ]; }; then
    local run="$dir/python/bin/python3"; [ "$(uname -m)" != "$arch" ] && run="arch -x86_64 $run"
    $run -c "import webview, faster_whisper, ctranslate2, anthropic, av, numpy, PIL, yt_dlp; print('OK $arch')" \
      || echo "::warning::$arch: пробний запуск не вдався"
  fi
  tar -C "$dir" -czf "$OUT/svit-runtime-$RT-$arch.tar.gz" python
  ls -la "$OUT/svit-runtime-$RT-$arch.tar.gz"
}

# Apple Silicon
# DaVinci Resolve 21 потребує macOS 15, тож орієнтуємось на macOS 15
build aarch64 arm64 macosx_15_0_arm64 ""
# Intel: onnxruntime новіший за 1.23 для Intel-Маків не випускають
build x86_64 x86_64 macosx_15_0_x86_64 "onnxruntime<1.24"
ls -la "$OUT"
