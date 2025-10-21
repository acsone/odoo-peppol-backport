import json
from base64 import b64encode
from contextlib import contextmanager
from urllib import parse

from freezegun import freeze_time
from requests import PreparedRequest, Response, Session

from odoo.exceptions import UserError
from odoo.tests.common import tagged
from odoo.tools.misc import file_open

from .utils import RequestHandlerTransactionCase

ID_CLIENT = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
FAKE_UUID = [
    "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
    "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",
]
FILE_PATH = "account_peppol_backport/tests/assets"


@freeze_time("2023-01-01")
@tagged("-at_install", "post_install")
class TestPeppolMessage(RequestHandlerTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "account_peppol.edi.mode", "test"
        )

        cls.env.company.write(
            {
                "country_id": cls.env.ref("base.be").id,
                "peppol_eas": "0208",
                "peppol_endpoint": "0477472701",
                "account_peppol_proxy_state": "active",
            }
        )

        edi_identification = cls.env[
            "account_edi_proxy_client_peppol.user"
        ]._get_proxy_identification(cls.env.company, "peppol")
        cls.proxy_user = cls.env["account_edi_proxy_client_peppol.user"].create(
            {
                "id_client": ID_CLIENT,
                "proxy_type": "peppol",
                "edi_mode": "test",
                "edi_identification": edi_identification,
                "private_key": b64encode(
                    file_open(f"{FILE_PATH}/private_key.pem", "rb").read()
                ),
                "refresh_token": FAKE_UUID[0],
            }
        )

        cls.invalid_partner, cls.valid_partner = cls.env["res.partner"].create(
            [
                {
                    "name": "Wintermute",
                    "city": "Charleroi",
                    "country_id": cls.env.ref("base.be").id,
                    "peppol_eas": "0208",
                    "peppol_endpoint": "3141592654",
                },
                {
                    "name": "Molly",
                    "city": "Namur",
                    "email": "Namur@company.com",
                    "country_id": cls.env.ref("base.be").id,
                    "peppol_eas": "0208",
                    "peppol_endpoint": "2718281828",
                },
            ]
        )

        cls.valid_partner.account_peppol_is_endpoint_valid = True
        cls.valid_partner.account_peppol_validity_last_check = "2022-12-01"

        cls.env["res.partner.bank"].create(
            {
                "acc_number": "0144748555",
                "partner_id": cls.env.company.partner_id.id,
            }
        )

    @classmethod
    def _get_mock_data(cls, error=False):
        proxy_documents = {
            FAKE_UUID[0]: {
                "accounting_supplier_party": False,
                "filename": "test_outgoing.xml",
                "enc_key": "",
                "document": "",
                "state": "done" if not error else "error",
                "direction": "outgoing",
                "document_type": "Invoice",
            },
            FAKE_UUID[1]: {
                "accounting_supplier_party": "0198:dk16356706",
                "filename": "test_incoming",
                "enc_key": file_open(f"{FILE_PATH}/enc_key", mode="rb").read(),
                "document": b64encode(
                    file_open(f"{FILE_PATH}/document", mode="rb").read()
                ),
                "state": "done" if not error else "error",
                "direction": "incoming",
                "document_type": "Invoice",
            },
        }

        responses = {
            "/api/peppol/1/send_document": {
                "result": {"messages": [{"message_uuid": FAKE_UUID[0]}]}
            },
            "/api/peppol/1/ack": {"result": {}},
            "/api/peppol/1/get_all_documents": {
                "result": {
                    "messages": [
                        {
                            "accounting_supplier_party": "0198:dk16356706",
                            "filename": "test_incoming.xml",
                            "uuid": FAKE_UUID[1],
                            "state": "done" if not error else "error",
                            "direction": "incoming",
                            "document_type": "Invoice",
                            "sender": "0198:dk16356706",
                            "receiver": "0208:0477472701",
                            "timestamp": "2022-12-30",
                            "error": False if not error else "Test error",
                        }
                    ],
                }
            },
        }
        return proxy_documents, responses

    @contextmanager
    def _set_context(self, other_context):
        previous_context = self.env.context
        self.env.context = dict(previous_context, **other_context)
        yield self
        self.env.context = previous_context

    @classmethod
    def _request_handler(cls, s: Session, r: PreparedRequest, /, **kw):
        response = Response()
        response.status_code = 200
        if r.path_url.startswith('/api/peppol/1/lookup'):
            peppol_identifier = parse.parse_qs(r.path_url.rsplit('?')[1])['peppol_identifier'][0]
            url_quoted_peppol_identifier = parse.quote_plus(peppol_identifier)
            if peppol_identifier.endswith('0477472701'):
                response.status_code = 200
                response.json = lambda: {
                    "result": {
                        'identifier': peppol_identifier,
                        'smp_base_url': "http://iap-services.odoo.com",
                        'ttl': 60,
                        'service_group_url': f'http://iap-services.odoo.com/iso6523-actorid-upis%3A%3A{url_quoted_peppol_identifier}',
                        'services': [
                            {
                                "href": f"http://iap-services.odoo.com/iso6523-actorid-upis%3A%3A{url_quoted_peppol_identifier}/services/busdox-docid-qns%3A%3Aurn%3Aoasis%3Anames%3Aspecification%3Aubl%3Aschema%3Axsd%3AInvoice-2%3A%3AInvoice%23%23urn%3Acen.eu%3Aen16931%3A2017%23compliant%23urn%3Afdc%3Apeppol.eu%3A2017%3Apoacc%3Abilling%3A3.0%3A%3A2.1",
                                "document_id": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1",
                            },
                        ],
                    },
                }
                return response
            if peppol_identifier.endswith('3141592654'):
                response.status_code = 404
                response.json = lambda: {"error": {"code": "NOT_FOUND", "message": "no naptr record", "retryable": False}}
                return response
            if peppol_identifier.endswith('2718281828'):
                response.status_code = 200
                response.json = lambda: {
                    "result": {
                        'identifier': peppol_identifier,
                        'smp_base_url': "http://iap-services.odoo.com",
                        'ttl': 60,
                        'service_group_url': f'http://iap-services.odoo.com/iso6523-actorid-upis%3A%3A{url_quoted_peppol_identifier}',
                        'services': [],
                    },
                }
                return response

            if peppol_identifier == '0198:dk16356706':
                response.status_code = 200
                response.json = lambda: {"result": {
                        'identifier': peppol_identifier,
                        'smp_base_url': "http://iap-services.odoo.com",
                        'ttl': 60,
                        'service_group_url': f'http://iap-services.odoo.com/iso6523-actorid-upis%3A%3A{url_quoted_peppol_identifier}',
                        'services': [],
                    },
                }
                return response

        proxy_documents, responses = cls._get_mock_data(cls.env.context.get("error"))
        url = r.path_url
        body = json.loads(r.body)
        if url == "/api/peppol/1/send_document":
            if not body["params"]["documents"]:
                raise UserError("No documents were provided")  # pylint: disable=translation-required

        if url == "/api/peppol/1/get_document":
            uuid = body["params"]["message_uuids"][0]
            response.json = lambda: {"result": {uuid: proxy_documents[uuid]}}
            return response

        if url not in responses:
            return super()._request_handler(s, r, **kw)
        response.json = lambda: responses[url]
        return response

    def test_receive_error_peppol(self):
        # an error peppol message should be created
        with self._set_context({"error": True}):
            self.env[
                "account_edi_proxy_client_peppol.user"
            ]._cron_peppol_get_new_documents()

            move = self.env["account.move"].search(
                [("peppol_message_uuid", "=", FAKE_UUID[1])]
            )
            self.assertRecordValues(
                move,
                [
                    {
                        "peppol_move_state": "error",
                        "move_type": "in_invoice",
                    }
                ],
            )

    def test_receive_success_peppol(self):
        # a correct move should be created
        self.env[
            "account_edi_proxy_client_peppol.user"
        ]._cron_peppol_get_new_documents()

        move = self.env["account.move"].search(
            [("peppol_message_uuid", "=", FAKE_UUID[1])]
        )
        self.assertRecordValues(
            move,
            [
                {
                    "peppol_move_state": "done",
                    "move_type": "in_invoice",
                }
            ],
        )

    def test_validate_partner(self):
        new_partner = self.env["res.partner"].create(
            {
                "name": "Deanna Troi",
                "city": "Namur",
                "country_id": self.env.ref("base.be").id,
            }
        )
        self.assertRecordValues(
            new_partner,
            [
                {
                    "account_peppol_verification_label": "not_verified",
                    "account_peppol_is_endpoint_valid": False,
                    "peppol_eas": "0208",
                    "peppol_endpoint": False,
                }
            ],
        )

        new_partner.peppol_endpoint = "0477472701"
        self.assertRecordValues(
            new_partner,
            [
                {
                    "account_peppol_verification_label": "valid",
                    "account_peppol_is_endpoint_valid": True,  # should validate automatically
                    "peppol_eas": "0208",
                    "peppol_endpoint": "0477472701",
                }
            ],
        )

        new_partner.peppol_endpoint = "3141592654"
        self.assertRecordValues(
            new_partner,
            [
                {
                    "account_peppol_verification_label": "not_valid",
                    "account_peppol_is_endpoint_valid": False,
                    "peppol_eas": "0208",
                    "peppol_endpoint": "3141592654",
                }
            ],
        )

        new_partner.ubl_cii_format = False
        self.assertFalse(new_partner.account_peppol_is_endpoint_valid)

        # the participant exists on the network but cannot receive XRechnung
        new_partner.write(
            {
                "ubl_cii_format": "xrechnung",
                "peppol_endpoint": "0477472701",
            }
        )
        self.assertRecordValues(
            new_partner,
            [
                {
                    "account_peppol_verification_label": "not_valid_format",
                    "account_peppol_is_endpoint_valid": False,
                    "peppol_eas": "0208",
                    "peppol_endpoint": "0477472701",
                }
            ],
        )
