# Sdoo 中国财税合规包交付运行手册

## 适用范围

本手册用于交付、部署、验收和签核 Odoo 19 中国财税合规插件体系：

- `sudo_country_pack_cn`：中国财税合规主国家包。
- `sudo_country_pack_cn_einvoice_xbrl`：可选电子发票 XBRL 解析子模块。
- `tools/`：交付包构建、自动验收、交付清单、状态汇总、签核包和签核证据校验工具。
- `docs/samples/`：受控外部税务数据契约和签核证据样例。

本手册不包含生产服务器地址、私钥、口令、客户数据、数据库备份或 filestore。上述材料不得进入 Git 或交付包。

## 标准交付物

标准交付至少包含以下文件：

1. `sdoo-cn-compliance-delivery.tgz`：确定性交付包。
2. `sdoo-cn-compliance-delivery.bundle.json`：交付包元数据，包含版本、源提交和文件哈希。
3. `cn_delivery_manifest.json`：交付清单。
4. `cn_delivery_acceptance_summary.json`：自动验收摘要。
5. `cn_delivery_status.json` / `cn_delivery_status.md`：业务可验收状态汇总。
6. `cn_signoff_packet.json` / `cn_signoff_packet.md`：生产签核行动包。
7. `cn_signoff_validation.json`：只有完成真人签核证据校验后才生成。

交付前必须使用 `verify_cn_delivery_artifacts.py` 证明 bundle、metadata、manifest 和 summary 互相一致。

## 构建交付包

在代码仓库根目录执行：

```powershell
python tools\build_cn_delivery_bundle.py `
  --output dist\sdoo-cn-compliance-delivery.tgz `
  --metadata dist\sdoo-cn-compliance-delivery.bundle.json
```

构建器会使用与 delivery manifest 相同的文件清单，并规范化 tar.gz 内的 ownership、permissions 和 mtime。相同源文件重复构建时，bundle SHA-256 应保持一致。

## 部署到 Odoo

在目标服务器准备隔离目录，例如 `/opt/sdoo-cn-compliance-delivery`，并解压 bundle：

```bash
mkdir -p /opt/sdoo-cn-compliance-delivery
tar -xzf sdoo-cn-compliance-delivery.tgz -C /opt/sdoo-cn-compliance-delivery
```

将以下目录加入 Odoo `addons_path`：

```text
/opt/sdoo-cn-compliance-delivery/addons
```

如果启用可选 XBRL 解析子模块，生产 Python 环境还必须按受控变更流程安装并锁定：

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

如需启用 XBRL 子模块，在确认依赖已安装后再执行：

```bash
python /path/to/odoo-bin \
  -c /path/to/odoo.conf \
  -d target_database \
  -i sudo_country_pack_cn_einvoice_xbrl \
  --stop-after-init
```

## 自动验收

核心闭环验收：

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
- `full` profile 的 tax-data、XBRL、签核和交付工具测试通过。
- Odoo runtime 日志为 `0 failed / 0 errors`。
- acceptance summary 的 `result` 为 `passed`。

## 交付物一致性校验

```bash
python tools/verify_cn_delivery_artifacts.py \
  --bundle sdoo-cn-compliance-delivery.tgz \
  --bundle-metadata sdoo-cn-compliance-delivery.bundle.json \
  --manifest cn_delivery_manifest.json \
  --summary cn_delivery_acceptance_summary.json
```

校验通过代表：

- bundle metadata、manifest 和 summary 的版本一致。
- bundle SHA-256 与实际文件一致。
- manifest 与 bundle metadata 的逐文件 SHA-256 一致。
- summary 引用的 manifest 摘要一致。
- 如果 summary 包含 Odoo runtime 日志，则日志结果为 `0 failed / 0 errors`。

## 预览库和真实数据门禁

在隔离预览库安装后，应至少执行以下检查：

```bash
python tools/check_cn_preview_health.py \
  --url "http://127.0.0.1:18070/web/login?db=target_database" \
  --json-output /tmp/cn_preview_health.json

python tools/check_cn_preview_module.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --expected-version 19.0.1.130.0 \
  --json-output /tmp/cn_preview_module.json

python tools/check_cn_real_data_closed_loop.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --expected-version 19.0.1.130.0 \
  --require-demo-ready \
  --require-closed-loop-evidence \
  --json-output /tmp/cn_real_data_closed_loop.json
```

这些检查只证明预览库可打开、模块版本正确、真实数据闭环证据满足当前业务验收门槛。它们不等于生产签核完成。

## 状态汇总

