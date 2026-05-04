# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import _, api, fields, models, modules, tools
from odoo.exceptions import UserError, ValidationError

from odoo.addons.account_edi_proxy_client_peppol.models.account_edi_proxy_user import (
    AccountEdiProxyError,
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

    # Technical field to hide country specific fields from accounting configuration
    country_code = fields.Char(related='company_id.country_id.code', readonly=True)
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
        help="If not check, you will only be able to send invoices but not receive them.",
        compute='_compute_smp_registration',
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
            error_code = response['error'].get('code')
            error_message = response['error'].get('message') or response['error'].get('data', {}).get('message')
            raise UserError(errors.get(error_code) or error_message or _('Connection error, please try again later.'))
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
    @api.depends("country_code", "company_id.country_id.code")
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

    @api.depends('account_peppol_eas', 'account_peppol_endpoint')
    def _compute_smp_registration(self):
        for config in self:
            config.account_peppol_smp_registration = False
            if config.account_peppol_eas and config.account_peppol_endpoint:
                try:
                    edi_identification = f'{config.account_peppol_eas}:{config.account_peppol_endpoint}'
                    config._check_company_on_peppol(config.company_id, edi_identification)
                    config.account_peppol_smp_registration = True
                except UserError:  # pylint: disable=except-pass
                    pass

    @handle_demo
    def _check_company_on_peppol(self, company, edi_identification):
        if (
            not company.account_peppol_migration_key
            and company.partner_id._check_peppol_participant_exists(edi_identification, check_company=True)
        ):
            participant_info = company.partner_id._peppol_lookup_participant(edi_identification)
            error_msg = _(
                "A participant with these details has already been registered on the network. "
                "If you have previously registered to a Peppol service, please deregister."
            )

            if isinstance(participant_info, str):
                error_msg += _("The Peppol service that is used is likely to be %s.", participant_info)
            raise UserError(error_msg)

    def _get_company_details(self):
        self.ensure_one()
        return {
            'peppol_company_name': self.company_id.display_name,
            'peppol_company_vat': self.company_id.vat,
            'peppol_company_street': self.company_id.street,
            'peppol_company_city': self.company_id.city,
            'peppol_company_zip': self.company_id.zip,
            'peppol_country_code': self.company_id.country_id.code,
            'peppol_phone_number': self.company_id.account_peppol_phone_number,
            'peppol_contact_email': self.company_id.account_peppol_contact_email,
            'peppol_migration_key': self.company_id.account_peppol_migration_key,
        }

    def _peppol_register_sender(self):
        self.ensure_one()
        params = {
            'company_details': self._get_company_details(),
        }
        self._call_peppol_proxy(
            endpoint='/api/peppol/1/register_sender',
            params=params,
        )
        self.company_id.account_peppol_proxy_state = 'sender'

    def _peppol_register_sender_as_receiver(self):
        self.ensure_one()
        company = self.company_id

        if company.account_peppol_proxy_state != 'sender':
            # a participant can only try registering as a receiver if they are currently a sender
            peppol_state_translated = dict(company._fields['account_peppol_proxy_state'].selection)[company.account_peppol_proxy_state]
            raise UserError(
                _('Cannot register a user with a %s application', peppol_state_translated))

        edi_proxy_client = self.env['account_edi_proxy_client_peppol.user']
        edi_identification = edi_proxy_client._get_proxy_identification(company, 'peppol')
        self._check_company_on_peppol(company, edi_identification)

        self._call_peppol_proxy(
            endpoint='/api/peppol/1/register_sender_as_receiver',
            params={
                'migration_key': company.account_peppol_migration_key,
                'supported_identifiers': list(company._peppol_supported_document_types())
            },
        )
        # once we sent the migration key over, we don't need it
        # but we need the field for future in case the user decided to migrate away from Odoo
        company.account_peppol_migration_key = False
        company.account_peppol_proxy_state = 'smp_registration'

        self.env.ref('account_peppol_backport.ir_cron_peppol_get_participant_status').method_direct_trigger()

    def _peppol_deregister_participant(self):
        self.ensure_one()

        if self.company_id.account_peppol_proxy_state == 'receiver':
            # fetch all documents and message statuses before unlinking the edi user
            # so that the invoices are acknowledged
            self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_message_status()
            self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_new_documents()
            if not tools.config['test_enable'] and not modules.module.current_test:
                self.env.cr.commit()  # pylint: disable=invalid-commit

        if self.company_id.account_peppol_proxy_state != 'not_registered':
            self._call_peppol_proxy(endpoint='/api/peppol/1/cancel_peppol_registration')

        self.company_id.account_peppol_proxy_state = 'not_registered'
        self.company_id.account_peppol_migration_key = False
        self.account_peppol_edi_user.unlink()

    # -------------------------------------------------------------------------
    # BUSINESS ACTIONS
    # -------------------------------------------------------------------------

    @handle_demo
    def button_create_peppol_proxy_user(self):
        """
        The first step of the Peppol onboarding.
        - Creates an EDI proxy user on the iap side, then the client side
        - Register the user as sender
        - Register the user as receiver if possible
        """
        self.ensure_one()

        if self.account_peppol_proxy_state in ('smp_registration', 'receiver', 'rejected'):
            raise UserError(
                _('Cannot register a user with a %s application') % self.account_peppol_proxy_state)

        if not self.account_peppol_phone_number:
            raise ValidationError(_("Please enter a mobile number to verify your application."))
        if not self.account_peppol_contact_email:
            raise ValidationError(_("Please enter a primary contact email to verify your application."))

        company = self.company_id
        edi_user = company.account_edi_proxy_client_peppol_ids.filtered(lambda u: u.proxy_type == 'peppol')
        if not edi_user:
            edi_proxy_client = self.env['account_edi_proxy_client_peppol.user']
            edi_user = edi_proxy_client.sudo()._register_proxy_user(company, 'peppol', self.account_peppol_edi_mode)

            # if there is an error when activating the participant below,
            # the client side is rolled back and the edi user is deleted on the client side
            # but remains on the proxy side.
            # it is important to keep these two in sync, so commit before activating.
            if not modules.module.current_test:
                self.env.cr.commit()  # pylint: disable=invalid-commit

        self._peppol_register_sender()

        if self.account_peppol_smp_registration:
            try:
                self._peppol_register_sender_as_receiver()
            except (UserError, AccountEdiProxyError):
                self.button_deregister_peppol_participant()
                raise

        ## success
        notifications = {
            'sender': {
                'message': _('You can now send electronic invoices via Peppol.'),
            },
            'smp_registration': {  # TODO remove in master
                'message': _('Your Peppol registration will be activated soon. You can already send invoices.'),
            },
            'receiver': {
                'message': _('You can now send and receive electronic invoices via Peppol'),
            },
        }
        state = self.company_id.account_peppol_proxy_state
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': notifications[state]['message'],
            }
        }

    @handle_demo
    def button_update_peppol_user_data(self):
        """
        Action for the user to be able to update their contact details any time
        Calls /update_user on the iap server
        """
        self.ensure_one()

        if not self.account_peppol_contact_email or not self.account_peppol_phone_number:
            raise ValidationError(_("Contact email and mobile number are required."))

        params = {
            'update_data': {
                'peppol_phone_number': self.account_peppol_phone_number,
                'peppol_contact_email': self.account_peppol_contact_email,
            }
        }

        self._call_peppol_proxy(
            endpoint='/api/peppol/1/update_user',
            params=params,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Contact details were updated."),
            }
        }

    @handle_demo
    def button_peppol_smp_registration(self):
        """
        The second (optional) step in Peppol registration.
        The user can choose to become a Receiver and officially register on the Peppol
        network, i.e. receive documents from other Peppol participants.
        """
        self.ensure_one()
        self._peppol_register_sender_as_receiver()
        if self.account_peppol_proxy_state == 'smp_registration':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Registered to receive documents via Peppol."),
                    'type': 'success',
                    'message': _("Your registration on Peppol network should be activated within a day. The updated status will be visible in Settings."),
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
        return True

    @handle_demo
    def button_migrate_peppol_registration(self):
        """
        Migrates AWAY from Odoo's SMP.
        If the user is a receiver, they need to request a migration key, generated on the IAP server.
        The migration key is then displayed in Peppol settings.
        Currently, reopening after migrating away is not supported.
        """
        raise UserError(_("This feature is deprecated. Contact Odoo support if you need a migration key."))

    @handle_demo
    def button_deregister_peppol_participant(self):
        """
        Deregister the edi user from Peppol network
        """
        self.ensure_one()

        if self.account_peppol_edi_user:
            self._peppol_deregister_participant()
        return True
