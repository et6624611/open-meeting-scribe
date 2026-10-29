#!/bin/sh
# 在每台员工 Mac 上运行（或由 IT 通过 MDM 批量下发）。
# 前提：与本 README 同目录已有 oms-root-ca.crt（由服务器端 internal-ca 模式导出）。
# 效果：macOS 系统信任该企业根证书，浏览器访问 https://<服务器IP>:8443 不再告警。
set -eu
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain "$(dirname "$0")/oms-root-ca.crt"
echo "企业根证书已信任。请重启浏览器后访问公司给您的 https 地址。"
