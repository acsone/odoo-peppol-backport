# Copyright 2025 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64

from odoo import api, fields, models
from odoo.osv.expression import FALSE_DOMAIN

from odoo.addons.account_peppol_backport.wizard.account_invoice_send import (
    PeppolAttachment,
)
from odoo.addons.account_peppol_send_format_odoo.wizard.account_invoice_send import (
    AccountInvoiceSend as BaseAccountInvoiceSend,
)


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    peppol_is_show_attachment_visible = fields.Boolean(
        compute="_compute_peppol_is_show_attachment_visible",
    )
    peppol_existing_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="account_invoice_send_existing_attachment_rel",
        string="Existing Attachments",
    )
    peppol_existing_attachment_ids_domain = fields.Binary(
        compute="_compute_peppol_existing_attachment_ids_domain",
    )
    peppol_new_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="account_invoice_send_new_attachment_rel",
        string="New Attachments",
    )

    @api.depends(
        "checkbox_send_peppol",
        "invoice_ids",
    )
    def _compute_peppol_is_show_attachment_visible(self):
        for rec in self:
            rec.peppol_is_show_attachment_visible = (
                len(rec.invoice_ids) == 1 and rec.checkbox_send_peppol
            )

    @api.depends(
        "invoice_ids",
        "peppol_is_show_attachment_visible",
    )
    def _compute_peppol_existing_attachment_ids_domain(self):
        for rec in self:
            invoice = rec.invoice_ids
            if len(invoice) != 1:
                rec.peppol_existing_attachment_ids_domain = FALSE_DOMAIN
                continue
            invoice_id = invoice.id
            if isinstance(invoice_id, models.NewId):
                invoice_id = invoice_id.origin
            rec.peppol_existing_attachment_ids_domain = [
                ("res_id", "=", invoice_id),
                ("res_model", "=", invoice._name),
            ]

    @api.onchange(
        "checkbox_send_peppol",
        "peppol_is_show_attachment_visible",
    )
    def _onchange_load_peppol_attachments(self):
        for rec in self:
            invoice = rec.invoice_ids
            if rec.peppol_is_show_attachment_visible and len(invoice) == 1:
                rec.peppol_existing_attachment_ids = invoice.peppol_attachment_ids

    def action_send_peppol(self):
        self.ensure_one()
        invoice = self.invoice_ids
        if self.peppol_is_show_attachment_visible and len(invoice) == 1:
            new_attachments = self.peppol_new_attachment_ids
            new_attachments.write(
                {
                    "res_id": invoice.id,
                    "res_model": invoice._name,
                    "res_field": False,
                }
            )
            invoice.write(
                {
                    "peppol_attachment_ids": [
                        fields.Command.set(
                            self.peppol_existing_attachment_ids.ids
                            + new_attachments.ids
                        )
                    ]
                }
            )
        return super().action_send_peppol()

    @api.model
    def _peppol_generate_xml_string_and_filename(self, invoice) -> tuple[bytes, str]:
        (
            xml_string,
            xml_filename,
        ) = BaseAccountInvoiceSend._peppol_generate_xml_string_and_filename(
            self, invoice
        )
        peppol_attachments = invoice.peppol_attachment_ids
        if peppol_attachments:
            attachments = [
                PeppolAttachment(
                    filename=peppol_attachment.name,
                    content=base64.b64decode(peppol_attachment.datas),
                    mimetype=peppol_attachment.mimetype,
                )
                for peppol_attachment in peppol_attachments
            ]
            xml_string = self._peppol_embed_attachments(xml_string, attachments)
        return xml_string, xml_filename
