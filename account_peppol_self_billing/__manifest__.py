# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# from odoo.addons.account_invoice_supplier_self_invoice

{
    "name": "Odoo/addons/account Peppol Self Billing",
    "summary": """If a contact is configured for PEPPOL and self-billing, you ensures that self-billing is authorized via PEPPOL for this customer.""",
    "version": "16.0.1.0.0",
    "license": "AGPL-3",
    "author": "ACSONE SA/NV,Odoo Community Association (OCA)",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "depends": [
        # Third-party
        "account_invoice_supplier_self_invoice",
        "account_peppol_backport",
    ],
    "data": ["views/res_partner.xml"],
    "demo": [],
}
