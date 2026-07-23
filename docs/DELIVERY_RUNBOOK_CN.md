# Sdoo 中国财税合规包交付运行手册

## 适用范围

本手册用于交付、部署、验收和签核 Odoo 19 中国财税合规插件体系：

- `sudo_country_pack_cn`：中国财税合规主国家包。
- `sudo_country_pack_cn_einvoice_xbrl`：可选电子发票 XBRL 解析子模块。
- `tools/`：交付包构建、自动验收、交付清单、状态汇总、签核包、签核证据校验和有序证据链工具。
- `docs/samples/`：受控外部税务数据契约和签核证据样例。

本手册不包含生产服务器地址、私钥、口令、客户数据、数据库备份或 filestore。上述材料不得进入 Git 或交付包。

## 标准交付物

标准交付至少包含：

1. `sdoo-cn-compliance-delivery.tgz`：确定性交付包。
2. `sdoo-cn-compliance-delivery.bundle.json`：交付包元数据，包含版本、源提交、文件哈希和 bundle 哈希。
3. `cn_delivery_manifest.json`：交付清单。
4. `cn_delivery_acceptance_summary.json`：自动验收摘要。
5. `cn_delivery_status.json` / `cn_delivery_status.md`：业务可验收状态摘要。
6. `cn_signoff_packet.json` / `cn_signoff_packet.md`：生产签核行动包。
7. `cn_signoff_validation.json`：只有完成真人签核证据校验后才能作为生产签核证据使用。

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

如启用可选 XBRL 解析子模块，生产 Python 环境还必须按受控变更流程安装并锁定：

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
- 如 summary 包含 Odoo runtime 日志，则日志结果为 `0 failed / 0 errors`。

## 预览库和真实数据门槛

在隔离预览库安装后，至少执行以下检查：

```bash
python tools/check_cn_preview_health.py \
  --url "http://127.0.0.1:18070/web/login?db=target_database" \
  --json-output /tmp/cn_preview_health.json

python tools/check_cn_preview_module.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --expected-version 19.0.1.147.0 \
  --json-output /tmp/cn_preview_module.json

python tools/check_cn_real_data_closed_loop.py \
  --python-bin /path/to/python \
  --odoo-bin /path/to/odoo-bin \
  --config /path/to/odoo.conf \
  --database target_database \
  --expected-version 19.0.1.147.0 \
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
  --upgrade-summary /tmp/cn_delivery_acceptance_upgrade_summary.json \
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
- 业务复核人对合规总览、风险中心、整改跟踪和合规报告页面的代表性 UX 走查确认，尤其是风险等级、原因、影响金额、期间、责任人、截止日期、整改状态和下一步动作在常用桌面和笔记本屏幕上是否清晰可读。

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
- `decisions` 必须是列表，且每个签核动作 key 必须唯一、必须来自 signoff packet，不得重复或自造额外签核项。
- 必填签核动作全部有真人决策、签核人、签核时间和证据引用；签核人和证据引用必须替换为真实记录，不允许保留模板占位值。
- 签核日期必须使用 ISO 格式 `YYYY-MM-DD`，例如 `2026-07-17`；`YYYY-MM-DD` 这个模板文本本身不能通过校验。
- 自动验收证据未被标记为失败或阻断。
- 如果任何签核动作选择 `accepted_with_limitations`、`approved_with_limitations`、`current_with_documented_limitations`、`limitations_documented`、`passed_with_limitations` 或 `deploy_with_limitations`，必须在 `limitations` 中写明限制条件和客户可见说明；`limitations` 必须是列表，且至少包含一条 20 个字符以上的实质性限制说明。

签核证据校验通过后，再次汇总状态时必须带上 `--signoff-validation`：

```bash
python tools/summarize_cn_delivery_status.py \
  --manifest /tmp/cn_delivery_manifest.json \
  --summary /tmp/cn_delivery_acceptance_summary.json \
  --upgrade-summary /tmp/cn_delivery_acceptance_upgrade_summary.json \
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
- AI 只能提供受控解释和操作引导，不替代规则引用或中国财税专业判断。
- 正式业务库部署前，应先在隔离副本完成安装、升级、权限、多公司、真实数据只读验收和业务 UAT。
- 生产数据库、filestore、客户附件、密钥和访问口令不得进入 Git 或交付包。
- 若官方来源、规则内容、适用范围或客户数据口径发生变化，必须重新执行来源治理、规则测试、专业签核和交付状态汇总。

## Production Sign-Off Evidence Draft

```bash
python tools/render_cn_signoff_evidence_template.py \
  --packet dist/cn_signoff_packet_mNNN.json \
  --json-output dist/cn_signoff_evidence_draft_mNNN.json
```

Use this generated draft as the preferred starting point for production
sign-off evidence. It copies `version`, `source_commit` and every production
action key from the current sign-off packet, then leaves reviewer, date,
evidence reference and notes placeholders for human replacement. The draft must
remain invalid until real signed evidence replaces every placeholder.

## Objective Completion Audit

```bash
python tools/audit_cn_objective_completion.py \
  --status dist/cn_delivery_status_mNNN.json \
  --json-output dist/cn_objective_completion_audit_mNNN.json \
  --markdown-output dist/cn_objective_completion_audit_mNNN.md
```

Use this audit after each status refresh to see which parts of the final
objective are backed by current evidence and which remain blocked by human UAT,
professional sign-off, official-source freshness review or customer-specific
data/risk review.

## Ordered Sign-Off Evidence Chain

For release evidence, prefer the ordered chain builder instead of manually
running status, packet, validation and objective-audit commands out of order:

```bash
python tools/build_cn_signoff_evidence_chain.py \
  --bundle-metadata dist/sdoo-cn-compliance-delivery-mNNN.bundle.json \
  --manifest dist/cn_delivery_manifest_mNNN_full.json \
  --summary dist/cn_delivery_acceptance_mNNN_remote.json \
  --upgrade-summary dist/cn_delivery_acceptance_mNNN_upgrade_remote.json \
  --preview-health dist/cn_preview_health_mNNN.json \
  --preview-module dist/cn_preview_module_mNNN.json \
  --real-data-closed-loop dist/cn_real_data_closed_loop_mNNN.json \
  --preview-url http://127.0.0.1:18070/web/login?db=target_database \
  --output-prefix dist/cn_delivery_mNNN_chain
```

The builder creates a bootstrap validation only to bind production blockers to
the sign-off packet, generates the objective completion audit, then renders and
validates the final sign-off packet that already contains objective-audit
evidence. With placeholder evidence, the final validation must remain blocked.
After signed human evidence is available, rerun the same command with:

```bash
  --completed-evidence dist/cn_signoff_evidence_completed.json \
  --require-production-signoff-ready
```

`--require-production-signoff-ready` must be used for any production release
automation. It exits non-zero when the chain is still using placeholder
evidence, when the human sign-off evidence does not validate, or when the final
status still reports production blockers.

Only the final chain status should be used as production-readiness evidence.
Do not use the bootstrap status, standalone packet, standalone validation or
draft evidence files as a production deployment decision.
