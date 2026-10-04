#!/usr/bin/env bash
# build/macos_sign_notarize.sh — mac 主应用签名/公证/DMG 链路（WP-G G-7，D-G4 L1 层）
# 【状态：DEFERRED，已移出 v10】项目方 2026-09-24 裁决「暂时不考虑 Apple 开发者账号
# 与凭据」。本脚本保留备查，不再推进、不催凭据。发布材料口径硬约束：不得出现
# 「macOS 一键安装」字样，只可写「macOS 支持应用内一键安装本地引擎组件」。
#
# 职责：Developer ID codesign（hardened runtime）→ .dmg 组装 → notarytool 公证 → staple。
#
# 凭据（GitHub Secrets，由 workflow 注入环境变量；缺任一组 → dry-run 跳过签名/公证，
# 只产未签名 .dmg + ZIP，并显式打印 DRY-RUN 标记——「链路写好、凭据缺失时 dry-run 跳过」
# 是 G-7 在 Apple 凭据到位前的唯一允许状态，不得声称 mac 一键安装已完成）：
#   APPLE_CERT_P12_B64        Developer ID Application 证书 .p12（base64）
#   APPLE_CERT_PASSWORD       .p12 密码
#   APPLE_SIGNING_IDENTITY    签名身份（如 "Developer ID Application: Xxx (TEAMID)"）
#   APPLE_API_ISSUER          notarytool App Store Connect API Issuer ID
#   APPLE_API_KEY_ID          notarytool API Key ID
#   APPLE_API_KEY_B64         notarytool .p8 私钥（base64）
#
# 用法：
#   build/macos_sign_notarize.sh <分发目录 dist/OpenMeetingScribe-macOS> <输出目录 dist>
set -euo pipefail

DIST_DIR="${1:?用法: macos_sign_notarize.sh <分发目录> <输出目录>}"
OUT_DIR="${2:?缺少输出目录}"
APP_PATH="$DIST_DIR/OpenMeetingScribe.app"
ENTITLEMENTS="$(cd "$(dirname "$0")" && pwd)/entitlements.mac.plist"
DRY_RUN=0

log()  { echo "[SIGN] $*"; }
fail() { echo "[SIGN] ERROR: $*" >&2; exit 1; }

[ -d "$APP_PATH" ] || fail "未找到 $APP_PATH"
mkdir -p "$OUT_DIR"
DMG_PATH="$OUT_DIR/OpenMeetingScribe-macOS.dmg"

# ── 凭据检查：缺失 → dry-run（不中断构建，产出未签名 dmg/zip） ──
SIGN_VARS=("APPLE_CERT_P12_B64" "APPLE_CERT_PASSWORD" "APPLE_SIGNING_IDENTITY")
NOTARY_VARS=("APPLE_API_ISSUER" "APPLE_API_KEY_ID" "APPLE_API_KEY_B64")
missing=()
for v in "${SIGN_VARS[@]}" "${NOTARY_VARS[@]}"; do
  [ -n "${!v:-}" ] || missing+=("$v")
