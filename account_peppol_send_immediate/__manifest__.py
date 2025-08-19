# Copyright 2025 ACSONE SA/NV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

{
    "name": "Account Peppol Send Immediate",
    "summary": """Send the invoices to the Peppol accesspoint immediately.""",
    "version": "16.0.1.0.0",
    "license": "LGPL-3",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        "account_peppol_backport",
    ],
    "excludes": [
        "account_peppol_send_queue_job",
    ],
    "data": [],
    "demo": [],
}
