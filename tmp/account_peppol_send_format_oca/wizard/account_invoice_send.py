from odoo import api, models


class AccountInvoiceSend(models.TransientModel):
    _inherit = "account.invoice.send"

    @api.model
    def _peppol_generate_xml_string_and_filename(self, invoice):
        # XXX PEPPOL BACKPORT: this does not generate a valid ubl_bis3 document
        ubl_version = invoice.get_ubl_version()
        xml_string = invoice.generate_ubl_xml_string(version=ubl_version)
        xml_filename = invoice.get_ubl_filename(version=ubl_version)
        return xml_string, xml_filename