done
if [ ${#missing[@]} -gt 0 ]; then
  DRY_RUN=1
  log "DRY-RUN：凭据缺失（${missing[*]}）→ 跳过 codesign/notarization。"
  log "DRY-RUN：产出为未签名 .dmg——用户会撞 Gatekeeper「已损坏/无法验证开发者」，"
  log "DRY-RUN：不得对外声称 mac 一键安装已支持（G-7 blocked-on-credentials）。"
fi

KEYCHAIN_NAME="oms-signing.keychain-db"
KEYCHAIN_PATH="$HOME/Library/Keychains/$KEYCHAIN_NAME"
API_KEY_DIR=""

cleanup() {
  if [ "$DRY_RUN" -eq 0 ]; then
    security delete-keychain "$KEYCHAIN_PATH" 2>/dev/null || true
    [ -n "$API_KEY_DIR" ] && rm -rf "$API_KEY_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [ "$DRY_RUN" -eq 0 ]; then
  # ── 1) 导入证书到临时 keychain ──
  log "导入 Developer ID 证书到临时 keychain…"
  CERT_P12="$(mktemp -t oms_cert).p12"
  echo "$APPLE_CERT_P12_B64" | base64 --decode > "$CERT_P12"
  security create-keychain -p "" "$KEYCHAIN_NAME"
  security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
  security unlock-keychain -p "" "$KEYCHAIN_PATH"
  security import "$CERT_P12" -P "$APPLE_CERT_PASSWORD" -A -t cert -f pkcs12 -k "$KEYCHAIN_PATH"
  security set-key-partition-list -S apple-tool:,apple: -s -k "" "$KEYCHAIN_PATH" >/dev/null
  security list-keychain -d user -s "$KEYCHAIN_PATH" login.keychain
  rm -f "$CERT_P12"
  security find-identity -v "$KEYCHAIN_PATH" | grep -q "Developer ID Application" \
    || fail "keychain 中未找到 Developer ID Application 身份"

  # ── 2) codesign：先内层（frameworks/dylibs/ffmpeg），后 .app 整体（hardened runtime） ──
  log "codesign（identity=$APPLE_SIGNING_IDENTITY）…"
  sign_inner() {
    local target="$1"
    find "$target" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 |
      while IFS= read -r -d '' f; do
        codesign --force --timestamp --options runtime -s "$APPLE_SIGNING_IDENTITY" "$f" 2>/dev/null || true
      done
  }
  [ -d "$DIST_DIR/ffmpeg" ] && sign_inner "$DIST_DIR/ffmpeg" || true
  if [ -d "$APP_PATH/Contents/Frameworks" ]; then
    for fw in "$APP_PATH/Contents/Frameworks"/*.framework "$APP_PATH/Contents/Frameworks"/*.dylib; do
      [ -e "$fw" ] || continue
      codesign --force --deep --timestamp --options runtime -s "$APPLE_SIGNING_IDENTITY" "$fw"
    done
  fi
  # .app 内的可执行二进制（PyInstaller onedir 的 _internal 动态库量大，逐个签）
  find "$APP_PATH" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 |
    while IFS= read -r -d '' f; do
      codesign --force --timestamp --options runtime -s "$APPLE_SIGNING_IDENTITY" "$f"
    done
  codesign --force --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" \
    -s "$APPLE_SIGNING_IDENTITY" "$APP_PATH"
  codesign --verify --deep --strict --verbose=2 "$APP_PATH" || fail ".app 签名校验失败"
  log ".app 签名完成 ✓"

  # ── 3) notarytool 凭据（.p8） ──
  API_KEY_DIR="$(mktemp -d -t oms_notary)"
  API_P8="$API_KEY_DIR/AuthKey_${APPLE_API_KEY_ID}.p8"
  echo "$APPLE_API_KEY_B64" | base64 --decode > "$API_P8"
  chmod 600 "$API_P8"
fi

# ── 4) .dmg 组装（dry-run 也产 dmg：验证 hdiutil 链路） ──
log "组装 .dmg…"
rm -f "$DMG_PATH"
STAGING="$(mktemp -d -t oms_dmg)"
cp -R "$APP_PATH" "$STAGING/"
[ -f "$DIST_DIR/启动会议助手.command" ] && cp "$DIST_DIR/启动会议助手.command" "$STAGING/" || true
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "OpenMeetingScribe" -srcfolder "$STAGING" -ov -format UDZO "$DMG_PATH" >/dev/null
rm -rf "$STAGING"
log ".dmg 就位: $DMG_PATH（$(du -sh "$DMG_PATH" | cut -f1)）"

if [ "$DRY_RUN" -eq 0 ]; then
  # ── 5) dmg 签名 + 公证 + staple ──
  codesign --force --timestamp -s "$APPLE_SIGNING_IDENTITY" "$DMG_PATH"
  log "提交公证（notarytool --wait，通常 2–10 分钟）…"
  xcrun notarytool submit "$DMG_PATH" \
    --key "$API_P8" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" \
    --wait --output-format json > notary-result.json || {
      cat notary-result.json 2>/dev/null || true
      fail "notarytool 提交失败"
    }
  STATUS="$(python3 -c "import json;print(json.load(open('notary-result.json')).get('status',''))" 2>/dev/null || echo "")"
  if [ "$STATUS" != "Accepted" ]; then
    SUB_ID="$(python3 -c "import json;print(json.load(open('notary-result.json')).get('id',''))" 2>/dev/null || echo "")"
    xcrun notarytool log "$SUB_ID" --key "$API_P8" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" || true
    fail "公证未通过（status=$STATUS），日志已打印"
  fi
  xcrun stapler staple "$DMG_PATH" || fail "staple 失败"
  xcrun stapler staple "$APP_PATH" || true
  # Gatekeeper 评估（全新机器双击安装的 CI 侧等价验证）
  spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG_PATH" || true
  log "公证通过并已 staple ✓（L1 达标形态）"
  echo "SIGN_RESULT=signed-notarized" >> "${GITHUB_ENV:-/dev/null}"
else
  echo "SIGN_RESULT=dry-run-unsigned" >> "${GITHUB_ENV:-/dev/null}"
fi
