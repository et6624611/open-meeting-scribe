#!/usr/bin/env bash
# OpenMeetingScribe 企业版 P0 — 内网私有化一键安装（幂等：重复执行=按当前 .env 收敛）
# 用法：
#   ./oms-offline-install.sh            # 安装或调整配置
#   ./oms-offline-install.sh --build    # 从仓库源码构建镜像（联网/开发场景）
# 离线交付：将发布包中的 images/*.tar 放在本目录 images/ 下再执行本脚本。
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null 2>&1 || { echo "错误：未安装 docker，请先安装 Docker Engine（README-admin.md §1）"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "错误：需要 docker compose v2 插件"; exit 1; }

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已生成默认配置 .env（当前为出厂 HTTP 模式）"
fi
set -a; source .env; set +a

PROFILE_ARGS=()
if [ "${OMS_TLS_MODE:-off}" != "off" ]; then
  PROFILE_ARGS+=(--profile tls)
  export OMS_PUBLIC_BIND=127.0.0.1   # 开加密后应用端口收敛回环，员工只经 https 代理访问
fi

if [ "${1:-}" = "--build" ]; then
  docker build -t "open-meeting-scribe:${OMS_VERSION}" ../..
elif ! docker image inspect "open-meeting-scribe:${OMS_VERSION}" >/dev/null 2>&1; then
  loaded=0
  for f in images/*.tar; do
    [ -e "$f" ] || continue
    docker load -i "$f"
    loaded=1
  done
  if [ "$loaded" != 1 ]; then
    echo "错误：本机没有镜像 open-meeting-scribe:${OMS_VERSION}，且 images/ 下没有离线镜像 tar。"
    echo "请把企业版发布包中的 images/*.tar 放到 images/ 目录后重跑，或使用 --build 从源码构建。"
    exit 1
  fi
fi

docker compose "${PROFILE_ARGS[@]}" up -d

echo "等待服务健康（/healthz）…"
ok=0
for _ in $(seq 1 30); do
  status=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$(docker compose "${PROFILE_ARGS[@]}" ps -q oms-app)" 2>/dev/null || echo starting)
  if [ "$status" = healthy ]; then ok=1; break; fi
  sleep 2
done
[ "$ok" = 1 ] || { echo "错误：探活超时（/healthz），请查看日志：docker compose logs oms-app"; exit 1; }

lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}'); : "${lan_ip:=127.0.0.1}"

if [ "${OMS_TLS_MODE:-off}" = "internal-ca" ]; then
  mkdir -p ca
  if docker compose "${PROFILE_ARGS[@]}" cp oms-proxy:/data/caddy/pki/authorities/local/root.crt ca/oms-root-ca.crt 2>/dev/null; then
    echo "已导出企业根证书：ca/oms-root-ca.crt（发给员工或用 ca/ 下导入脚本批量信任）"
  fi
fi

echo ""
echo "=============================================="
echo "  安装完成。"
echo ""
echo "  第一步（仅管理员，在本台服务器上）："
echo "    用服务器本机浏览器打开 http://localhost:${OMS_PORT} 完成初始化向导"
echo "    （未初始化时仅本机回环可进入初始化，防止对外抢先注册管理员）"
echo ""
if [ "${OMS_TLS_MODE:-off}" = "off" ]; then
  echo "  员工访问地址：http://${lan_ip}:${OMS_PORT}"
  echo "  当前为内网明文模式：同事的登录密码与会议文字在内网可被抓包。"
  echo "  建议管理员开启加密访问：编辑 .env 将 OMS_TLS_MODE 改为 internal-ca 后重跑本脚本。"
else
  echo "  员工访问地址：https://${lan_ip}:${OMS_TLS_PORT}"
  echo "  员工终端需先信任企业根证书（ca/oms-root-ca.crt + 同目录导入脚本，或 IT 批量下发）。"
fi
echo "  企业数据自动备份在本目录 backups/（保留 ${OMS_BACKUP_KEEP_DAYS} 天，永不出外网）。"
echo "=============================================="
