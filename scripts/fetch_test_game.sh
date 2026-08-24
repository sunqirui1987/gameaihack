#!/usr/bin/env bash
# 下载用于管线验收的开源游戏 APK（Google Play 同款 Unciv，来源 GitHub Releases / F-Droid）。
# 不从 Play 抓取商业包，不需要 Google 账号。
set -euo pipefail
# 沿用环境变量；未设置时不强制代理。需要代理时：
#   export https_proxy=http://127.0.0.1:9090
DEST="${1:-samples/unciv.apk}"
mkdir -p "$(dirname "$DEST")"
URLS=(
  "https://github.com/yairm210/Unciv/releases/download/4.21.11/Unciv-signed.apk"
  "https://mirror.eu.ossplanet.net/fdroid/repo/com.unciv.app_1248.apk"
)
for u in "${URLS[@]}"; do
  echo "try $u"
  if curl -L --fail --retry 2 --max-time 180 -o "$DEST" "$u"; then
    if unzip -t "$DEST" >/dev/null 2>&1; then
      ls -lh "$DEST"
      exit 0
    fi
  fi
done
echo "下载失败。请浏览器打开 https://github.com/yairm210/Unciv/releases 手动保存 Unciv-signed.apk 到 $DEST" >&2
exit 1
