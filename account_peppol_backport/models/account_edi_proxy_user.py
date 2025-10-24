# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from base64 import b64encode

from odoo import _, fields, models, modules, tools
from odoo.exceptions import UserError

from odoo.addons.account_edi_proxy_client_peppol.models.account_edi_proxy_user import (
    AccountEdiProxyError,
)

from ..tools.demo_utils import handle_demo

_logger = logging.getLogger(__name__)
BATCH_SIZE = 50


class AccountEdiProxyClientPeppolUser(models.Model):
    _inherit = 'account_edi_proxy_client_peppol.user'

    peppol_verification_code = fields.Char(string='SMS verification code')
    proxy_type = fields.Selection(selection_add=[('peppol', 'PEPPOL')], ondelete={'peppol': 'cascade'})

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------


    def _make_request(self, url, params=False):
        assert not self.proxy_type or self.proxy_type == 'peppol', "This proxy object should only be used for Peppol requests."
        if self.proxy_type == 'peppol':
            return self._make_request_peppol(url, params=params)
        return super()._make_request(url, params=params)

    @handle_demo
    def _make_request_peppol(self, url, params=False):
        # extends account_edi_proxy_client to update peppol_proxy_state
        # of archived users
        try:
            result = super()._make_request(url, params)
        except AccountEdiProxyError as e:
            if (
                e.code == 'no_such_user'
                and not self.active
                and not self.company_id.account_edi_proxy_client_peppol_ids.filtered(lambda u: u.proxy_type == 'peppol')
            ):
                self.company_id.write({
                    'account_peppol_proxy_state': 'not_registered',
                    'account_peppol_migration_key': False,
                })
                # commit the above changes before raising below
                if not tools.config['test_enable'] and not modules.module.current_test:
                    self.env.cr.commit()  # pylint: disable=invalid-commit
            raise AccountEdiProxyError(e.code, e.message) from e
        return result

    def _get_proxy_urls(self):
        urls = super()._get_proxy_urls()
        urls['peppol'] = {
            'prod': 'https://peppol.api.odoo.com',
            'test': 'https://peppol.test.odoo.com',
            'demo': 'demo',
        }
        return urls

    # -------------------------------------------------------------------------
    # CRONS
    # -------------------------------------------------------------------------

    def _cron_peppol_get_new_documents(self):
        edi_users = self.search([('company_id.account_peppol_proxy_state', '=', 'active'), ('proxy_type', '=', 'peppol')])
        edi_users._peppol_get_new_documents()

    def _cron_peppol_get_message_status(self):
        edi_users = self.search([('company_id.account_peppol_proxy_state', '=', 'active'), ('proxy_type', '=', 'peppol')])
        edi_users._peppol_get_message_status()

    # -------------------------------------------------------------------------
    # BUSINESS ACTIONS
    # -------------------------------------------------------------------------

    def _get_proxy_identification(self, company, proxy_type):
        if proxy_type == 'peppol':
            if not company.peppol_eas or not company.peppol_endpoint:
                raise UserError(
                    _("Please fill in the EAS code and the Participant ID code."))
            return f'{company.peppol_eas}:{company.peppol_endpoint}'
        return super()._get_proxy_identification(company, proxy_type)

    def _peppol_get_new_documents(self):
        # Context added to not break stable policy: useful to tweak on databases processing large invoices
        job_count = self._context.get('peppol_crons_job_count') or BATCH_SIZE
        need_retrigger = False
        params = {
            'domain': {
                'direction': 'incoming',
                'errors': False,
            }
        }
        for edi_user in self:
            params['domain']['receiver_identifier'] = edi_user.edi_identification
            try:
                # request all messages that haven't been acknowledged
                messages = edi_user._make_request(
                    url=f"{edi_user._get_server_url()}/api/peppol/1/get_all_documents",
                    params=params,
                )
            except AccountEdiProxyError as e:
                _logger.error(
                    'Error while receiving the document from Peppol Proxy: %s', e.message)
                continue

            message_uuids = [
                message['uuid']
                for message in messages.get('messages', [])
            ]
            if not message_uuids:
                continue

            company = edi_user.company_id
            journal = company.peppol_purchase_journal_id
            # use the first purchase journal if the Peppol journal is not set up
            # to create the move anyway
            if not journal:
                journal = self.env['account.journal'].search([
                    ('company_id', '=', company.id),
                    ('type', '=', 'purchase')
                ], limit=1)

            need_retrigger = need_retrigger or len(message_uuids) > job_count
            message_uuids = message_uuids[:job_count]
            proxy_acks = []

            # retrieve attachments for filtered messages
            all_messages = edi_user._make_request(
                f"{edi_user._get_server_url()}/api/peppol/1/get_document",
                {'message_uuids': message_uuids},
            )

            for uuid, content in all_messages.items():
                enc_key = content["enc_key"]
                document_content = content["document"]
                filename = content["filename"] or 'attachment'  # default to attachment, which should not usually happen
                decoded_document = edi_user._decrypt_data(document_content, enc_key)
                attachment_vals = {
                    'name': f'{filename}.xml',
                    'raw': decoded_document,
                    'type': 'binary',
                    'mimetype': 'application/xml',
                }

                try:
                    # XXX PEPPOL BACKPORT Note when backporting to 15 and before.
                    # If _create_document_from_attachment from
                    # account_edi_ubl_cii is not available, this will create an empty move
                    # with the XML document as attachment. This is not very useful.
                    # At the very minimum, the part that extracts EmbeddedDocumentBinaryObject
                    # should be recreated so users have at least a PDF attachment to
                    # work with.
                    attachment = self.env['ir.attachment'].create(attachment_vals)
                    move = journal\
                        .with_company(company)\
                        .with_context(
                            default_journal_id=journal.id,
                            default_move_type='in_invoice',
                            default_peppol_move_state=content['state'],
                            default_peppol_message_uuid=uuid,
                        )\
                        ._create_document_from_attachment(attachment.id)
                    move._message_log(body=_('Peppol document has been received successfully'))
                # pylint: disable=broad-except
                except Exception:  # noqa: BLE001
                    # if the invoice creation fails for any reason,
                    # we want to create an empty invoice with the attachment
                    move = self.env['account.move'].create({
                        'move_type': 'in_invoice',
                        'peppol_move_state': 'done',
                        'company_id': company.id,
                        'peppol_message_uuid': uuid,
                    })
                    attachment_vals.update({
                        'res_model': 'account.move',
                        'res_id': move.id,
                    })
                    self.env['ir.attachment'].create(attachment_vals)
                if 'is_in_extractable_state' in move._fields:
                    move.is_in_extractable_state = False

                proxy_acks.append(uuid)

            if not tools.config['test_enable']:
                self.env.cr.commit()  # pylint: disable=invalid-commit
            if proxy_acks:
                edi_user._make_request(
                    f"{edi_user._get_server_url()}/api/peppol/1/ack",
                    {'message_uuids': proxy_acks},
                )

        if need_retrigger:
            self.env.ref('account_peppol_backport.ir_cron_peppol_get_new_documents')._trigger()

    def _peppol_get_message_status(self):
        # Context added to not break stable policy: useful to tweak on databases processing large invoices
        job_count = self._context.get('peppol_crons_job_count') or BATCH_SIZE
        need_retrigger = False
        for edi_user in self:
            edi_user_moves = self.env['account.move'].search(
                [
                    ('peppol_move_state', '=', 'processing'),
                    ('company_id', '=', edi_user.company_id.id),
                ],
                limit=job_count + 1,
            )
            if not edi_user_moves:
                continue

            need_retrigger = need_retrigger or len(edi_user_moves) > job_count
            message_uuids = {move.peppol_message_uuid: move for move in edi_user_moves[:job_count]}
            messages_to_process = edi_user._make_request(
                f"{edi_user._get_server_url()}/api/peppol/1/get_document",
                {'message_uuids': list(message_uuids.keys())},
            )

            for uuid, content in messages_to_process.items():
                if uuid == 'error':
                    # this rare edge case can happen if the participant is not active on the proxy side
                    # in this case we can't get information about the invoices
                    edi_user_moves.peppol_move_state = 'error'
                    log_message = _("Peppol error: %s", content['message'])
                    edi_user_moves._message_log_batch(bodies={move.id: log_message for move in edi_user_moves})
                    break

                move = message_uuids[uuid]
                if content.get('error'):
                    # "Peppol request not ready" error:
                    # thrown when the IAP is still processing the message
                    if content['error'].get('code') == 702:
                        continue

                    move.peppol_move_state = 'error'
                    _logger.warning("%s", content['error'])
                    move._message_log(body=_("Peppol error: %s", content['error'].get('data', {}).get('message') or content['error']['message']))
                    continue

                move.peppol_move_state = content['state']
                move._message_log(body=_('Peppol status update: %s', content['state']))
                if move.peppol_move_state == 'done':
                    # XXX PEPPOL BACKPORT: this is not in Odoo 17
                    move.is_move_sent = True

            edi_user._make_request(
                f"{edi_user._get_server_url()}/api/peppol/1/ack",
                {'message_uuids': list(message_uuids.keys())},
            )

        if need_retrigger:
            self.env.ref('account_peppol_backport.ir_cron_peppol_get_message_status')._trigger()

    def _cron_peppol_get_participant_status(self):
        edi_users = self.search([('company_id.account_peppol_proxy_state', 'in', ['pending', 'not_verified', 'sent_verification']), ('proxy_type', '=', 'peppol')])
        edi_users._peppol_get_participant_status()

    def _peppol_get_participant_status(self):
        for edi_user in self:
            try:
                proxy_user = edi_user._make_request(
                    f"{edi_user._get_server_url()}/api/peppol/1/participant_status")
            except AccountEdiProxyError as e:
                _logger.error('Error while updating Peppol participant status: %s', e)
                continue

            state_map = {
                'active': 'active',
                'verified': 'pending',
                'rejected': 'rejected',
                'canceled': 'canceled',
            }

            if proxy_user['peppol_state'] in state_map:
                edi_user.company_id.account_peppol_proxy_state = state_map[proxy_user['peppol_state']]

    def _peppol_send_document(self, invoice, xml_string: bytes, xml_filename: str):
        """Send one invoice or credit note to the Peppol Access Point.

        Log the result of the operation in the invoice chatter. Update the
        peppol_move_state field of the invoice. Set the peppol_message_uuid
        field of the invoice if the document was sent successfully.

        The transaction *must* be committed after calling this method.
        """
        self.ensure_one()

        if invoice.peppol_move_state in ("processing", "done"):
            _logger.warning(
                "Not sending invoice %s to Peppol Access Point "
                "because it's state %s does not allow it.",
                invoice.display_name,
                invoice.peppol_move_state,
            )
            return

        partner = invoice.partner_id.commercial_partner_id
        if not partner.account_peppol_is_endpoint_valid:
            invoice.peppol_move_state = "error"
            invoice._message_log(body=_(
                "Please verify partner %s configuration in partner settings.",
                partner.display_name,
            ))
            return
        if not partner.peppol_eas or not partner.peppol_endpoint:
            invoice.peppol_move_state = "error"
            invoice._message_log(body=_(
                "The partner %s is missing Peppol EAS and/or Endpoint identifier.",
                partner.display_name,
            ))
            return

        receiver_identification = f"{partner.peppol_eas}:{partner.peppol_endpoint}"
        params = {
            "documents": [
                {
                    "filename": xml_filename,
                    "receiver": receiver_identification,
                    "ubl": b64encode(xml_string).decode(),
                }
            ]
        }

        try:
            response = self._make_request(
                f"{self._get_server_url()}/api/peppol/1/send_document",
                params=params,
            )
        except AccountEdiProxyError as e:
            invoice.peppol_move_state = "error"
            invoice._message_log(body=_("Peppol proxy error: %s", e.message))
        else:
            if response.get("error"):
                # at the moment the only error that can happen here is ParticipantNotReady error
                invoice.peppol_move_state = "error"
                invoice._message_log(body=_("Peppol error: %s", response["error"].get("message")))
            else:
                # The response only contains message uuids,
                # so we have to rely on the order to connect peppol messages to account.move.
                # In this case, we have only one invoice and response message.
                message_uuid = None
                messages = response.get("messages", [])
                if messages:
                    message_uuid = messages[0].get("message_uuid")
                if message_uuid:
                    invoice.peppol_message_uuid = message_uuid
                    invoice.peppol_move_state = "processing"
                    sent_xml_attachment = None
                    if self.env["ir.config_parameter"].sudo().get_param(
                        "account_peppol_backport.log_sent_xml"
                    ):
                        sent_xml_attachment = self.env["ir.attachment"].create({
                            "raw": xml_string,
                            "name": xml_filename,
                            "type": "binary",
                            "mimetype": "application/xml",
                            "res_model": "account.move",
                            "res_id": invoice.id,
                        })
                    invoice._message_log(body=_(
                        "The document has been sent to the Peppol Access Point for processing"
                    ), attachment_ids=[sent_xml_attachment.id] if sent_xml_attachment else [])
                else:
                    invoice.peppol_move_state = "error"
                    invoice._message_log(body=_(
                        "Peppol proxy did not return a message uuid."
                    ))
