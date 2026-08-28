{
    "name": "Account Peppol Partner",
    "summary": """Peppol information on partners.""",
    "version": "12.0.1.0.0",
    "license": "LGPL-3",
    'author': (
        'Odoo S.A., ACSONE SA/NV, Coop IT Easy SC, '
        'Odoo Community Association (OCA)'
    ),
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        "account",
        "mail",
    ],
    "external_dependencies": {
        "python": [
            "stdnum",
        ],
    },
    "data": ["views/res_partner_views.xml"],
}
