#!/bin/bash
# Збирає готове середовище Svit Editor (Python 3.11 + усі компоненти) для обох типів Маків.
# Запускається на GitHub (macos-14, Apple Silicon): arm64 ставимо звичайно і перевіряємо,
# x86_64 (Intel) — готовими пакетами під платформу Intel, перевіряємо через Rosetta, якщо вона є.
# Результат: dist-runtime/svit-runtime-<N>-arm64.tar.gz і svit-runtime-<N>-x86_64.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
RT="$(tr -d '[:space:]' < runtime/VERSION)"
OUT="dist-runtime"
WORK="$(mktemp -d)"
rm -rf "$OUT" && mkdir -p "$OUT"
REQ="runtime/requirements.txt"
PBS="astral-sh/python-build-standalone"

assets="$(gh release view -R "$PBS" --json assets --jq '.assets[].name')"
pick() {   # pick <arch>  → ім'я архіву Python 3.11 для цієї архітектури
  echo "$assets" | grep -E "^cpython-3\.11\.[0-9]+\+[0-9]+-$1-apple-darwin-install_only_stripped\.tar\.gz$" | sort -V | tail -1
}

fetch_python() {   # fetch_python <pbs-arch> <dir>
  local name; name="$(pick "$1")"
  [ -n "$name" ] || { echo "::error::Не знайшов Python 3.11 для $1"; exit 1; }
  echo "Python: $name"
  gh release download -R "$PBS" -p "$name" -D "$WORK/dl-$1" --clobber
  mkdir -p "$2"
  tar -xzf "$WORK/dl-$1/$name" -C "$2"     # усередині — тека python/
}

slim() {   # прибираємо зайве: тести, кеші, заголовки
  local root="$1"
  find "$root" -type d \( -name __pycache__ -o -name tests -o -name test \) -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$root/python/include" "$root/python/share" 2>/dev/null || true
  find "$root" -name "*.pyc" -delete 2>/dev/null || true
}

pack() {   # pack <arch> <dir>
  echo "$RT" > "$2/python/SVIT_RUNTIME"
  tar -C "$2" -czf "$OUT/svit-runtime-$RT-$1.tar.gz" python
  ls -la "$OUT/svit-runtime-$RT-$1.tar.gz"
}

SMOKE='import webview, faster_whisper, ctranslate2, anthropic, av, numpy, PIL, yt_dlp, certifi, tokenizers
try:
    import onnxruntime; print("onnxruntime", onnxruntime.__version__)
except Exception as e:
    print("onnxruntime: немає", e)
print("OK")'

# ---------------- Apple Silicon: звичайне встановлення + перевірка
A="$WORK/arm64"
fetch_python aarch64 "$A"
PYA="$A/python/bin/python3"
"$PYA" -m pip install --no-cache-dir --disable-pip-version-check --upgrade pip
"$PYA" -m pip install --no-cache-dir --disable-pip-version-check --prefer-binary -r "$REQ"
"$PYA" -c "$SMOKE"
"$PYA" -m pip freeze > "$OUT/requirements-arm64.lock"
slim "$A"
"$PYA" -c "import webview, faster_whisper; print('після чистки OK')"
pack arm64 "$A"

# ---------------- Intel: готові пакети під x86_64 (onnxruntime новіший за 1.23 для Intel не випускають)
X="$WORK/x86_64"
fetch_python x86_64 "$X"
SITE="$(ls -d "$X"/python/lib/python3.11/site-packages)"
# пакети, які існують лише як вихідний код (чистий Python) — збираємо в колеса заздалегідь
"$PYA" -m pip wheel --no-cache-dir --no-deps -w "$WORK/purewheels" proxy_tools bottle >/dev/null 2>&1 || true
echo "onnxruntime<1.24" > "$WORK/x86-constraints.txt"
"$PYA" -m pip install --no-cache-dir --disable-pip-version-check \
  --target "$SITE" --upgrade \
  --platform macosx_13_0_x86_64 --python-version 3.11 --implementation cp --abi cp311 \
  --only-binary=:all: --find-links "$WORK/purewheels" \
  -c "$WORK/x86-constraints.txt" -r "$REQ"
PYX="$X/python/bin/python3"
if arch -x86_64 /usr/bin/true 2>/dev/null; then
  arch -x86_64 "$PYX" -c "$SMOKE"
  arch -x86_64 "$PYX" -m pip freeze > "$OUT/requirements-x86_64.lock" || true
else
  echo "::warning::Rosetta недоступна — Intel-середовище не перевірене запуском"
fi
slim "$X"
pack x86_64 "$X"
ls -la "$OUT"
