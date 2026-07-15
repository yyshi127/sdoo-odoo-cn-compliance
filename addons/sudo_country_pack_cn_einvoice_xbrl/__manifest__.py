{
    "name": "Sdoo China Electronic Invoice XBRL Parser",
    "summary": "Isolated Arelle parser for governed China e-invoice datasets",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "author": "Sdoo",
    "license": "LGPL-3",
    "depends": [
        "sudo_country_pack_cn",
    ],
    "external_dependencies": {
        "python": ["arelle"],
    },
    "data": [
        "security/compliance_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/taxonomy_bundle_views.xml",
        "views/xbrl_job_views.xml",
        "views/external_dataset_views.xml",
        "wizard/parse_wizard_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
}
