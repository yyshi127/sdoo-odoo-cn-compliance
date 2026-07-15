# Sdoo China Electronic Invoice XBRL Parser

中国国家包的可选电子发票 XBRL 解析插件。插件将企业依法取得并已封存的电子发票源文件交给隔离工作进程，使用固定版本 Arelle 离线校验，再通过基础包的受控解析契约写入只读规范化台账。

## 安装

1. 先安装 `sudo_country_pack_cn`。
2. 在 Odoo Python 运行环境安装 `requirements.txt` 中固定版本的 `arelle-release==2.42.1`。
3. 更新应用列表并安装技术模块 `sudo_country_pack_cn_einvoice_xbrl`。
4. 不要把 Arelle 依赖临时安装在 Odoo 模块目录或提交到本仓库。

## 使用顺序

1. 在 `合规 -> 配置 -> 电子发票分类标准包` 登记财政部官方 ZIP、来源页面、入口文件和命名空间。
2. 由独立合规管理员执行安全检查并封存；同一人复核必须记录例外理由。
3. 对已识别的官方角色 URI 尾空格问题，明确选择受控兼容方案并填写确认说明；严格模式会拒绝含该问题的标准包。
4. 在中国外部数据集中封存企业依法取得的电子发票 XML、XBRL 或 ZIP。
5. 从数据集提交 XBRL 解析，后台任务完成后查看解析运行和电子发票台账。

## 审计边界

- 原始财政部 ZIP、SHA-256 和封存清单保持不变。
- 技术兼容只作用于隔离临时目录中的工作副本；完成 XML 语义检查后只修改目标 `roleURI` 属性两端空白，不整体重写 XSD。
- 任务记录兼容方案、修正数量和工作副本分类标准 SHA-256。
- 工作进程离线运行，限制 CPU、内存、超时、输入和输出体积。
- 任一 Arelle 校验错误都会阻止规范化结果生效。
- 失败重试不会替代上一份成功台账。
- 基础中国包后续升级不会把已安装解析器的能力标记误写为未启用。
- 解析成功不代表发票真实、可抵扣或税务处理合规，后续仍需真实性、账票和申报勾稽规则。

## 验证

纯 Python 契约测试不需要启动 Odoo：

```powershell
python tools\test_xbrl_contract.py
python tools\test_xbrl_normalizer.py
python tools\test_xbrl_worker_compatibility.py
```

`19.0.1.1.0` 已使用财政部“全面数字化电子发票（推广应用版）”官方包，在隔离 Odoo 运行时完成新装、升级、真实子进程和 cron 队列验收。专票、普票分别解析出 39/33 个事实和 3/2 条会计分录，均为 0 警告、0 错误；17 个 Odoo 运行时测试方法全部通过。详细记录见 `docs/MILESTONE_19_XBRL_RUNTIME_ACCEPTANCE.md`。

生产部署仍必须在目标 Odoo Python 环境安装固定的 `arelle-release==2.42.1`，并重新执行官方样例和企业依法取得文件的受控验收。临时 `PYTHONPATH` 仅可用于隔离测试，不能作为生产安装方式。
