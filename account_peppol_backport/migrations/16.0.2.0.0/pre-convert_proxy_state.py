# SPDX-FileCopyrightText: 2025 Coop IT Easy SC
#
# SPDX-License-Identifier: AGPL-3.0-or-later

def migrate(cr, version):
    cr.execute(
        """
        update res_company
        set account_peppol_proxy_state = case
            when account_peppol_proxy_state in ('not_verified', 'sent_verification', 'canceled') then 'not_registered'
            when account_peppol_proxy_state = 'pending' then 'smp_registration'
            when account_peppol_proxy_state = 'active' then 'receiver'
        end
        where account_peppol_proxy_state in ('not_verified', 'sent_verification', 'pending', 'active', 'canceled')
        """,
    )
