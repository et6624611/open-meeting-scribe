#!/usr/bin/env bash
# internal-ca 模式证书引导（EP0-OPS）：
# 首次生成企业根 CA（ca/ca.key 私钥永不出服务器；ca/oms-root-ca.crt 发员工导入），
# 并为当前局域网 IP 签发含 IP SAN 的服务器证书到 proxy/certs/internal/。
# 为什么预签而非 Caddy 动态签发：员工以 IP 直接访问时浏览器 TLS 握手无 SNI，
# Caddy `tls internal` 无名可配 → 握手报 tlsv1 alert internal error（CI smoke 实测，
# 预签 IP SAN 证书 + 员工导入根证书为唯一既加密又无告警的内网形态）。
# 幂等：CA 复用不重发（员工已导入的根证书持续有效）；IP 变化/临期 30 天内自动重签。
set -euo pipefail
cd "$(dirname "$0")/.."   # deploy/private

LAN_IP="${1:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
: "${LAN_IP:=127.0.0.1}"
mkdir -p ca proxy/certs/internal

if [ ! -f ca/ca.key ]; then
  echo "internal-ca: 首次运行，生成企业根 CA"
  openssl req -x509 -newkey rsa:2048 -keyout ca/ca.key -out ca/oms-root-ca.crt \
    -days 825 -nodes -subj "/CN=OpenMeetingScribe Enterprise CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
  chmod 600 ca/ca.key
fi

need=1
if [ -f proxy/certs/internal/server.crt ]; then
  # -checkend N 返回 0 = 距过期还有超过 N 秒（非临期）
  if openssl x509 -in proxy/certs/internal/server.crt -noout -ext subjectAltName 2>/dev/null \
       | grep -Eq "IP Address:${LAN_IP}(,|$)" \
     && openssl verify -CAfile ca/oms-root-ca.crt proxy/certs/internal/server.crt >/dev/null 2>&1 \
     && openssl x509 -in proxy/certs/internal/server.crt -noout -checkend $((30 * 86400)); then
    need=0
  fi
fi

if [ "$need" = 1 ]; then
  openssl req -newkey rsa:2048 -keyout proxy/certs/internal/server.key \
    -out proxy/certs/internal/server.csr -nodes -subj "/CN=oms-internal"
  printf 'subjectAltName=IP:127.0.0.1,IP:%s\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n' "$LAN_IP" \
    > proxy/certs/internal/san.cnf
  openssl x509 -req -in proxy/certs/internal/server.csr \
    -CA ca/oms-root-ca.crt -CAkey ca/ca.key \
    -out proxy/certs/internal/server.crt -days 397 \
    -extfile proxy/certs/internal/san.cnf
  chmod 600 proxy/certs/internal/server.key
  rm -f proxy/certs/internal/server.csr proxy/certs/internal/san.cnf
  echo "internal-ca: 服务器证书已签发（SAN: 127.0.0.1, ${LAN_IP}；员工根证书在 ca/oms-root-ca.crt）"
else
  echo "internal-ca: 现有证书有效且覆盖当前 IP（${LAN_IP}），不重签"
fi
