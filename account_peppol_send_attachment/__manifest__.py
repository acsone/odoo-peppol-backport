# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Account Peppol Send Attachment",
    "summary": """Allow to link attachments to be sent to be peppol alongside the PDF report""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        "account_peppol_send_format_odoo",
    ],
    "data": [
        "wizards/account_invoice_send.xml",
    ],
    "demo": [],
}
