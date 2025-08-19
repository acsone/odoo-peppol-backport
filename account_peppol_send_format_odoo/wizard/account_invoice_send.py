from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.account_peppol_backport.wizard.account_invoice_send import (
    PeppolAttachment,
)


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    @api.model
    def _peppol_generate_xml_string_and_filename(self, invoice) -> tuple[bytes, str]:
        builder = self.env["account.edi.xml.ubl_bis3"]
        xml_string, errors = builder._export_invoice(invoice)
        if errors:
            raise UserError(
                _("There were errors while generating the XML: %s") % ",\n".join(errors)
            )

        pdf_invoice = (
            self.env["ir.actions.report"]
            .with_context(
                # For OCA account_invoice_ubl, in case it is installed and
                # configured the UBL XML in the PDF.
                no_embedded_ubl_xml=True,
            )
            ._render_qweb_pdf("account.account_invoices", [invoice.id])[0]
        )
        attachments = [
            PeppolAttachment(
                filename=f"{invoice._get_report_mail_attachment_filename()}.pdf",
                content=pdf_invoice,
                mimetype="application/pdf",
            )
        ]
        xml_string = self._peppol_embed_attachments(xml_string, attachments)

        xml_filename = builder._export_invoice_filename(invoice)

        return xml_string, xml_filename
