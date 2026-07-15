{
    "name": "Sdoo China Country Pack",
    "summary": "Governed China fiscal compliance profiles and country-pack foundations",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Sdoo",
    "license": "LGPL-3",
    "depends": [
        "sudo_global_finance",
        "account",
        "l10n_cn",
    ],
    "data": [
        "data/country_pack_data.xml",
        "views/compliance_integration_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
