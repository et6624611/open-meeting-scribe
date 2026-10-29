# 在每台员工 Windows 电脑上以管理员身份运行（PowerShell）。
# 前提：与脚本同目录已有 oms-root-ca.crt（由服务器端 internal-ca 模式导出）。
# 效果：系统信任该企业根证书，浏览器访问 https://<服务器IP>:8443 不再告警。
$cert = Join-Path $PSScriptRoot "oms-root-ca.crt"
Import-Certificate -FilePath $cert -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Write-Host "企业根证书已信任。请重启浏览器后访问公司给您的 https 地址。"
