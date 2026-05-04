# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Peppol",
    'summary': "This module is used to register with the Odoo SA PEPPOL access point",
    'category': 'Accounting/Accounting',
    'version': '12.0.2.0.0',
    'depends': [
        'account_peppol_partner',
        'account_edi_proxy_client_peppol',
    ],
    "external_dependencies": {
        "python": [
            "phonenumbers",
            "stdnum",
        ],
    },
    'data': [
        'data/cron.xml',
        'views/account_journal_dashboard_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/account_invoice_send_views.xml'
    ],
    'demo': [
        'demo/account_peppol_demo.xml',
    ],
    'license': 'LGPL-3',
    'author': (
        'Odoo S.A., ACSONE SA/NV, Coop IT Easy SC, '
        'Odoo Community Association (OCA)'
    ),
    'website': 'https://github.com/acsone/odoo-peppol-backport',
}
