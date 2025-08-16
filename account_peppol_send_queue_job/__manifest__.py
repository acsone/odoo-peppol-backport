# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Account Peppol Send via Queue Job",
    "summary": """Send  invoices to the Peppol accesspoint as queue jobs..""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        "account_peppol_backport",
        "queue_job",
    ],
    "excludes": [
        "account_peppol_send_immediate",
    ],
    "data": [],
    "demo": [],
}
