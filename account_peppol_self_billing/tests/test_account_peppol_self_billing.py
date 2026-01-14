# Copyright 2026 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo.addons.account_peppol_partner_supported_document_type.tests.test_account_peppol_partner_supported_document_type import (
    PEPPOL_ENDPOINT_NO_SELF_BILLING,
    PEPPOL_ENDPOINT_SELF_BILLING,
    TestAccountPeppolPartnerSupportedDocumentType,
)


class TestAccountPeppolSelfBilling(TestAccountPeppolPartnerSupportedDocumentType):
    def test_1(self):
        self.partner.peppol_endpoint = PEPPOL_ENDPOINT_NO_SELF_BILLING
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "valid",
                    "account_peppol_is_endpoint_valid": True,
                    "peppol_self_billing_supported": False,
                }
            ],
        )
        self.partner.peppol_endpoint = PEPPOL_ENDPOINT_SELF_BILLING
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "valid",
                    "account_peppol_is_endpoint_valid": True,
                    "peppol_self_billing_supported": True,
                }
            ],
        )
        self.partner.peppol_eas = "0002"
        self.assertRecordValues(
            self.partner,
            [
                {
                    "account_peppol_verification_label": "not_valid",
                    "account_peppol_is_endpoint_valid": False,
                    "peppol_self_billing_supported": False,
                }
            ],
        )
        self.assertFalse(self.partner.ubl_cii_supported_format)
