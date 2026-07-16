# M41 中国评估数据基础摘要

## 目标

M40 已经交付“中国数据准备中心”，但规则评估和报告准备页面仍需要直接告诉用户：本次评估期间到底有没有受控数据基础、是否存在封存或真实性问题、是否已经形成规范化记录。本次增量把数据准备状态挂到规则评估上，让“规则扫描 → 风险 → 整改 → 报告”的链条更容易理解。

## 已交付

- 新增 `sudo.compliance.assessment` 中国数据基础字段：
  - `cn_data_basis_state`：未设期间、未登记数据、数据受阻、需复核、数据可用。
  - `cn_data_basis_dataset_count`、`cn_data_basis_ready_count`、`cn_data_basis_warning_count`、`cn_data_basis_blocked_count`。
  - `cn_data_basis_normalized_record_count`。
  - `cn_data_basis_next_action`。
- 新增 `action_cn_open_assessment_data_basis()`，按评估档案和评估期间打开相关数据集。
- 报告准备中心增加数据基础状态、相关数据集、规范化记录和下一步提示。
- 国家包能力增加 `china_assessment_data_basis`。
- 版本升级到 `19.0.1.38.0`，并新增迁移脚本刷新国家包元数据。

## 设计边界

- 只做可视化与导航，不改变报告准备状态判定，也不阻止用户编制带限制说明的报告。
- 相关数据集按评估档案和期间重叠匹配，不强制要求每个税种都具备完整数据；缺口由具体规则和对账批次继续识别。
- 当前运行库仍因服务器 PostgreSQL 故障无法做真实 Odoo 升级验证；已完成静态 XML/Python/插件契约校验。
