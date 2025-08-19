# Copyright 2025 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Account Peppol Send Format Odoo",
    "summary": """Convert invoices to Peppol XML using the Odoo's account_edi_ubl_cii module.""",
    "version": "16.0.1.0.0",
    "license": "LGPL-3",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        "account_edi_ubl_cii",
        "account_edi_ubl_cii_tax_extension",
        "account_peppol_backport",
    ],
    "excludes": [
        "account_peppol_send_format_oca",
    ],
    "data": [],
    "demo": [],
}
