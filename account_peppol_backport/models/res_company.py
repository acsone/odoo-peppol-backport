# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
import re
import uuid
from urllib.parse import urlencode, urlparse

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from stdnum import ean, get_cc_module

from odoo import SUPERUSER_ID, _, api, fields, models, modules, tools
from odoo.exceptions import UserError, ValidationError

from odoo.addons.account_peppol_partner.models.eas_mapping import PEPPOL_LIST
from odoo.addons.account_edi_proxy_client_peppol.models.account_edi_proxy_user import (
    AccountEdiProxyError, _get_proxy_error_message,
)

from ..tools.peppol_iap_connector import PeppolIAPConnector
from ..tools.signed_tokens import hash_sign, verify_hash_signed

_logger = logging.getLogger(__name__)

try:
    import phonenumbers
except ImportError:
    phonenumbers = None


def _cc_checker(country_code, code_type):
    return lambda endpoint: get_cc_module(country_code, code_type).is_valid(endpoint)


def _re_sanitizer(expression):
    return lambda endpoint: (res.group(0) if (res := re.search(expression, endpoint)) else endpoint)


PEPPOL_ENDPOINT_RULES = {
    '0007': _cc_checker('se', 'orgnr'),
    '0088': ean.is_valid,
    '0184': _cc_checker('dk', 'cvr'),
    '0192': _cc_checker('no', 'orgnr'),
    '0208': _cc_checker('be', 'vat'),
}

PEPPOL_ENDPOINT_WARNINGS = {
    '0151': _cc_checker('au', 'abn'),
    '0201': lambda endpoint: bool(re.match('[0-9a-zA-Z]{6}$', endpoint)),
    '0210': _cc_checker('it', 'codicefiscale'),
    '0211': _cc_checker('it', 'iva'),
    '9906': _cc_checker('it', 'iva'),
    '9907': _cc_checker('it', 'codicefiscale'),
}

