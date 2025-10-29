# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # redefine as related
    company_registry = fields.Char(related="coc_registration_number", readonly=False)

    def _peppol_eas_endpoint_depends(self):
        return super()._peppol_eas_endpoint_depends() + ["coc_registration_number"]

    # override to use the actual peppol fields
    def _get_peppol_endpoint_id(self):
        self.ensure_one()
        # Override this function if your business case requires other values.
        return {
            "endpoint_id": self.peppol_endpoint,
            "scheme_id": self.peppol_eas,
        }
