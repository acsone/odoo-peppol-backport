# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from odoo import api, models

from odoo.addons.account_peppol_backport.wizard.account_invoice_send import (
    PeppolAttachment,
)


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    @api.model
    def _peppol_generate_xml_string_and_filename(self, invoice):
        version = invoice.get_ubl_version()
        xml_string = invoice.generate_ubl_xml_string(version=version)
        if not invoice.company_id.embed_pdf_in_ubl_xml_invoice:
            pdf_invoice = (
                self.env.ref("account.account_invoices")
                .with_context(
                    # For OCA account_invoice_ubl, in case it is configured to
                    # embed the UBL XML in the PDF.
                    no_embedded_ubl_xml=True,
                )
                .render_qweb_pdf(invoice.ids)[0]
            )
            attachment_filename = invoice.number.replace("/", "_") + ".pdf"
            attachments = [
                PeppolAttachment(
                    filename=attachment_filename,
                    content=pdf_invoice,
                    mimetype="application/pdf",
                )
            ]
            xml_string = self._peppol_embed_attachments(xml_string, attachments)
        xml_filename = invoice.number.replace("/", "_") + "_ubl_bis3.xml"

        return xml_string, xml_filename
