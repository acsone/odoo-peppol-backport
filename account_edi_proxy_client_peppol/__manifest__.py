{
    'name': 'Proxy features for the peppol access point',
    'version': '12.0.1.0.0',
    'category': 'Accounting/Accounting',
    'depends': ['account'],
    'external_dependencies': {
        'python': ['cryptography']
    },
    'data': [
        'security/ir.model.access.csv',
        'security/account_edi_proxy_client_security.xml',
        'views/account_edi_proxy_user_views.xml',
    ],
    'license': 'LGPL-3',
    'author': (
        'Odoo S.A., ACSONE SA/NV, Coop IT Easy SC, '
        'Odoo Community Association (OCA)'
    ),
    'website': 'https://github.com/acsone/odoo-peppol-backport',
}
