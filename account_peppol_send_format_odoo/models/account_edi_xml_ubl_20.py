# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from odoo import models


class AccountEDIXMLUBL20(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_20"

    def _export_invoice_vals(self, invoice):
        # set order_reference in the same way as in odoo 17.0
        vals = super()._export_invoice_vals(invoice)
        if not vals["vals"]["order_reference"]:
            vals["vals"]["order_reference"] = invoice.name
        return vals
