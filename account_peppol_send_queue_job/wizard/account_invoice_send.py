import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    @api.model
    def _peppol_send_invoice(self, invoice):
        if invoice.peppol_move_state in ("processing", "done"):
            raise UserError(
                _(
                    "Cannot send an invoice that is already being processed "
                    "or has been sent."
                )
            )
        invoice.peppol_move_state = "to_send"
        self.env["account.invoice.send"].with_delay()._peppol_send_invoice_job(
            invoice.id
        )

    @api.model
    def _peppol_send_invoice_job(self, invoice_id):
        invoice = self.env["account.move"].browse(invoice_id)
        if invoice.state != "posted":
            _logger.warning(
                "Invoice %s is not posted, skipping Peppol send job.",
                invoice.display_name,
            )
            return
        if invoice.peppol_move_state != "to_send":
            _logger.warning(
                "Invoice %s is not in 'to_send' state, skipping Peppol send job.",
                invoice.display_name,
            )
            return
        try:
            xml_string, xml_filename = self._peppol_generate_xml_string_and_filename(
                invoice
            )
        except Exception as e:
            # This is usually a configuration or data error, so we log as info
            # level to get the stack trace in the logs, in case the message
            # written in the invoice chatter is not clear enough.
            _logger.info(
                "Error generating Peppol XML for invoice %s: %s",
                invoice.display_name,
                e,
                exc_info=True,
            )
            invoice.peppol_move_state = "error"
            invoice._message_log(body=_("Error generating Peppol XML: %s", e))
        else:
            edi_user = invoice.company_id.account_edi_proxy_client_peppol_ids.filtered(
                lambda u: u.proxy_type == "peppol"
            )
            edi_user._peppol_send_document(invoice, xml_string, xml_filename)
