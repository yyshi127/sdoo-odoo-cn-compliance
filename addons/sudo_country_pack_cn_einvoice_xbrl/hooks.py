from copy import deepcopy

from .models.country_pack import _CAPABILITY_WRITE_MARKER


def _set_parser_capability(env, enabled):
    country_pack = env.ref(
        "sudo_country_pack_cn.compliance_country_pack_cn",
        raise_if_not_found=False,
    )
    if not country_pack:
        return
    capabilities = deepcopy(country_pack.capability_json or {})
    features = capabilities.setdefault("features", {})
    features["einvoice_xbrl_parser"] = bool(enabled)
    country_pack.with_context(
        cn_xbrl_capability_transition=_CAPABILITY_WRITE_MARKER
    ).write({"capability_json": capabilities})


def post_init_hook(env):
    _set_parser_capability(env, True)


def uninstall_hook(env):
    _set_parser_capability(env, False)