```bash
python tools/summarize_cn_delivery_status.py \
  --manifest /tmp/cn_delivery_manifest.json \
  --summary /tmp/cn_delivery_acceptance_summary.json \
  --bundle-metadata /tmp/sdoo-cn-compliance-delivery.bundle.json \
  --preview-url "http://127.0.0.1:18070/web/login?db=target_database" \
  --preview-health /tmp/cn_preview_health.json \
  --preview-module /tmp/cn_preview_module.json \
  --real-data-closed-loop /tmp/cn_real_data_closed_loop.json \
  --json-output /tmp/cn_delivery_status.json \
  --markdown-output /tmp/cn_delivery_status.md \
  --require-business-uat-ready \
  --require-source-control-clean
```

当所有自动验收、预览库检查、真实数据闭环检查和源码状态检查通过时，状态汇总可以显示 `business_uat_ready=true`。这表示可以进入业务验收，不表示可以直接生产上线。

## 生产签核包

在业务 UAT 可准备后，生成生产签核行动包：

```bash
python tools/generate_cn_signoff_packet.py \
  --status /tmp/cn_delivery_status.json \
  --json-output /tmp/cn_signoff_packet.json \
  --markdown-output /tmp/cn_signoff_packet.md \
  --require-business-uat-ready
```

签核包用于列出上线前必须由人完成的事项，包括但不限于：

- 中国财税专业人员对规则、来源、适用范围和报告边界的签核。
- 业务负责人对 UAT 结果和可用性范围的确认。
- 技术负责人对交付包、版本、源码提交和部署环境的确认。
- 数据负责人对客户数据缺口、限制说明和不可自动判断事项的确认。

## 签核证据校验

以 `docs/samples/cn_signoff_evidence_template.json` 为模板填写真人签核证据。完成后执行：

```bash
python tools/validate_cn_signoff_evidence.py \
  --packet /tmp/cn_signoff_packet.json \
  --evidence /tmp/cn_signoff_evidence.json \
  --json-output /tmp/cn_signoff_validation.json \
  --require-production-signoff-ready
```

签核证据必须满足：

- schema 版本正确。
- evidence 引用的 delivery version、source commit 和 signoff packet 与当前交付一致。
- 必填签核动作全部有真人决策、签核人、签核时间和证据引用。
- 自动验收证据未被标记为失败或阻断。
- 如果签核结论为 `deploy_with_limitations`，必须写明限制条件和客户可见说明。

签核证据校验通过后，再次汇总状态时必须带上 `--signoff-validation`：

```bash
python tools/summarize_cn_delivery_status.py \
  --manifest /tmp/cn_delivery_manifest.json \
  --summary /tmp/cn_delivery_acceptance_summary.json \
  --bundle-metadata /tmp/sdoo-cn-compliance-delivery.bundle.json \
  --preview-url "http://127.0.0.1:18070/web/login?db=target_database" \
  --preview-health /tmp/cn_preview_health.json \
  --preview-module /tmp/cn_preview_module.json \
  --real-data-closed-loop /tmp/cn_real_data_closed_loop.json \
  --signoff-validation /tmp/cn_signoff_validation.json \
  --json-output /tmp/cn_delivery_status_signed.json \
  --markdown-output /tmp/cn_delivery_status_signed.md \
  --require-business-uat-ready \
  --require-source-control-clean \
  --require-production-signoff-ready
```

只有在签核证据校验通过，且自动验收、交付物一致性、预览库、真实数据闭环和源码状态全部通过时，状态汇总才允许显示 `production_signoff_ready=true`。

## 开发演示数据

开发或演示时可以准备受控样例数据：

```bash
python tools/prepare_cn_demo_profile.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --allow-demo-data

python tools/prepare_cn_demo_closed_loop.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --allow-demo-data
```

演示数据只能用于开发、培训或预览，不得作为生产签核证据，也不得替代客户依法取得的账、票、申报、缴税和人事薪税资料。

## 生产注意事项

- 本插件不会自动发布未经治理、独立审批和中国财税专业人员签核的中国财税规则。
- 数据不足必须作为限制和下一步动作展示，不得解释为合规通过。
- AI 只能提供受控解释和操作引导，不替代规则引擎或中国财税专业判断。
- 正式业务库部署前，应先在隔离副本完成安装、升级、权限、多公司、真实数据只读验收和业务 UAT。
- 生产数据库、filestore、客户附件、密钥和访问口令不得进入 Git 或交付包。
- 若官方来源、规则内容、适用范围或客户数据口径发生变化，必须重新执行来源治理、规则测试、专业签核和交付状态汇总。
