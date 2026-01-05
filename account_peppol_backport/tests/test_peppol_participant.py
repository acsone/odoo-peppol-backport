import json
from contextlib import contextmanager
from urllib.parse import parse_qs, quote_plus

from freezegun import freeze_time
from psycopg2 import IntegrityError
from requests import PreparedRequest, Response, Session

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .utils import RequestHandlerTransactionCase

ID_CLIENT = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
FAKE_UUID = 'yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy'
PDF_FILE_PATH = 'account_peppol/tests/assets/peppol_identification_test.pdf'


# SMP returns 200 for these and 404 otherwise

SMP_OK_IDS = {'0208:0000000000', '0208:0000000001'}


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
            '/api/peppol/1/participant_status': {
                'result': {
                    'peppol_state': 'active' if not reject else 'rejected',
                }
            },
            '/api/peppol/1/activate_participant': {'result': {}},
            '/iap/account_edi/2/create_user': {
                'result': {
                    'id_client': ID_CLIENT,
                    'refresh_token': FAKE_UUID,
                }
            },
            '/api/peppol/1/send_verification_code': {'result': {}},
            '/api/peppol/1/update_user': {'result': {}},
            '/api/peppol/1/verify_phone_number': {'result': {}},
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
        if r.path_url.startswith("/api/peppol/1/lookup"):
            peppol_identifier = parse_qs(r.path_url.rsplit("?")[1])[
                "peppol_identifier"
            ][0]

            if peppol_identifier in SMP_OK_IDS:

                response.json = lambda: {
                    "result": {
                        "identifier": peppol_identifier,
                        "smp_base_url": "http://example.com/smp",
                        "ttl": 60,
                        "service_group_url": "http://example.com/smp/iso6523-actorid-upis%3A%3A"
                        + quote_plus(peppol_identifier),
                        "services": [],
                    }
                }

            else:

                response.status_code = 404

                response.json = lambda: {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "no naptr record",
                        "retryable": False,
                    },
                }

            return response

        url = r.path_url
        body = json.loads(r.body)
        responses = cls._get_mock_responses(cls.env.context.get('reject'))
        if (
            url == '/api/peppol/1/activate_participant'
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
        yield self
        self.env.context = previous_context

    def test_create_participant_missing_data(self):
        # creating a participant without eas/endpoint/document should not be possible
        settings = self.env['res.config.settings'].create({
            'account_peppol_eas': False,
            'account_peppol_endpoint': False,
        })
        with self.assertRaises(ValidationError), self.cr.savepoint():
            settings.button_create_peppol_proxy_user()

    def test_create_participant_already_exists(self):
        # creating a participant that already exists on Peppol network should not be possible
        vals = self._get_participant_vals()
        vals['account_peppol_eas'] = '0208'
        settings = self.env['res.config.settings'].create(vals)
        with self.assertRaises(UserError), self.cr.savepoint():
            settings.button_create_peppol_proxy_user()

    def test_create_success_participant(self):
        # should be possible to apply with all data
        # the account_peppol_proxy_state should correctly change to pending
        # then the account_peppol_proxy_state should change success
        # after checking participant status
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        settings.button_create_peppol_proxy_user()
        self.assertEqual(company.account_peppol_proxy_state, 'not_verified')
        settings.button_send_peppol_verification_code()
        self.assertEqual(company.account_peppol_proxy_state, 'sent_verification')
        settings.account_peppol_verification_code = '123456'
        settings.button_check_peppol_verification_code()
        self.assertEqual(company.account_peppol_proxy_state, 'pending')
        self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_participant_status()
        self.assertEqual(company.account_peppol_proxy_state, 'active')

    def test_create_reject_participant(self):
        # the account_peppol_proxy_state should change to rejected
        # if we reject the participant
        company = self.env.company
        settings = self.env['res.config.settings'].create(self._get_participant_vals())

        with self._set_context({'reject': True}):
            settings.button_create_peppol_proxy_user()
            company.account_peppol_proxy_state = 'pending'
            self.env['account_edi_proxy_client_peppol.user']._cron_peppol_get_participant_status()
            self.assertEqual(company.account_peppol_proxy_state, 'rejected')

    @mute_logger('odoo.sql_db')
    def test_create_duplicate_participant(self):
        # should not be possible to create a duplicate participant
        settings = self.env['res.config.settings'].create(self._get_participant_vals())
        settings.button_create_peppol_proxy_user()
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            settings.account_peppol_proxy_state = 'not_registered'
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
            self.assertEqual(self.env.company.account_peppol_proxy_state, 'not_verified')
            self.assertFalse(settings.account_peppol_migration_key) # the key should be reset once we've used it
