#!/usr/bin/env bash
# OpenMeetingScribe 企业版 P0 — 升级与回滚（EP0-OPS）
# 用法：
#   ./oms-upgrade.sh <新镜像.tar>   # 强制备份 → 载入 → 新镜像执行迁移 → 滚动替换 → 健康门禁
#   ./oms-upgrade.sh --rollback     # 镜像切回上一版本（P0 schema additive-only，旧镜像可读新库）
# 数据恢复（灾难场景，非日常）：停服后将 backups/instance_<时间>.db 与 snap_<时间>.tar.gz
#   解包覆盖 data/ 对应文件，再 ./oms-offline-install.sh 拉起。
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "错误：请先执行 oms-offline-install.sh 完成安装"; exit 1; }
set -a; source .env; set +a

PROFILE_ARGS=()
if [ "${OMS_TLS_MODE:-off}" != "off" ]; then
  PROFILE_ARGS+=(--profile tls)
  export OMS_PUBLIC_BIND=127.0.0.1
fi

compose() { docker compose "${PROFILE_ARGS[@]}" "$@"; }

if [ "${1:-}" = "--rollback" ]; then
  [ -f .oms_version_prev ] || { echo "错误：没有上一版本记录，无法回滚"; exit 1; }
  PREV=$(cat .oms_version_prev)
  if ! docker image inspect "$PREV" >/dev/null 2>&1; then
    prev_tar=$(ls images/*.tar 2>/dev/null | grep -F "${PREV##*:}" | head -1 || true)
    [ -n "$prev_tar" ] || { echo "错误：本机没有镜像 $PREV，且 images/ 无对应离线 tar（发布包请保留最近 2 版 tar）"; exit 1; }
    docker load -i "$prev_tar" >/dev/null
  fi
  sed -i "s/^OMS_VERSION=.*/OMS_VERSION=${PREV##*:}/" .env
  compose up -d
  echo "已回滚到上一版本镜像：$PREV（数据未动；如需恢复升级前数据快照见本脚本头部注释）"
  exit 0
fi

[ -f "${1:-}" ] || { echo "用法：$0 <新镜像.tar> | --rollback"; exit 1; }

echo "[1/4] 强制升级前备份（RPO=0 的还原点）…"
compose run --rm oms-backup python /opt/oms-backup.py --once

echo "[2/4] 载入新镜像…"
NEW_LOADED=$(docker load -i "$1" | sed -n 's/^Loaded image: //p' | head -1)
[ -n "$NEW_LOADED" ] || { echo "错误：镜像载入失败"; exit 1; }

echo "[3/4] 用新镜像执行数据库迁移（幂等/事务化，失败即中止不切流）…"
docker run --rm \
  -e OMS_DATA_ROOT=/app/data \
  -e REQUIRE_AUTH=true \
  -v "$PWD/data:/app/data" \
  "$NEW_LOADED" python -m app.db migrate

echo "[4/4] 切换版本 ${OMS_VERSION} -> ${NEW_LOADED##*:} 并滚动替换…"
echo "open-meeting-scribe:${OMS_VERSION}" > .oms_version_prev
sed -i "s/^OMS_VERSION=.*/OMS_VERSION=${NEW_LOADED##*:}/" .env
compose up -d

ok=0
for _ in $(seq 1 20); do
  status=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$(compose ps -q oms-app)" 2>/dev/null || echo starting)
  if [ "$status" = healthy ]; then ok=$((ok + 1)); else ok=0; fi
  [ "$ok" -ge 3 ] && break
  sleep 3
done
if [ "$ok" -ge 3 ]; then
  echo "升级完成：$NEW_LOADED（升级前备份已落 backups/，回滚请用 $0 --rollback）"
else
  echo "错误：健康门禁未通过，自动回滚到上一版本…"
  "$0" --rollback
  exit 1
fi
