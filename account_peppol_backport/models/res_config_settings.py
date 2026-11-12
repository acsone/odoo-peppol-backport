# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models, modules, tools
from odoo.exceptions import UserError, ValidationError

from odoo.addons.account_edi_proxy_client_peppol.models.account_edi_proxy_user import (
    AccountEdiProxyError,
    _get_proxy_error_message,
)
from odoo.addons.account_peppol_partner.models.eas_mapping import (
    EAS_MAPPING,
    PEPPOL_LIST,
)
from ..tools.demo_utils import handle_demo

# at the moment, only European countries are accepted
ALLOWED_COUNTRIES = set(EAS_MAPPING.keys()) - {'AU', 'SG', 'NZ'}


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_account_peppol_eligible = fields.Boolean(
        string="PEPPOL eligible",
        compute="_compute_is_account_peppol_eligible",
    )  # technical field used for showing the Peppol settings conditionally
    account_peppol_edi_user = fields.Many2one(
        comodel_name='account_edi_proxy_client_peppol.user',
        string='EDI user',
        compute='_compute_account_peppol_edi_user',
    )
    account_peppol_contact_email = fields.Char(related='company_id.account_peppol_contact_email', readonly=False)
    account_peppol_eas = fields.Selection(related='company_id.peppol_eas', readonly=False)
    account_peppol_edi_identification = fields.Char(related='account_peppol_edi_user.edi_identification')
    account_peppol_endpoint = fields.Char(related='company_id.peppol_endpoint', readonly=False)
    account_peppol_endpoint_warning = fields.Char(
        string="Warning",
        compute="_compute_account_peppol_endpoint_warning",
    )
    account_peppol_migration_key = fields.Char(related='company_id.account_peppol_migration_key', readonly=False)
    account_peppol_phone_number = fields.Char(related='company_id.account_peppol_phone_number', readonly=False)
    account_peppol_proxy_state = fields.Selection(related='company_id.account_peppol_proxy_state', readonly=False)
    account_peppol_purchase_journal_id = fields.Many2one(related='company_id.peppol_purchase_journal_id', readonly=False)
    account_peppol_verification_code = fields.Char(related='account_peppol_edi_user.peppol_verification_code', readonly=False)
    account_peppol_sender_only = fields.Boolean(related='company_id.peppol_sender_only', readonly=False)
    is_account_peppol_participant = fields.Boolean(
        string='Use PEPPOL',
        related='company_id.is_account_peppol_participant', readonly=False,
        help='Register as a PEPPOL user',
    )
    account_peppol_edi_mode = fields.Selection(
        selection=[('demo', 'Demo'), ('test', 'Test'), ('prod', 'Live')],
        compute='_compute_account_peppol_edi_mode',
        inverse='_inverse_account_peppol_edi_mode',
        readonly=False,
    )
    account_peppol_mode_constraint = fields.Selection(
        selection=[('demo', 'Demo'), ('test', 'Test'), ('prod', 'Live')],
        compute='_compute_account_peppol_mode_constraint',
        help="Using the config params, this field specifies which edi modes may be selected from the UI"
    )
    account_peppol_smp_registration = fields.Boolean(
        string='Register as a receiver',
        compute='_compute_smp_registration',
        help='Reception is enabled when Sender Only Mode is disabled and the endpoint is available.',
    )

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _call_peppol_proxy(self, endpoint, params=None, edi_user=None):
        errors = {
            'code_incorrect': _('The verification code is not correct'),
            'code_expired': _('This verification code has expired. Please request a new one.'),
            'too_many_attempts': _('Too many attempts to request an SMS code. Please try again later.'),
        }

        if not edi_user:
            edi_user = self.company_id.account_edi_proxy_client_peppol_ids.filtered(lambda u: u.proxy_type == 'peppol')

        params = params or {}
        try:
            response = edi_user._make_request(
                f"{edi_user._get_server_url()}{endpoint}",
                params=params,
            )
        except AccountEdiProxyError as e:
            raise UserError(e.message) from e

        if 'error' in response:
            error = response['error']
            error_code = error.get('code') if isinstance(error, dict) else None
            raise UserError(errors.get(error_code) or _get_proxy_error_message(error))
        return response

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange('account_peppol_endpoint')
    def _onchange_account_peppol_endpoint(self):
        if self.account_peppol_endpoint:
            self.account_peppol_endpoint = ''.join(char for char in self.account_peppol_endpoint if char.isalnum())

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    @api.depends("country_code")
    def _compute_is_account_peppol_eligible(self):
        # we want to show Peppol settings only to customers that are eligible for Peppol,
        # except countries that are not in Europe
        for config in self:
            config.is_account_peppol_eligible = config.country_code in PEPPOL_LIST

    @api.depends('is_account_peppol_eligible', 'account_peppol_edi_user')
    def _compute_account_peppol_mode_constraint(self):
        mode_constraint = self.env['ir.config_parameter'].sudo().get_param('account_peppol.mode_constraint')
        trial_param = self.env['ir.config_parameter'].sudo().get_param('saas_trial.confirm_token')
        self.account_peppol_mode_constraint = trial_param and 'demo' or mode_constraint or 'prod'

    @api.depends('is_account_peppol_eligible', 'account_peppol_edi_user')
    def _compute_account_peppol_edi_mode(self):
        for config in self:
            config.account_peppol_edi_mode = config.company_id._get_peppol_edi_mode()

    def _inverse_account_peppol_edi_mode(self):
        for config in self:
            if not config.account_peppol_edi_user and config.account_peppol_edi_mode:
                self.env['ir.config_parameter'].sudo().set_param('account_peppol.edi.mode', config.account_peppol_edi_mode)
                return

    @api.depends("company_id.account_edi_proxy_client_peppol_ids")
    def _compute_account_peppol_edi_user(self):
        for config in self:
            config.account_peppol_edi_user = config.company_id.account_edi_proxy_client_peppol_ids.filtered(
                lambda u: u.proxy_type == 'peppol')

    @api.depends('account_peppol_eas', 'account_peppol_endpoint')
    def _compute_account_peppol_endpoint_warning(self):
        for config in self:
            if (
                not config.account_peppol_eas
                or config.company_id._check_peppol_endpoint_number(warning=True)
            ):
                config.account_peppol_endpoint_warning = False
            else:
                config.account_peppol_endpoint_warning = _("The endpoint number might not be correct. "
                                                           "Please check if you entered the right identification number.")

    # -------------------------------------------------------------------------
    # BUSINESS ACTIONS
    # -------------------------------------------------------------------------

    @api.depends(
        'account_peppol_eas', 'account_peppol_endpoint',
        'account_peppol_migration_key', 'account_peppol_sender_only',
        'account_peppol_edi_mode',
    )
    def _compute_smp_registration(self):
        for config in self:
            config.account_peppol_smp_registration = False
            if (
                config.account_peppol_sender_only
                or not config.account_peppol_eas
                or not config.account_peppol_endpoint
            ):
                continue
            identification = '%s:%s' % (
                config.account_peppol_eas, config.account_peppol_endpoint,
            )
            try:
                config._check_company_on_peppol(config.company_id, identification)
            except UserError:
                continue
            config.account_peppol_smp_registration = True

    @handle_demo
    def _check_company_on_peppol(self, company, edi_identification):
        if company.account_peppol_migration_key:
            return
        participant_info = company.partner_id.with_company(company)._check_peppol_participant_exists(
            edi_identification, check_company=True,
        )
        if participant_info:
            message = _(
                "A participant with these details has already been registered on the network. "
                "You can register as sender only, or provide a migration key to receive documents."
            )
            if isinstance(participant_info, str):
                message += _(" The Peppol service that is used is likely to be %s.", participant_info)
            raise UserError(message)

    def _get_company_details(self):
        self.ensure_one()
        company = self.company_id
        return {
            'peppol_company_name': company.display_name,
            'peppol_company_vat': company.vat,
            'peppol_company_street': company.street,
            'peppol_company_city': company.city,
            'peppol_company_zip': company.zip,
            'peppol_country_code': company.country_id.code,
            'peppol_phone_number': company.account_peppol_phone_number,
            'peppol_contact_email': company.account_peppol_contact_email,
            'peppol_migration_key': company.account_peppol_migration_key,
        }

    def _peppol_register_sender(self):
        self.ensure_one()
        self._call_peppol_proxy(
            endpoint='/api/peppol/1/register_sender',
            params={'company_details': self._get_company_details()},
        )
        self.company_id.account_peppol_proxy_state = 'sender'

    def _peppol_register_sender_as_receiver(self):
        self.ensure_one()
        company = self.company_id
        if company.account_peppol_proxy_state != 'sender':
            raise UserError(_("Only a registered sender can enable reception."))
        if company.peppol_sender_only:
            raise UserError(_("Disable Sender Only Mode before enabling reception."))
        edi_client = self.env['account_edi_proxy_client_peppol.user']
        identification = edi_client._get_proxy_identification(company, 'peppol')
        self._check_company_on_peppol(company, identification)
        self._call_peppol_proxy(
            endpoint='/api/peppol/1/register_sender_as_receiver',
            params={
                'migration_key': company.account_peppol_migration_key,
                'supported_identifiers': list(company._peppol_supported_document_types()),
            },
        )
        company.account_peppol_migration_key = False
        company.account_peppol_proxy_state = 'smp_registration'
        self.env.ref('account_peppol_backport.ir_cron_peppol_get_participant_status')._trigger(
            at=fields.Datetime.now() + timedelta(hours=1),
        )

    def _peppol_deregister_participant(self):
        self.ensure_one()
        edi_user = self.account_peppol_edi_user
        if self.company_id.account_peppol_proxy_state == 'receiver':
            edi_user._peppol_get_message_status()
            edi_user._peppol_get_new_documents()
            if not tools.config['test_enable'] and not modules.module.current_test:
                self.env.cr.commit()  # pylint: disable=invalid-commit
        if self.company_id.account_peppol_proxy_state != 'not_registered':
            self._call_peppol_proxy(endpoint='/api/peppol/1/cancel_peppol_registration')
        self.company_id.account_peppol_proxy_state = 'not_registered'
        self.company_id.account_peppol_migration_key = False
        edi_user.unlink()

    @handle_demo
    def button_create_peppol_proxy_user(self):
        """register as sender, then optionally request reception without SMS verification"""
        self.ensure_one()
        if self.account_peppol_edi_mode != 'demo':
            return self.button_register_with_kyc()
        self = self.with_company(self.company_id)
        company = self.company_id
        if company.account_peppol_proxy_state not in ('not_registered', 'sender'):
            raise UserError(
                _('Cannot register a user with a %s application', company.account_peppol_proxy_state),
            )
        if not self.account_peppol_phone_number:
            raise ValidationError(_("Please enter a mobile number to verify your application."))
        if not self.account_peppol_contact_email:
            raise ValidationError(_("Please enter a primary contact email to verify your application."))
        company.partner_id._check_peppol_eas()
        edi_client = self.env['account_edi_proxy_client_peppol.user']
        edi_user = self.account_peppol_edi_user
        if not edi_user:
            edi_client.sudo()._register_proxy_user(company, 'peppol', self.account_peppol_edi_mode)
            # preserve the proxy credentials if a later remote call fails
            if not tools.config['test_enable'] and not modules.module.current_test:
                self.env.cr.commit()  # pylint: disable=invalid-commit
        if company.account_peppol_proxy_state == 'not_registered':
            self._peppol_register_sender()
            # keep the valid sender connection if reception cannot be enabled
            if not tools.config['test_enable'] and not modules.module.current_test:
                self.env.cr.commit()  # pylint: disable=invalid-commit
        if self.account_peppol_smp_registration:
            self._peppol_register_sender_as_receiver()
        messages = {
            'sender': _('You can now send electronic invoices via Peppol.'),
            'smp_registration': _(
                'Your Peppol registration will be activated soon. You can already send invoices.'
            ),
            'receiver': _('You can now send and receive electronic invoices via Peppol.'),
        }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': messages[company.account_peppol_proxy_state],
            },
        }

    def button_register_with_kyc(self):
        """Odoo 17's active registration path, the old create_user route is deprecated"""
        self.ensure_one()
        if self.account_peppol_edi_mode == 'demo':
            return self.button_create_peppol_proxy_user()
        company = self.company_id.with_company(self.company_id)
        user = self.env.user
        if user.id != SUPERUSER_ID and (company not in user.company_ids or not (
            user.has_group('base.group_system') or user.has_group('account.group_account_manager')
        )):
            raise UserError(_('You are not allowed to register this company on Peppol.'))
        if company.account_peppol_proxy_state not in ('not_registered', 'in_verification'):
            raise UserError(_('Cannot register a user with a %s application', company.account_peppol_proxy_state))
        if not self.account_peppol_phone_number or not self.account_peppol_contact_email:
            raise ValidationError(_('Contact email and mobile number are required.'))
        company.partner_id._check_peppol_eas()
        identifier = self.env['account_edi_proxy_client_peppol.user']._get_proxy_identification(company, 'peppol').lower()
        connection_values = company._peppol_can_connect(identifier)
        authorization_url = company._peppol_select_kyc_url(connection_values)
        token = connection_values['_connect_token']
        if authorization_url:
            company.account_peppol_proxy_state = 'in_verification'
            return {'type': 'ir.actions.act_url', 'url': authorization_url, 'target': 'self'}
        company._peppol_complete_connection(token)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def button_peppol_reset_to_sender(self):
        self.ensure_one()
        self.company_id.peppol_sender_only = True
        self.company_id._peppol_apply_sender_only(self.account_peppol_edi_user)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @handle_demo
    def button_update_peppol_user_data(self):
        self.ensure_one()
        if not self.account_peppol_contact_email or not self.account_peppol_phone_number:
            raise ValidationError(_("Contact email and mobile number are required."))
        self._call_peppol_proxy(
            endpoint='/api/peppol/1/update_user',
            params={'update_data': {
                'peppol_phone_number': self.account_peppol_phone_number,
                'peppol_contact_email': self.account_peppol_contact_email,
            }},
        )

    @handle_demo
    def button_peppol_smp_registration(self):
        self.ensure_one()
        self._peppol_register_sender_as_receiver()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Your registration to receive Peppol documents is pending.'),
            },
        }

    @handle_demo
    def button_migrate_peppol_registration(self):
        raise UserError(_("This feature is deprecated. Contact Odoo support if you need a migration key."))

    @handle_demo
    def button_deregister_peppol_participant(self):
        self.ensure_one()
        if self.account_peppol_edi_user:
            self._peppol_deregister_participant()
        return True
