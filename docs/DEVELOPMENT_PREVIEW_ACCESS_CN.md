# 中国合规包开发预览入口说明

## 目的

本说明用于恢复和核对隔离开发实例的浏览器访问入口。它只描述通用访问方式，不保存服务器密码、私钥内容、客户数据或生产地址。

## 推荐结构

开发 Odoo 实例应只监听服务器回环地址：

```text
http_interface = 127.0.0.1
http_port = 18070
```

本机浏览器访问时，通过 SSH 本地转发暴露到本机端口：

```powershell
ssh -i C:\path\to\id_ed25519 `
  -N `
  -L 18069:127.0.0.1:18070 `
  user@example-server
```

然后在本机访问：

```text
http://127.0.0.1:18069/web/login?db=target_database
```

## 检查项

如果本机访问失败，按顺序检查：

1. 本机 `18069` 是否正在监听。
2. SSH 转发进程是否仍在运行。
3. 服务器上 Odoo 开发实例是否正在监听 `127.0.0.1:18070`。
4. Odoo 配置中的 `dbfilter` 是否允许目标数据库。
5. 目标数据库是否已安装或升级到当前交付版本。

## 验证命令

本机检查：

```powershell
Get-NetTCPConnection -LocalPort 18069 -ErrorAction SilentlyContinue
Invoke-WebRequest `
  -Uri "http://127.0.0.1:18069/web/login?db=target_database" `
  -UseBasicParsing `
  -TimeoutSec 20
```

服务器检查：

```bash
ss -ltnp | grep -E '18070|8069'
ps -ef | grep -E 'odoo.*odoo-dev.conf' | grep -v grep
```

开发预览入口只是人工查看和演示入口，不替代 delivery acceptance、manifest、bundle metadata 或 artifact verifier。
