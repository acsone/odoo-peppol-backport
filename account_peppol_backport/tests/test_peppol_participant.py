import json
from base64 import b64decode
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

from freezegun import freeze_time
from requests import PreparedRequest, Response, Session

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from .utils import RequestHandlerTransactionCase
from ..tools.signed_tokens import hash_sign, verify_hash_signed

ID_CLIENT = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
FAKE_UUID = 'yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy'
PDF_FILE_PATH = 'account_peppol/tests/assets/peppol_identification_test.pdf'

@freeze_time('2023-01-01')
@tagged('-at_install', 'post_install')
class TestPeppolParticipant(RequestHandlerTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('account_peppol.edi.mode', 'test')

    @classmethod
    def _get_mock_responses(cls, reject=False):
        return {
            '/api/peppol/2/participant_status': {
                'result': {
                    'peppol_state': 'receiver' if not reject else 'rejected',
                }
            },
            '/api/peppol/1/register_sender': {'result': {}},
            '/api/peppol/1/register_sender_as_receiver': {'result': {}},
            '/api/peppol/1/cancel_peppol_registration': {'result': {}},
            '/api/peppol/1/unregister_to_sender': {'result': {}},
            '/api/peppol/1/update_user': {'result': {}},
            '/api/peppol/1/migrate_peppol_registration': {
                'result': {
                    'migration_key': 'test_key',
                }
            },
        }

    @classmethod
    def _request_handler(cls, s: Session, r: PreparedRequest, /, **kw):
        response = Response()
        response.status_code = 200
        if r.method == 'GET' and r.path_url.startswith('/api/peppol/2/can_connect?'):
            cls.can_connect_params = {
                key: values[0] for key, values in parse_qs(urlparse(r.url).query).items()
            }
            response._content = json.dumps({
                'auth_required': bool(cls.env.context.get('auth_required')),
                'available_auths': {
                    'generic': {'authorization_url': 'https://peppol.test.odoo.com/authorize/test'},
                },
            }).encode()
            return response
        if r.path_url == '/api/peppol/2/connect':
            cls.registration_params = json.loads(r.body)
            cls.receiver_params = cls.registration_params
            identifier = cls.registration_params['peppol_identifier']
            state = 'sender' if identifier.startswith('0208:') and not cls.registration_params.get('peppol_migration_key') else 'smp_registration'
            response._content = json.dumps({
                'id_client': ID_CLIENT,
                'refresh_token': FAKE_UUID,
                'peppol_state': state,
            }).encode()
            return response
        if r.path_url == '/iap/account_edi/2/create_user':
            raise AssertionError('Peppol registration must not call deprecated create_user')
        if r.method == 'GET' and r.path_url.startswith('/api/peppol/1/lookup?'):
            identifier = parse_qs(urlparse(r.url).query)['peppol_identifier'][0]
            response._content = json.dumps({
                'result': {'identifier': identifier, 'services': []}
                if identifier == '0208:0000000000' else False,
            }).encode()
            return response
        if r.url.endswith('/iso6523-actorid-upis%3A%3A9925%3A0000000000'):
            response.status_code = 404
            return response

        if r.url.endswith('/iso6523-actorid-upis%3A%3A0208%3A0000000000'):
            response._content = b'<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<smp:ServiceGroup xmlns:wsa="http://www.w3.org/2005/08/addressing" xmlns:id="http://busdox.org/transport/identifiers/1.0/" xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:smp="http://busdox.org/serviceMetadata/publishing/1.0/"><id:ParticipantIdentifier scheme="iso6523-actorid-upis">0208:0000000000</id:ParticipantIdentifier></smp:ServiceGroup>'
            return response

        url = r.path_url
        body = json.loads(r.body)
        if url == '/api/peppol/1/register_sender_as_receiver':
            cls.receiver_params = body['params']
            if cls.env.context.get('receiver_error'):
                response.json = lambda: {'result': {'error': {
                    'code': 'registration_rejected',
                    'message': 'Reception could not be enabled',
                }}}
                return response
        responses = cls._get_mock_responses(cls.env.context.get('reject'))
        if (
            url == '/api/peppol/1/register_sender_as_receiver'
            and cls.env.context.get('migrate_to')
            and not body['params']['migration_key']
        ):
            raise UserError('No migration key was provided')  # pylint: disable=translation-required

        if cls.env.context.get('migrated_away'):
            response.json = lambda: {
                'result': {
                    'proxy_error': {
                        'code': 'no_such_user',
                        'message': 'The user does not exist on the proxy',
                    }
                }
            }
            return response

        if url not in responses:
            return super()._request_handler(s, r, **kw)
        response.json = lambda: responses[url]
        return response

    def _get_participant_vals(self):
        return {
            'account_peppol_eas': '9925',
            'account_peppol_endpoint': '0000000000',
            'account_peppol_phone_number': '+32483123456',
            'account_peppol_contact_email': 'yourcompany@test.example.com',
        }

    @contextmanager
    def _set_context(self, other_context):
        previous_context = self.env.context
        self.env.context = dict(previous_context, **other_context)
        try:
            yield self
        finally:
            self.env.context = previous_context

    def test_create_participant_missing_data(self):
        # creating a participant without eas/endpoint/document should not be possible
        settings = self.env['res.config.settings'].create({
            'account_peppol_eas': False,
            'account_peppol_endpoint': False,
        })
        with self.assertRaises(ValidationError), self.cr.savepoint():
            settings.button_create_peppol_proxy_user()

    def test_existing_participant_registers_as_sender_only(self):
        vals = self._get_participant_vals()
        vals['account_peppol_eas'] = '0208'
        settings = self.env['res.config.settings'].create(vals)
        settings.button_create_peppol_proxy_user()
        self.assertEqual(self.env.company.account_peppol_proxy_state, 'sender')
        with self.assertRaises(UserError), self.cr.savepoint():
            settings.button_peppol_smp_registration()

    def test_create_success_participant(self):
        # registration no longer requires SMS verification
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        settings.button_create_peppol_proxy_user()
        self.assertEqual(company.account_peppol_proxy_state, 'smp_registration')
        self.assertTrue(b64decode(self.registration_params['public_key']).startswith(b'-----BEGIN PUBLIC KEY-----'))
        self.assertNotIn('jsonrpc', self.registration_params)
        self.assertIn(
            'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1',
            self.receiver_params['supported_identifiers'],
        )
        self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_participant_status()
        self.assertEqual(company.account_peppol_proxy_state, 'receiver')

    def test_sender_only_can_enable_reception_without_recreating_user(self):
        settings = self.env['res.config.settings'].create({
            **self._get_participant_vals(),
            'account_peppol_sender_only': True,
        })
        settings.button_create_peppol_proxy_user()
        self.assertEqual(self.env.company.account_peppol_proxy_state, 'sender')
        edi_user = settings.account_peppol_edi_user
        settings.account_peppol_sender_only = False
        settings.button_peppol_smp_registration()
        self.assertEqual(self.env.company.account_peppol_proxy_state, 'smp_registration')
        self.assertEqual(settings.account_peppol_edi_user, edi_user)

    def test_kyc_redirect_then_callback_creates_connection_once(self):
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        with self._set_context({'auth_required': True}):
            action = settings.button_create_peppol_proxy_user()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['url'], 'https://peppol.test.odoo.com/authorize/test')
        self.assertEqual(self.env.company.account_peppol_proxy_state, 'in_verification')
        self.assertFalse(settings.account_peppol_edi_user)
        token = self.can_connect_params['connect_token']
        company = self.env.company
        user = company._peppol_complete_connection(token, auth_token='test-authorization')
        self.assertEqual(company.account_peppol_proxy_state, 'smp_registration')
        self.assertEqual(self.registration_params['auth_token'], 'test-authorization')
        self.assertEqual(company._peppol_complete_connection(token, auth_token='test-authorization'), user)
        self.assertEqual(len(settings.account_peppol_edi_user), 1)

    def test_callback_rejects_tampered_or_stale_token(self):
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        with self._set_context({'auth_required': True}):
            settings.button_create_peppol_proxy_user()
            first_token = self.can_connect_params['connect_token']
            settings.button_create_peppol_proxy_user()
            current_token = self.can_connect_params['connect_token']
        self.assertFalse(company._peppol_decode_connect_token(first_token[:-5] + 'AAAAA'))
        with self.assertRaises(UserError), self.cr.savepoint():
            company._peppol_complete_connection(first_token, auth_token='test-authorization')
        self.assertFalse(settings.account_peppol_edi_user)
        self.assertTrue(company._peppol_decode_connect_token(current_token))

    def test_kyc_token_expires_and_is_bound_to_database(self):
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        with self._set_context({'auth_required': True}):
            settings.button_create_peppol_proxy_user()
        signing_env = company.sudo().env
        values = verify_hash_signed(signing_env, 'account_peppol_connect', self.can_connect_params['connect_token'])
        secret = signing_env['ir.config_parameter'].get_param('database.secret')
        self.assertEqual(verify_hash_signed(None, 'account_peppol_connect', self.can_connect_params['connect_token'], secret=secret), values)
        expired = hash_sign(signing_env, 'account_peppol_connect', values, expiration_hours=-1)
        self.assertFalse(company._peppol_decode_connect_token(expired))
        values['db_name'] = self.env.cr.dbname + '_other'
        other_database = hash_sign(signing_env, 'account_peppol_connect', values, expiration_hours=1)
        self.assertFalse(company._peppol_decode_connect_token(other_database))

    def test_kyc_preserves_old_credentials_until_authorization(self):
        settings = self.env['res.config.settings'].create({
            **self._get_participant_vals(), 'account_peppol_sender_only': True,
        })
        settings.button_create_peppol_proxy_user()
        user = settings.account_peppol_edi_user
        old_key = user.sudo().private_key
        self.env.company.account_peppol_proxy_state = 'not_registered'
        with self._set_context({'auth_required': True}):
            action = settings.button_create_peppol_proxy_user()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertTrue(user.active)
        self.assertEqual(user.sudo().private_key, old_key)
        self.assertEqual(settings.account_peppol_edi_user, user)

    def test_reception_failure_keeps_existing_sender_credentials(self):
        settings = self.env['res.config.settings'].create({
            **self._get_participant_vals(),
            'account_peppol_sender_only': True,
        })
        settings.button_create_peppol_proxy_user()
        edi_user = settings.account_peppol_edi_user
        settings.account_peppol_sender_only = False
        with self._set_context({'receiver_error': True}):
            with self.assertRaises(UserError), self.cr.savepoint():
                settings.button_peppol_smp_registration()
        self.assertEqual(self.env.company.account_peppol_proxy_state, 'sender')
        self.assertTrue(edi_user.exists())
        self.assertEqual(settings.account_peppol_edi_user, edi_user)

    def test_create_reject_participant(self):
        # the account_peppol_proxy_state should change to rejected
        # if we reject the participant
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())

        with self._set_context({'reject': True}):
            settings.button_create_peppol_proxy_user()
            company.account_peppol_proxy_state = 'smp_registration'
            self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_participant_status()
            self.assertEqual(company.account_peppol_proxy_state, 'rejected')

    def test_kyc_replaces_old_connection_without_blocking_uniqueness(self):
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        company = self.env.company
        settings.button_register_with_kyc()
        old_user = settings.account_peppol_edi_user
        old_user.id_client = 'old-client'
        company.account_peppol_proxy_state = 'not_registered'
        settings.button_register_with_kyc()
        self.assertFalse(old_user.active)
        new_user = settings.account_peppol_edi_user
        self.assertTrue(new_user.active)
        self.assertNotEqual(old_user, new_user)
        self.assertEqual(old_user.edi_identification, new_user.edi_identification)

    def test_create_duplicate_participant(self):
        # should not be possible to create a duplicate participant
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        settings.button_create_peppol_proxy_user()
        with self.assertRaises(UserError), self.cr.savepoint():
            settings.button_create_peppol_proxy_user()

    def test_save_migration_key(self):
        # migration key should be saved
        settings = self.env['res.config.settings']\
            .create({
                **self._get_participant_vals(),
                'account_peppol_migration_key': 'helloo',
            })

        with self._set_context({'migrate_to': True}):
            settings.button_create_peppol_proxy_user()
            self.assertEqual(self.env.company.account_peppol_proxy_state, 'smp_registration')
            self.assertFalse(settings.account_peppol_migration_key) # the key should be reset once we've used it
