# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"
    ubl_cii_supported_format = fields.Char(readonly=True)

    def _check_document_type_support(self, participant_info, ubl_cii_format):
        res = super()._check_document_type_support(participant_info, ubl_cii_format)
        services = (participant_info or {}).get("services") or []
        customization_ids = self._get_customization_ids()
        customization_ids.update(
            {"selfbilling": "urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0"}
        )
        supported = set()
        for service in services:
            document_id = service.get("document_id") or ""
            supported |= {
                fmt for fmt, cid in customization_ids.items() if cid in document_id
            }
        if self.exists() and len(self) == 1:
            self.ubl_cii_supported_format = "|".join(supported)

        # if partner not configured for self-billing with peppol
        # -> nothing to check
        if not (self.self_invoice and self.is_peppol_edi_format):
            return res
        if ubl_cii_format != "ubl_bis3":
            # only support ubl_bis3 for now
            return False
        return "selfbilling" in supported

    @api.depends("self_invoice")
    def _compute_account_peppol_is_endpoint_valid(self):
        return super()._compute_account_peppol_is_endpoint_valid()
