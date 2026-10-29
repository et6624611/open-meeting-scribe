# 企业根证书导入（仅 TLS_MODE=internal-ca 时需要）

服务器开启"加密访问（内置 CA）"后，会在本目录生成 `oms-root-ca.crt`。
把它连同对应平台的导入脚本发给员工（或 IT 批量下发），每台终端执行一次即可：

- macOS：`sh import-root-ca.mac.sh`（需管理员密码）
- Windows：右键 `import-root-ca.win.ps1` → 使用管理员身份运行 PowerShell

说明（对用户向口径）：这只是让电脑认识"公司自己的服务器"，一次导入长期有效；
不导入也不影响 http 明文模式使用，但内网明文可被抓包，建议开启加密并统一导入证书。
`oms-root-ca.crt` 为公钥证书，不含私钥；私钥始终留在服务器容器卷内。
