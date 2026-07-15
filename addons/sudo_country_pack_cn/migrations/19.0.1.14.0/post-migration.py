from odoo import SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata


SOURCE_URL_REPLACEMENTS = {
    "source_cn_accounting_law_2024_candidate": (
        "https://wb.flk.npc.gov.cn/flfg/PDF/"
        "b450cf89277c40918e7077c5418d93d9.pdf",
        "https://kjs.mof.gov.cn/zhengcefabu/202408/t20240812_3941615.htm",
    ),
    "source_cn_accounting_archives_order_79_candidate": (
        "https://tfs.mof.gov.cn/caizhengbuling/201512/"
        "t20151214_1613338.htm",
        "https://www.gov.cn/gongbao/content/2016/content_5041555.htm",
    ),
}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_country_pack_metadata(env)
    for source_xmlid, (old_url, new_url) in SOURCE_URL_REPLACEMENTS.items():
        source = env.ref(
            f"sudo_country_pack_cn.{source_xmlid}",
            raise_if_not_found=False,
        )
        if (
            not source
            or source.status != "draft"
            or source.snapshot_attachment_id
            or source.content_hash
            or source.official_url != old_url
        ):
            continue
        source.write({"official_url": new_url})
        env["sudo.compliance.audit.event"]._log_records(
            source,
            "authority_source.candidate_url_migrated",
            previous_state="draft",
            new_state="draft",
            details={"old_url": old_url, "new_url": new_url},
        )
