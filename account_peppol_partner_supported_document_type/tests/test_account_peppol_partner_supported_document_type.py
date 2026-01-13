# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from urllib.parse import parse_qs, quote_plus

from requests import PreparedRequest, Response, Session

from odoo.tests.common import tagged

from odoo.addons.account_peppol_backport.tests.utils import (
    RequestHandlerTransactionCase,
)

PEPPOL_ENDPOINT_SELF_BILLING = "1618033988"
PEPPOL_ENDPOINT_NO_SELF_BILLING = "1414213562"

PEPPOL_IDENTIFIER_SELF_BILLING = f"0208:{PEPPOL_ENDPOINT_SELF_BILLING}"
PEPPOL_IDENTIFIER_NO_SELF_BILLING = f"0208:{PEPPOL_ENDPOINT_NO_SELF_BILLING}"
SERVICE_GROUP_URL = "http://example.com/smp/iso6523-actorid-upi"
BILL3_DOCUMENT = "xxx##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"
SELFBILLING_DOCUMENT = "xxx#urn:cen.eu:en16931:2017##compliant#urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0::2.1"


@tagged("-at_install", "post_install")
class TestAccountPeppolPartnerSupportedDocumentType(RequestHandlerTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "account_peppol.edi.mode", "test"
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Self-Billing Partner",
                "city": "Brussels",
                "country_id": cls.env.ref("base.be").id,
                "peppol_eas": "0208",
            }
        )

    @classmethod
    def _request_handler(cls, s: Session, r: PreparedRequest, /, **kw):
        response = Response()
        response.status_code = 200
        if r.path_url.startswith("/api/peppol/1/lookup"):
            peppol_identifier = parse_qs(r.path_url.rsplit("?")[1])[
                "peppol_identifier"
            ][0]
            if not peppol_identifier.startswith("0208"):
                response.status_code = 404
                response.json = lambda: {
                    "error": {
                        "code": "NOT_FOUND",
                        "message": "no naptr record",
                        "retryable": False,
                    },
                }
                return response
            services = [{"document_id": BILL3_DOCUMENT}]
            if peppol_identifier == PEPPOL_IDENTIFIER_SELF_BILLING:
                services.append({"document_id": SELFBILLING_DOCUMENT})
            service_group_url = (
                f"{SERVICE_GROUP_URL}s%3A%3A{quote_plus(peppol_identifier)}"
            )
            response.json = lambda: {
                "result": {
                    "identifier": peppol_identifier,
                    "smp_base_url": "http://example.com/smp",
                    "ttl": 60,
                    "service_group_url": service_group_url,
                    "services": services,
                }
            }
            return response
        return super()._request_handler(s, r, **kw)

    def test_0(self):
        """test supported document type is stored on partner"""
        self.partner.peppol_endpoint = PEPPOL_ENDPOINT_NO_SELF_BILLING
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "valid",
                    "account_peppol_is_endpoint_valid": True,
                }
            ],
        )
        self.assertSetEqual(
            set(self.partner.ubl_cii_supported_format.split("\n")),
            {BILL3_DOCUMENT},
        )
        self.partner.peppol_endpoint = PEPPOL_ENDPOINT_SELF_BILLING
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "valid",
                    "account_peppol_is_endpoint_valid": True,
                }
            ],
        )
        self.assertSetEqual(
            set(self.partner.ubl_cii_supported_format.split("\n")),
            {BILL3_DOCUMENT, SELFBILLING_DOCUMENT},
        )
        self.partner.peppol_eas = "0002"
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "not_valid",
                    "account_peppol_is_endpoint_valid": False,
                }
            ],
        )
        self.assertFalse(self.partner.ubl_cii_supported_format)
