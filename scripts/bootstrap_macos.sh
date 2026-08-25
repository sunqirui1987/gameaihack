#!/usr/bin/env bash
# 把 doctor 缺的系统工具装到 ~/.local/bin，不走 Homebrew 的 OpenJDK 依赖链。
set -euo pipefail

BIN="${GAMEAIHACK_BIN:-$HOME/.local/bin}"
SHARE="${GAMEAIHACK_SHARE:-$HOME/.local/share/gameaihack}"
mkdir -p "$BIN" "$SHARE"

fetch() {
  local dest="$1"
  shift
  local u
  for u in "$@"; do
    echo "[bootstrap] GET $u"
    if curl -fL --retry 2 --connect-timeout 15 --max-time 240 -o "$dest" "$u"; then
      return 0
    fi
    rm -f "$dest"
  done
  return 1
}

gh() {
  local path="$1"
  echo "https://ghfast.top/https://github.com/${path}"
  echo "https://gitclone.com/github.com/${path}"
  echo "https://github.com/${path}"
}

if [[ ! -x "$BIN/apktool" ]]; then
  echo "[bootstrap] apktool"
  jar="$SHARE/apktool.jar"
  fetch "$jar" $(gh "iBotPeaches/Apktool/releases/download/v2.11.1/apktool_2.11.1.jar")
  cat >"$BIN/apktool" <<EOF
#!/bin/sh
exec java -jar "$jar" "\$@"
EOF
  chmod +x "$BIN/apktool"
fi

if [[ ! -x "$BIN/jadx" ]]; then
  echo "[bootstrap] jadx"
  zip="$SHARE/jadx.zip"
  fetch "$zip" $(gh "skylot/jadx/releases/download/v1.5.1/jadx-1.5.1.zip")
  rm -rf "$SHARE/jadx"
  mkdir -p "$SHARE/jadx"
  unzip -qo "$zip" -d "$SHARE/jadx"
  inner="$(find "$SHARE/jadx" -type f -name jadx | head -n 1)"
  if [[ -z "$inner" ]]; then
    echo "[bootstrap] jadx zip 里没有 bin/jadx" >&2
    exit 1
  fi
  chmod +x "$inner" "$SHARE/jadx"/bin/* 2>/dev/null || true
  ln -sfn "$inner" "$BIN/jadx"
  rm -f "$zip"
fi

if [[ ! -x "$BIN/Il2CppDumper" ]]; then
  echo "[bootstrap] Il2CppDumper"
  tmp="$(mktemp -d)"
  zip="$tmp/dumper.zip"
  fetch "$zip" $(gh "AndnixSH/Il2CppDumper/releases/download/v6.7.46/Il2CppDumper-net8-macos-x64-v6.7.46.zip")
  unzip -qo "$zip" -d "$tmp/out"
  exe="$(find "$tmp/out" -type f -name Il2CppDumper | head -n 1)"
  if [[ -z "$exe" ]]; then
    echo "[bootstrap] zip 里没有 Il2CppDumper" >&2
    find "$tmp/out" | head >&2
    exit 1
  fi
  chmod +x "$exe"
  # 自包含发布通常还要同目录的依赖，整目录拷走
  rm -rf "$SHARE/Il2CppDumper"
  mkdir -p "$SHARE/Il2CppDumper"
  cp -R "$tmp/out"/. "$SHARE/Il2CppDumper/"
  exe_name="$(basename "$exe")"
  rel="${exe#$tmp/out/}"
  ln -sfn "$SHARE/Il2CppDumper/$rel" "$BIN/Il2CppDumper"
  ln -sfn "$BIN/Il2CppDumper" "$BIN/il2cppdumper"
  xattr -dr com.apple.quarantine "$SHARE/Il2CppDumper" "$BIN/Il2CppDumper" 2>/dev/null || true
  rm -rf "$tmp"
fi

echo "[bootstrap] 已安装："
ls -l "$BIN/apktool" "$BIN/jadx" "$BIN/Il2CppDumper"
echo "[bootstrap] 若 doctor 仍 MISS，把 $BIN 加进 PATH："
echo "  export PATH=\"$BIN:\$PATH\""
