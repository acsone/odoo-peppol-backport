# Part of Odoo. See LICENSE file for full copyright and licensing details.

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.account_peppol_partner.models.eas_mapping import (
    PEPPOL_MAILING_COUNTRIES,
)


class AccountMove(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def get_sale_types(self):
        return ['out_invoice', 'out_refund']

    def is_sale_document(self):
        return self.type in self.get_sale_types()

    peppol_message_uuid = fields.Char(string='PEPPOL message ID')
    peppol_move_state = fields.Selection(
        selection=[
            ('ready', 'Ready to send'),
            ('to_send', 'Queued'),
            ('skipped', 'Skipped'),
            ('processing', 'Pending Reception'),
            ('canceled', 'Canceled'),
            ('done', 'Done'),
            ('error', 'Error'),
        ],
        compute='_compute_peppol_move_state', store=True,
        string='PEPPOL status',
        copy=False,
    )
    peppol_is_demo_uuid = fields.Boolean(compute="_compute_peppol_is_demo_uuid")

    def action_cancel_peppol_documents(self):
        # if the peppol_move_state is processing/done
        # then it means it has been already sent to peppol proxy and we can't cancel
        if any(move.peppol_move_state in {'processing', 'done'} for move in self):
            raise UserError(_("Cannot cancel an entry that has already been sent to PEPPOL"))
        self.peppol_move_state = 'canceled'

    @api.depends('peppol_message_uuid')
    def _compute_peppol_is_demo_uuid(self):
        for move in self:
            move.peppol_is_demo_uuid = (move.peppol_message_uuid or '').startswith('demo_')

    @api.depends('move_id.state')
    def _compute_peppol_move_state(self):
        for move in self:
            if all([
                move.company_id.account_peppol_proxy_state == 'active',
                move.commercial_partner_id.account_peppol_is_endpoint_valid,
                move.move_id.state == 'posted',
                move.type in ('out_invoice', 'out_refund', 'out_receipt'),
                not move.peppol_move_state,
            ]):
                move.peppol_move_state = 'ready'
            elif (
                move.move_id.state == 'draft'
                and move.is_sale_document()
                and move.peppol_move_state not in ('processing', 'done')
            ):
                move.peppol_move_state = False
            else:
                move.peppol_move_state = move.peppol_move_state

    def _notify_by_email_prepare_rendering_context(self, message, msg_vals=False, model_description=False,
                                                   force_email_company=False, force_email_lang=False):
        render_context = super()._notify_by_email_prepare_rendering_context(
            message, msg_vals=msg_vals, model_description=model_description,
            force_email_company=force_email_company, force_email_lang=force_email_lang
        )
        invoice = render_context['record']
        invoice_country = invoice.commercial_partner_id.country_code
        company_country = invoice.company_id.country_code
        company_on_peppol = invoice.company_id.account_peppol_proxy_state == 'active'
        if company_on_peppol and company_country in PEPPOL_MAILING_COUNTRIES and invoice_country in PEPPOL_MAILING_COUNTRIES:
            render_context['peppol_info'] = {
                'peppol_country': invoice_country,
                'is_peppol_sent': invoice.peppol_move_state in ('processing', 'done'),
                'partner_on_peppol': invoice.commercial_partner_id.account_peppol_is_endpoint_valid,
            }
        return render_context

    def _extract_peppol_embedded_files(self, xml_data):
        self.ensure_one()
        tree = etree.fromstring(xml_data)
        invoice = self
        # this comes from account.edi.common._import_invoice_ubl_cii() from account_edi_ubl_cii in odoo 17.0
        attachments = self.env['ir.attachment']
        additional_docs = tree.findall('./{*}AdditionalDocumentReference')
        for document in additional_docs:
            attachment_name = document.find('{*}ID')
            attachment_data = document.find('{*}Attachment/{*}EmbeddedDocumentBinaryObject')
            if attachment_name is not None \
                    and attachment_data is not None \
                    and attachment_data.attrib.get('mimeCode') == 'application/pdf':
                text = attachment_data.text
                # Normalize the name of the file : some e-fff emitters put the full path of the file
                # (Windows or Linux style) and/or the name of the xml instead of the pdf.
                # Get only the filename with a pdf extension.
                name = (attachment_name.text or 'invoice').split('\\')[-1].split('/')[-1].split('.')[0] + '.pdf'
                attachment = self.env['ir.attachment'].create({
                    'name': name,
                    'datas_fname': name,
                    'res_id': invoice.id,
                    'res_model': 'account.invoice',
                    'datas': text + '=' * (len(text) % 3),  # Fix incorrect padding
                    'type': 'binary',
                    'mimetype': 'application/pdf',
                })
                # Upon receiving an email (containing an xml) with a configured alias to create invoice, the xml is
                # set as the main_attachment. To be rendered in the form view, the pdf should be the main_attachment.
                if invoice.message_main_attachment_id and \
                        invoice.message_main_attachment_id.name.endswith('.xml') and \
                        'pdf' not in invoice.message_main_attachment_id.mimetype:
                    invoice.message_main_attachment_id = attachment
                attachments |= attachment
        if attachments:
            # if default_res_id is present in the context, account_facturx
            # will not try to parse the pdf. this is what we want, as it may
            # fail.
            invoice.with_context(
                no_new_invoice=True,
                default_res_id=None,
            ).message_post(attachment_ids=attachments.ids)
