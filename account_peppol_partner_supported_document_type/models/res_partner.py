# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ubl_cii_supported_format = fields.Text(readonly=True)

    def _check_document_type_support(self, participant_info, ubl_cii_format):
        res = super()._check_document_type_support(participant_info, ubl_cii_format)
        services = (participant_info or {}).get("services") or []
        ubl_cii_supported_format = {
            service.get("document_id")
            for service in services
            if service.get("document_id")
        }
        if self.exists() and len(self) == 1:
            self.ubl_cii_supported_format = "\n".join(ubl_cii_supported_format)
        return res

    def button_account_peppol_check_partner_endpoint(self):
        self.ensure_one()
        self.ubl_cii_supported_format = False
        return super().button_account_peppol_check_partner_endpoint()
