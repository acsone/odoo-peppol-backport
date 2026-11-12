# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
# SPDX-FileCopyrightText: 2026 ACSONE SA/NV
# SPDX-License-Identifier: AGPL-3.0-or-later


def migrate(cr, version):
    # Replace full uniqueness constraints with the active-only indexes created
    # by the proxy model, so archived connections can be replaced after KYC.
    cr.execute("""
        ALTER TABLE account_edi_proxy_client_peppol_user
        DROP CONSTRAINT IF EXISTS account_edi_proxy_client_peppol_user_uniq_active_edi_identif,
        DROP CONSTRAINT IF EXISTS account_edi_proxy_client_peppol_user_uniq_active_company_proxy
    """)
    cr.execute("""
        UPDATE res_company
           SET account_peppol_proxy_state = CASE
               WHEN account_peppol_proxy_state IN ('not_verified', 'sent_verification', 'canceled')
                   THEN 'not_registered'
               WHEN account_peppol_proxy_state = 'pending' THEN 'smp_registration'
               WHEN account_peppol_proxy_state = 'active' THEN 'receiver'
           END
         WHERE account_peppol_proxy_state IN (
             'not_verified', 'sent_verification', 'pending', 'active', 'canceled'
         )
    """)
