# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

{
    "name": "Account Peppol Send Format OCA",
    "summary": (
        "Convert invoices to Peppol XML using the OCA's "
        "account_invoice_ubl_peppol module"
    ),
    "version": "12.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/acsone/odoo-peppol-backport",
    "author": "Coop IT Easy SC, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "depends": [
        "account_invoice_ubl_peppol",
        "account_peppol_backport",
    ],
    "excludes": [
        "account_peppol_send_format_odoo",
    ],
}
