from base64 import b64encode
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import cleanup_xml_node


@dataclass
class PeppolAttachment:
    filename: str
    content: bytes
    mimetype: str


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    enable_peppol = fields.Boolean()
    checkbox_send_peppol = fields.Boolean(
        string="Send via PEPPOL",
        help="Send the invoice via PEPPOL",
    )
    # technical field needed for computing a warning text about the peppol configuration
    peppol_warning = fields.Char(
        string="Warning",
        readonly=True
    )
    account_peppol_edi_mode_info = fields.Char(
        compute="_compute_account_peppol_edi_mode_info"
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res_ids = self._context.get('active_ids')
        invoices = self.env['account.move'].browse(res_ids)
        company = invoices.mapped('company_id')
        if len(company) > 1:
            raise UserError(_("You can only send from the same company."))
        peppol_warnings = []
        invalid_partners = (
            invoices.mapped("partner_id.commercial_partner_id").filtered(
                lambda partner: (
                    not partner.account_peppol_is_endpoint_valid
                    or not partner.account_peppol_is_endpoint_valid
                    or not partner.peppol_eas
                    or not partner.peppol_endpoint
                )
            )
        )
        if invalid_partners:
            names = ", ".join(invalid_partners[:5].mapped("display_name"))
            peppol_warnings.append(_(
                "The following partners are not correctly configured to receive Peppol documents. "
                "Please check and verify their Peppol endpoint and the Electronic Invoicing format: "
                "%s",
                names,
            ))
        already_sent_via_peppol = invoices.filtered(
            lambda m: m.peppol_move_state in ("processing", "done")
        )
        if already_sent_via_peppol:
            names = ", ".join(already_sent_via_peppol[:5].mapped("display_name"))
            peppol_warnings.append(_(
                "The following invoices have already been sent via Peppol: %s",
                names,
            ))
        res["peppol_warning"] = "\n".join(peppol_warnings) if peppol_warnings else False
        res["enable_peppol"] = (
            company.account_peppol_proxy_state == "active"
            and not peppol_warnings
        )
        if res["enable_peppol"]:
            res["checkbox_send_peppol"] = True
            res["is_email"] = False
            res["is_print"] = False
        return res

    @api.depends("invoice_ids")
    def _compute_account_peppol_edi_mode_info(self):
        mode_strings = {
            "test": _("Test"),
            "demo": _("Demo"),
        }
        for wizard in self:
            edi_mode = wizard.invoice_ids[0].company_id.account_edi_proxy_client_peppol_ids.edi_mode
            display_edi_mode = mode_strings.get(edi_mode)
            wizard.account_peppol_edi_mode_info = (
                f" ({display_edi_mode})" if display_edi_mode else ""
            )

    def action_send_and_print(self):
        if self.checkbox_send_peppol:
            raise UserError(
                _("You cannot send via Peppol and print or email at the same time.")
            )
        return super().action_send_and_print()

    def action_send_peppol(self):
        if self.is_print or self.is_email:
            raise UserError(
                _("You cannot send via Peppol and print or email at the same time.")
            )
        self.ensure_one()
        for invoice in self.invoice_ids:
            self._peppol_send_invoice(invoice)

    @api.model
    def _peppol_embed_attachments(
        self, xml_string: bytes, attachments: list[PeppolAttachment]
    ) -> str:
        if not attachments:
            return xml_string
        tree = etree.fromstring(xml_string)
        for attachment in attachments:
            to_inject = f"""
                <cac:AdditionalDocumentReference
                    xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
                    <cbc:ID>{escape(attachment.filename)}</cbc:ID>
                    <cac:Attachment>
                        <cbc:EmbeddedDocumentBinaryObject mimeCode={quoteattr(attachment.mimetype)} filename={quoteattr(attachment.filename)}>
                            {b64encode(attachment.content).decode("ascii")}
                        </cbc:EmbeddedDocumentBinaryObject>
                    </cac:Attachment>
                </cac:AdditionalDocumentReference>
            """
            anchor_elements = tree.xpath("//*[local-name()='AccountingSupplierParty']")
            anchor_index = tree.index(anchor_elements[0])
            tree.insert(anchor_index, etree.fromstring(to_inject))
        return etree.tostring(
            cleanup_xml_node(tree), xml_declaration=True, encoding="UTF-8"
        )

    @api.model
    def _peppol_generate_xml_string_and_filename(self, invoice) -> tuple[bytes, str]:
        raise SystemError(
            "This method should be overridden in the specific format module to generate "
            "the Peppol XML string and filename. Please install the "
            "'account_peppol_send_format_odoo' or 'account_peppol_send_format_oca' module."
        )

    @api.model
    def _peppol_send_invoice(self, invoice):
        raise SystemError(
            "This method should be overridden in the specific sending module to send "
            "the Peppol invoice. Please install the "
            "'account_peppol_send_immediate' or 'account_peppol_send_queue_job' module."
        )
