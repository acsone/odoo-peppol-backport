# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

SELF_BILLING_DOCUMENT_TYPE = "urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0"


class ResPartner(models.Model):
    _inherit = "res.partner"

    peppol_self_billing_supported = fields.Boolean(
        compute="_compute_peppol_self_billing_supported", store=True
    )

    @api.depends("ubl_cii_supported_format")
    def _compute_peppol_self_billing_supported(self):
        for rec in self:
            rec.peppol_self_billing_supported = bool(
                rec.ubl_cii_supported_format
                and any(
                    SELF_BILLING_DOCUMENT_TYPE in dt
                    for dt in rec.ubl_cii_supported_format.split("\n")
                )
            )
