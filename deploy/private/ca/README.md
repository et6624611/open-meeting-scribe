# 企业根证书导入（仅 TLS_MODE=internal-ca 时需要）

开启"加密访问（内置 CA）"后，安装脚本会在本目录生成 `oms-root-ca.crt`，
并为服务器当前局域网 IP 自动签发证书（放在 `proxy/certs/internal/`，IP 变化或临期时重跑安装脚本自动重签）。
把 `oms-root-ca.crt` 连同对应平台的导入脚本发给员工（或 IT 批量下发），每台终端执行一次：

- macOS：`sh import-root-ca.mac.sh`（需管理员密码）
- Windows：右键 `import-root-ca.win.ps1` → 使用管理员身份运行 PowerShell

说明（对用户向口径）：
- 这只是让电脑认识"公司自己的服务器"，一次导入长期有效；根证书重签才会失效（CA 私钥不轮换则不重签）。
- 不导入不影响 http 明文模式使用，但内网明文可被抓包，建议开启加密并统一导入证书。
- 本目录 `ca.key` 是企业根私钥：**只留在服务器上，永远不发给任何人**；
  `oms-root-ca.crt` 为公钥证书，可安全分发。
