# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from odoo import models


class AccountEDIXMLUBLBIS3(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_bis3"

    def _get_partner_party_vals(self, partner, role):
        # ensure that the peppol scheme and endpoint are correct, as the
        # default values computed by the account_edi_ubl_cii are not correct
        # for all countries. this has been fixed in odoo 17.0 (in the same way
        # as here).
        vals = super()._get_partner_party_vals(partner, role)
        partner = partner.commercial_partner_id
        vals.update(
            {
                "endpoint_id": partner.peppol_endpoint,
                "endpoint_id_attrs": {"schemeID": partner.peppol_eas},
            }
        )
        return vals
