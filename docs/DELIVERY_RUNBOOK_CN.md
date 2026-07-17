# Sdoo 中国财税合规包交付运行手册

## 适用范围

本手册用于交付、部署和验收 Odoo 19 中国财税合规插件体系：

- `sudo_country_pack_cn`：中国财税合规主国家包。
- `sudo_country_pack_cn_einvoice_xbrl`：可选的电子发票 XBRL 解析插件。
- `tools/`：交付包构建、验收、清单生成和交付物一致性核验工具。
- `docs/samples/`：受控外部税务数据契约样例。

本手册不包含生产服务器地址、私钥、口令、客户数据、数据库备份或 filestore。

## 交付物

标准交付至少包含四类文件：

1. 确定性 bundle：`sdoo-cn-compliance-delivery.tgz`
2. bundle 元数据：`sdoo-cn-compliance-delivery.bundle.json`
3. delivery manifest：`cn_delivery_manifest.json`
4. acceptance summary：`cn_delivery_acceptance_summary.json`

交付前必须使用 `verify_cn_delivery_artifacts.py` 证明上述交付物互相一致。

## 构建交付包

在代码仓库根目录执行：

```powershell
python tools\build_cn_delivery_bundle.py `
  --output dist\sdoo-cn-compliance-delivery.tgz `
  --metadata dist\sdoo-cn-compliance-delivery.bundle.json
```

构建器会使用与 delivery manifest 相同的文件清单，并规范化 tar.gz 内的
ownership、permissions 和 mtime。相同源文件重复构建时，bundle SHA-256 应保持一致。

## 部署到 Odoo

在目标服务器上准备一个隔离目录，例如 `/opt/sdoo-cn-compliance-delivery`，并解压 bundle：

```bash
mkdir -p /opt/sdoo-cn-compliance-delivery
tar -xzf sdoo-cn-compliance-delivery.tgz -C /opt/sdoo-cn-compliance-delivery
```

将以下目录加入 Odoo `addons_path`：

```text
/opt/sdoo-cn-compliance-delivery/addons
```

如果启用可选 XBRL 解析插件，生产 Python 环境还必须按受控变更流程安装并锁定：

```text
arelle-release==2.42.1
```

## 安装或升级

全新安装主国家包：

```bash
python /path/to/odoo-bin \
  -c /path/to/odoo.conf \
  -d target_database \
  -i sudo_country_pack_cn \
  --stop-after-init
```

升级主国家包：

```bash
python /path/to/odoo-bin \
  -c /path/to/odoo.conf \
  -d target_database \
  -u sudo_country_pack_cn \
  --stop-after-init
```

如需启用 XBRL 插件，在确认依赖已安装后再安装：

```bash
python /path/to/odoo-bin \
  -c /path/to/odoo.conf \
  -d target_database \
  -i sudo_country_pack_cn_einvoice_xbrl \
  --stop-after-init
```

## 验收

快速核心闭环验收：

```bash
python tools/run_cn_delivery_acceptance.py \
  --profile core \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database acceptance_database \
  --install \
  --logfile /tmp/cn_core_acceptance.log \
  --write-manifest /tmp/cn_delivery_manifest.json \
  --write-summary /tmp/cn_delivery_acceptance_summary.json
```

发布级全量验收：

```bash
python tools/run_cn_delivery_acceptance.py \
  --profile full \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database acceptance_database \
  --install \
  --logfile /tmp/cn_full_acceptance.log \
  --write-manifest /tmp/cn_delivery_manifest.json \
  --write-summary /tmp/cn_delivery_acceptance_summary.json
```

验收通过标准：

- 本地静态检查通过。
- Python 编译和关键 XML 解析通过。
- `full` profile 的 tax-data/XBRL 契约测试通过。
- Odoo runtime 日志为 `0 failed / 0 errors`。
- acceptance summary 的 `result` 为 `passed`。

## 交付物核验

```bash
python tools/verify_cn_delivery_artifacts.py \
  --bundle sdoo-cn-compliance-delivery.tgz \
  --bundle-metadata sdoo-cn-compliance-delivery.bundle.json \
  --manifest cn_delivery_manifest.json \
  --summary cn_delivery_acceptance_summary.json
```

核验通过代表：

- bundle metadata、manifest 和 summary 的版本一致。
- bundle SHA-256 与实际文件一致。
- manifest 与 bundle metadata 的逐文件 SHA-256 一致。
- summary 引用的 manifest 摘要一致。
- 如 summary 含 Odoo runtime 日志，则日志结果为 `0 failed / 0 errors`。

## 生产注意事项

- 本插件不会自动发布未经治理、审批和专业签核的中国财税规则。
- 数据不足必须作为限制和下一步动作展示，不得解释为合规通过。
- AI 只提供受控解释和操作引导，不替代规则引擎或中国财税专业判断。
- 正式业务库部署前应先在隔离副本完成安装、升级、权限、多公司和真实数据只读验收。
- 生产数据库、filestore、客户附件和密钥不得进入 Git 或交付包。
