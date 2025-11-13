# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Tax extension for UBL/CII',
    'version': '14.0.1.0.0',
    'summary': 'Tax extension for UBL/CII',
    'category': 'Accounting/Accounting',
    'website': 'https://github.com/acsone/odoo-peppol-backport',
    'depends': ['account_edi_ubl_cii'],
    'data': [
        'views/account_tax_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
    'author': 'Odoo S.A., Odoo Community Association (OCA), ACSONE SA/NV',
}
