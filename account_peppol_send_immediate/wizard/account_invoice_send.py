from odoo import api, models


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    @api.model
    def _peppol_send_invoice(self, invoice):
        xml_string, xml_filename = self._peppol_generate_xml_string_and_filename(
            invoice
        )
        edi_user = invoice.company_id.account_edi_proxy_client_peppol_ids.filtered(
            lambda u: u.proxy_type == "peppol"
        )
        edi_user._peppol_send_document(invoice, xml_string, xml_filename)
        # we commit to keep the peppol_move_state in sync with the remote proxy state
        self.env.cr.commit()  # pylint: disable=invalid-commit