PEPPOL_ENDPOINT_SANITIZERS = {
    '0007': _re_sanitizer(r'\d{10}'),
    '0184': _re_sanitizer(r'\d{8}'),
    '0192': _re_sanitizer(r'\d{9}'),
    '0208': _re_sanitizer(r'\d{10}'),
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_peppol_contact_email = fields.Char(
        string='Primary contact email',
        compute='_compute_account_peppol_contact_email', store=True, readonly=False,
        help='Primary contact email for Peppol-related communication',
    )
    account_peppol_migration_key = fields.Char(string="Migration Key")
    account_peppol_phone_number = fields.Char(
        string='Mobile number (for validation)',
        compute='_compute_account_peppol_phone_number', store=True, readonly=False,
        help='Contact mobile number for Peppol registration',
    )
    account_peppol_proxy_state = fields.Selection(
        selection=[
            ('not_registered', 'Not registered'),
            ('in_verification', 'In verification'),
            ('sender', 'Can send but not receive'),
            ('smp_registration', 'Can send, pending registration to receive'),
            ('receiver', 'Can send and receive'),
            ('rejected', 'Rejected'),
        ],
        string='PEPPOL status', required=True, default='not_registered',
    )
    is_account_peppol_participant = fields.Boolean(string='PEPPOL Participant')
    peppol_eas = fields.Selection(related='partner_id.peppol_eas', readonly=False)
    peppol_endpoint = fields.Char(related='partner_id.peppol_endpoint', readonly=False)
    peppol_purchase_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='PEPPOL Purchase Journal',
        domain=[('type', '=', 'purchase')],
        compute='_compute_peppol_purchase_journal_id', store=True, readonly=False,
        inverse='_inverse_peppol_purchase_journal_id',
    )
    peppol_sender_only = fields.Boolean(string='PEPPOL Sender Only', default=False)
    peppol_connect_nonce = fields.Char(copy=False, groups='base.group_system')

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _sanitize_peppol_phone_number(self, phone_number=None):
        self.ensure_one()

        error_message = _(
            "Please enter the mobile number in the correct international format.\n"
            "For example: +32123456789, where +32 is the country code.\n"
            "Currently, only European countries are supported.")

        if not phonenumbers:
            raise ValidationError(_("Please install the phonenumbers library."))

        phone_number = phone_number or self.account_peppol_phone_number
        if not phone_number:
            return

        if not phone_number.startswith('+'):
            phone_number = f'+{phone_number}'

        try:
            phone_nbr = phonenumbers.parse(phone_number)
        except phonenumbers.phonenumberutil.NumberParseException as e:
            raise ValidationError(error_message) from e

        country_code = phonenumbers.phonenumberutil.region_code_for_number(phone_nbr)
        if country_code not in PEPPOL_LIST or not phonenumbers.is_valid_number(phone_nbr):
            raise ValidationError(error_message)

    def _check_peppol_endpoint_number(self, warning=False):
        self.ensure_one()
        peppol_dict = PEPPOL_ENDPOINT_WARNINGS if warning else PEPPOL_ENDPOINT_RULES

        return True if (endpoint_rule := peppol_dict.get(self.peppol_eas)) is None else endpoint_rule(self.peppol_endpoint)

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('account_peppol_phone_number')
    def _check_account_peppol_phone_number(self):
        for company in self:
            if company.account_peppol_phone_number:
                company._sanitize_peppol_phone_number()

    @api.constrains('peppol_endpoint')
    def _check_peppol_endpoint(self):
        for company in self:
            if not company.peppol_endpoint:
                continue
            if not company._check_peppol_endpoint_number(PEPPOL_ENDPOINT_RULES):
                raise ValidationError(_("The Peppol endpoint identification number is not correct."))

    @api.constrains('peppol_purchase_journal_id')
    def _check_peppol_purchase_journal_id(self):
        for company in self:
            if company.peppol_purchase_journal_id and company.peppol_purchase_journal_id.type != 'purchase':
                raise ValidationError(_("A purchase journal must be used to receive Peppol documents."))

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('account_peppol_proxy_state')
    def _compute_peppol_purchase_journal_id(self):
        for company in self:
            if not company.peppol_purchase_journal_id and company.account_peppol_proxy_state in ('smp_registration', 'receiver'):
                company.peppol_purchase_journal_id = self.env['account.journal'].search([
                    ('company_id', '=', company.id),
                    ('type', '=', 'purchase'),
                ], limit=1)
                company.peppol_purchase_journal_id.is_peppol_journal = True
            else:
                company.peppol_purchase_journal_id = company.peppol_purchase_journal_id

    def _inverse_peppol_purchase_journal_id(self):
        for company in self:
            # This avoid having 2 or more journals from the same company with
            # `is_peppol_journal` set to True (which could occur after changes).
            journals_to_reset = self.env['account.journal'].search([
                ('company_id', '=', company.id),
                ('is_peppol_journal', '=', True),
            ])
            journals_to_reset.is_peppol_journal = False
            company.peppol_purchase_journal_id.is_peppol_journal = True

    @api.depends('email')
    def _compute_account_peppol_contact_email(self):
        for company in self:
            if not company.account_peppol_contact_email:
                company.account_peppol_contact_email = company.email

    @api.depends('phone')
    def _compute_account_peppol_phone_number(self):
        for company in self:
            if not company.account_peppol_phone_number:
                try:
                    # precompute only if it's a valid phone number
                    company._sanitize_peppol_phone_number(company.phone)
                    company.account_peppol_phone_number = company.phone
                except ValidationError:
                    continue

    # -------------------------------------------------------------------------
    # LOW-LEVEL METHODS
    # -------------------------------------------------------------------------

    @api.model
    def _sanitize_peppol_endpoint(self, vals, eas=False, endpoint=False):
        # TODO: remove in master
        if not (peppol_eas := vals.get('peppol_eas', eas)) or not (peppol_endpoint := vals.get('peppol_endpoint', endpoint)):
            return vals

        if sanitizer := PEPPOL_ENDPOINT_SANITIZERS.get(peppol_eas):
            vals['peppol_endpoint'] = sanitizer(peppol_endpoint)

        return vals

    @api.model
    def _sanitize_peppol_endpoint_in_values(self, values):
        eas = values.get('peppol_eas')
        endpoint = values.get('peppol_endpoint')
        if not eas or not endpoint:
            return
        if sanitizer := PEPPOL_ENDPOINT_SANITIZERS.get(eas):
            new_endpoint = sanitizer(endpoint)
            if new_endpoint:
                values['peppol_endpoint'] = new_endpoint

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sanitize_peppol_endpoint_in_values(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sanitize_peppol_endpoint_in_values(vals)
        return super().write(vals)

    def _peppol_modules_document_types(self):
        """Override this function to add supported document types as modules are installed.

        :returns: dictionary of the form: {module_name: [(document identifier, document_name)]}
        """
        return {
            'default': {
                "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1":
                    "Peppol BIS Billing UBL Invoice V3",
                "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1":
                    "Peppol BIS Billing UBL CreditNote V3",
                "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:nen.nl:nlcius:v1.0::2.1":
                    "SI-UBL 2.0 Invoice",
                "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:fdc:nen.nl:nlcius:v1.0::2.1":
                    "SI-UBL 2.0 CreditNote",
                "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:sg:3.0::2.1":
                    "SG Peppol BIS Billing 3.0 Invoice",
                "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:sg:3.0::2.1":
                    "SG Peppol BIS Billing 3.0 Credit Note",
                "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0::2.1":
                    "XRechnung UBL Invoice V2.0",
                "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0::2.1":
                    "XRechnung UBL CreditNote V2.0",
                "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:aunz:3.0::2.1":
                    "AU-NZ Peppol BIS Billing 3.0 Invoice",
                "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:aunz:3.0::2.1":
                    "AU-NZ Peppol BIS Billing 3.0 CreditNote",
            }
        }

    def _peppol_supported_document_types(self):
        """Returns a flattened dictionary of all supported document types."""
        return {
            identifier: document_name
            for module, identifiers in self._peppol_modules_document_types().items()
            for identifier, document_name in identifiers.items()
        }

    def _get_peppol_edi_mode(self):
        self.ensure_one()
        config_param = self.env['ir.config_parameter'].sudo().get_param('account_peppol.edi.mode')
        # by design, we can only have zero or one proxy user per company with type Peppol
        peppol_user = self.sudo().account_edi_proxy_client_peppol_ids.filtered(lambda u: u.proxy_type == 'peppol')
        return peppol_user.edi_mode or config_param or 'prod'

    def _peppol_generate_connect_token(self, peppol_identifier):
        self.ensure_one()
        nonce = uuid.uuid4().hex
        self.sudo().peppol_connect_nonce = nonce
        return hash_sign(self.sudo().env, 'account_peppol_connect', {
            'peppol_identifier': peppol_identifier,
            'company_id': self.id,
            'user_id': self.env.uid,
            'db_name': self.env.cr.dbname,
            'edi_mode': self._get_peppol_edi_mode(),
            'sender_only': self.peppol_sender_only,
            'nonce': nonce,
        }, expiration_hours=24 * 7 * 2)

    @api.model
    def _peppol_decode_connect_token(self, token):
        try:
            values = verify_hash_signed(self.sudo().env, 'account_peppol_connect', token)
        except (ValueError, TypeError, UnicodeError):
            return None
        if not isinstance(values, dict) or values.get('db_name') != self.env.cr.dbname:
            return None
        if not isinstance(values.get('company_id'), int) or not isinstance(values.get('user_id'), int):
            return None
        company = self.sudo().browse(values['company_id']).exists()
        user = self.env['res.users'].sudo().browse(values['user_id']).exists()
        if not company or not user:
            return None
        if user.id != SUPERUSER_ID and (
            not user.active or company not in user.company_ids
            or not (user.has_group('base.group_system') or user.has_group('account.group_account_manager'))
        ):
            return None
        identifier = '%s:%s' % (company.peppol_eas, company.peppol_endpoint)
        if (
            values.get('peppol_identifier') != identifier.lower()
            or values.get('edi_mode') != company._get_peppol_edi_mode()
            or values.get('sender_only') != company.peppol_sender_only
            or not values.get('nonce')
        ):
            return None
        return dict(values, company=company, user=user)

    def _peppol_can_connect(self, peppol_identifier):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM res_company WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_cache(['account_peppol_proxy_state'])
        if self.account_peppol_proxy_state not in ('not_registered', 'in_verification'):
            raise UserError(_('This company already has a Peppol connection.'))
        base_url = self.get_base_url().rstrip('/')
        token = self._peppol_generate_connect_token(peppol_identifier)
        database_query = '?' + urlencode({'db': self.env.cr.dbname})
        values = PeppolIAPConnector(self).can_connect(
            peppol_identifier=peppol_identifier,
            db_uuid=self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            callback_url=base_url + '/peppol/authentication/callback' + database_query,
            webhook_url=base_url + '/peppol/authentication/webhook' + database_query,
            connect_token=token,
            contact_email=self.account_peppol_contact_email,
        )
        return dict(values, _connect_token=token)

    @api.model
    def _peppol_select_kyc_url(self, values):
        if not values:
            raise UserError(_('Could not connect to the Peppol proxy.'))
        if values.get('identifier_invalid'):
            raise UserError(_('The company identifier is not valid for Peppol. Please check the EAS and endpoint.'))
        if values.get('db_invalid'):
            raise UserError(_('The database you are trying to connect to is not suitable for Peppol.'))
        if values.get('auth_required') is False:
            return None
        if values.get('auth_required') is not True:
            raise UserError(_('The Peppol proxy returned an invalid authorization response.'))
        if values.get('kyc_error'):
            raise UserError(_('Cannot initiate KYC for this identification scheme.'))
        auths = values.get('available_auths') or {}
        if not isinstance(auths, dict):
            raise UserError(_('The Peppol proxy returned an invalid authorization response.'))
        auth = auths.get('generic') or next(iter(auths.values()), None)
        if not isinstance(auth, dict) or not isinstance(auth.get('authorization_url'), str):
            raise UserError(_('Authentication is required but not available. Please contact Odoo support.'))
        if urlparse(auth['authorization_url']).scheme != 'https':
            raise UserError(_('The Peppol proxy returned an invalid authorization URL.'))
        return auth['authorization_url']

    def _peppol_create_connection(self, peppol_identifier, auth_token=None):
        """use Odoo 17's REST connection API and existing binary private-key storage"""
        self.ensure_one()
        mode = self._get_peppol_edi_mode()
        client = self.env['account_edi_proxy_client_peppol.user'].sudo()
        other_company = client.search([
            ('proxy_type', '=', 'peppol'), ('edi_mode', '=', mode),
            ('edi_identification', '=', peppol_identifier), ('company_id', '!=', self.id),
        ], limit=1)
        if other_company:
            raise UserError(_('Another company already has an active connection for this Peppol identifier.'))
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        private_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        )
        public_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        response = PeppolIAPConnector(self).create_connection(
            peppol_identifier=peppol_identifier,
            db_uuid=self.env['ir.config_parameter'].sudo().get_param('database.uuid'),
            public_key=base64.b64encode(public_pem).decode(),
            auth_token=auth_token,
            peppol_company_name=self.display_name,
            peppol_company_vat=self.vat,
            peppol_company_street=self.street,
            peppol_company_city=self.city,
            peppol_company_zip=self.zip,
            peppol_country_code=self.country_id.code,
            peppol_phone_number=self.account_peppol_phone_number,
            peppol_contact_email=self.account_peppol_contact_email,
            peppol_migration_key=self.sudo().account_peppol_migration_key,
            supported_identifiers=list(self._peppol_supported_document_types()),
        )
        if not response.get('id_client') or not response.get('refresh_token'):
            raise UserError(_('The Peppol proxy did not return connection credentials.'))
        existing = client.with_context(active_test=False).search([
            ('id_client', '=', response['id_client']),
        ], limit=1)
        if existing and (existing.company_id != self or existing.proxy_type != 'peppol' or existing.edi_mode != mode):
            raise UserError(_('The returned Peppol connection belongs to another company or environment.'))
        # archive only after authorization succeeds, keep old keys during KYC
        client.search([('company_id', '=', self.id), ('proxy_type', '=', 'peppol')]).active = False
        values = {
            'id_client': response['id_client'], 'company_id': self.id,
            'proxy_type': 'peppol', 'edi_mode': mode, 'edi_identification': peppol_identifier,
            'private_key': base64.b64encode(private_pem), 'refresh_token': response['refresh_token'],
            'active': True,
        }
        if existing:
            existing.write(values)
            edi_user = existing
        else:
            edi_user = client.create(values)
        state = response.get('peppol_state')
        if state not in ('sender', 'smp_registration', 'receiver', 'rejected'):
            _logger.warning('Unknown Peppol connection state for company %s: %s', self.id, state)
            state = 'not_registered'
        self.sudo().write({
            'account_peppol_proxy_state': state, 'account_peppol_migration_key': False,
            'peppol_connect_nonce': False,
        })
        # the connection exists on IAP now, preserve its credentials before further calls
        if not tools.config['test_enable'] and not modules.module.current_test:
            self.env.cr.commit()  # pylint: disable=invalid-commit
        self._peppol_apply_sender_only(edi_user)
        if self.account_peppol_proxy_state == 'smp_registration':
            self.env.ref('account_peppol_backport.ir_cron_peppol_get_participant_status')._trigger()
        return edi_user

    def _peppol_apply_sender_only(self, edi_user):
        self.ensure_one()
        if self.peppol_sender_only and self.account_peppol_proxy_state in ('receiver', 'smp_registration'):
            if not edi_user:
                raise UserError(_('No active Peppol connection was found for this company.'))
            try:
                response = edi_user._make_request(edi_user._get_server_url() + '/api/peppol/1/unregister_to_sender')
            except AccountEdiProxyError as exc:
                raise UserError(exc.message) from exc
            if response.get('error'):
                raise UserError(_get_proxy_error_message(response['error']))
            self.account_peppol_proxy_state = 'sender'

    def _peppol_complete_connection(self, token, auth_token=None):
        data = self._peppol_decode_connect_token(token)
        if not data or data['company'] != self:
            raise UserError(_('This Peppol authorization is invalid or expired. Please activate Peppol again.'))
        # serialize the browser callback and webhook, provisioning is not idempotent on IAP
        self.env.cr.execute('SELECT id FROM res_company WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_cache([
            'peppol_connect_nonce', 'account_edi_proxy_client_peppol_ids',
            'account_peppol_proxy_state', 'peppol_eas', 'peppol_endpoint', 'peppol_sender_only',
        ])
        data = self._peppol_decode_connect_token(token)
        if not data:
            raise UserError(_('The company details changed. Please activate Peppol again.'))
        nonce = self.sudo().peppol_connect_nonce
        if nonce != data['nonce']:
            users = self.sudo().account_edi_proxy_client_peppol_ids.filtered(
                lambda u: u.proxy_type == 'peppol' and u.edi_mode == data['edi_mode']
                and u.edi_identification == data['peppol_identifier'],
            )
            if not nonce and users and self.account_peppol_proxy_state in ('sender', 'smp_registration', 'receiver', 'rejected'):
                self._peppol_apply_sender_only(users)
                return users
            raise UserError(_('This Peppol authorization was replaced. Please use the latest authorization link.'))
        return self.with_company(self)._peppol_create_connection(data['peppol_identifier'], auth_token=auth_token)

    def _peppol_cancel_connection(self, token):
        data = self._peppol_decode_connect_token(token)
        if not data or data['company'] != self:
            raise UserError(_('This Peppol authorization is invalid or expired.'))
        self.env.cr.execute('SELECT id FROM res_company WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_cache(['peppol_connect_nonce'])
        if self.sudo().peppol_connect_nonce == data['nonce']:
            self.sudo().write({'peppol_connect_nonce': False, 'account_peppol_proxy_state': 'not_registered'})
