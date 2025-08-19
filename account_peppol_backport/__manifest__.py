# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "Peppol",
    'summary': "This module is used to register with the Odoo SA PEPPOL access point",
    'category': 'Accounting/Accounting',
    'version': '16.0.1.0.0',
    'depends': [
        'account_peppol_partner',
        'account_edi_proxy_client_peppol',
        # account_edi_ubl_cii is not strictly necessary but the part that
        # extracts EmbeddedDocumentBinaryObject is useful to have at least a PDF
        # attachment in the draft moves created from incoming Peppol invoices.
    ],
    "external_dependencies": {
        "python": ["phonenumbers"],
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
    'assets': {
        'web.assets_backend': [
            'account_peppol_backport/static/src/components/**/*',
        ],
    },
    'author': 'Odoo S.A.,ACSONE SA/NV,Odoo Community Association (OCA)',
    'website': 'https://github.com/acsone/odoo-peppol-backport',
}
