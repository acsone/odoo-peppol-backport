# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""public REST connection API from Odoo 17, without the legacy JSON-RPC envelope"""

import requests

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.account_edi_proxy_client_peppol.models.account_edi_proxy_user import (
    _get_proxy_error_message,
)


class PeppolIAPConnector:
    def __init__(self, company):
        company.ensure_one()
        self.company = company
        mode = company._get_peppol_edi_mode()
        if mode not in ('prod', 'test'):
            raise UserError(_('A real Peppol connection requires Test or Live mode.'))
        self.base_url = company.env['account_edi_proxy_client_peppol.user']._get_proxy_urls()['peppol'][mode]

    def request_public_http(self, method, endpoint, data=None, params=None):
        values = {}
        try:
            response = requests.request(
                method, self.base_url + endpoint, json=data, params=params,
                timeout=30, headers={'Content-Type': 'application/json'},
            )
            values = response.json()
            response.raise_for_status()
        except (requests.exceptions.RequestException, ValueError) as exc:
            if isinstance(values, dict) and (values.get('code') or values.get('error')):
                raise UserError(_get_proxy_error_message(values.get('error') or values)) from exc
            raise UserError(_('Failed to connect to Odoo Peppol Proxy.')) from exc
        if not isinstance(values, dict):
            raise UserError(_('The Peppol proxy returned an invalid response.'))
        if values.get('error') or values.get('code'):
            raise UserError(_get_proxy_error_message(values.get('error') or values))
        return values

    def can_connect(self, *, peppol_identifier, db_uuid, callback_url, connect_token,
                    contact_email=None, webhook_url=None):
        return self.request_public_http('GET', '/api/peppol/2/can_connect', params={
            'dbuuid': db_uuid,
            'peppol_identifier': peppol_identifier,
            'callback_url': callback_url,
            'connect_token': connect_token,
            'contact_email': contact_email,
            'webhook_url': webhook_url,
        })

    def create_connection(self, *, peppol_identifier, db_uuid, public_key,
                          auth_token=None, **company_details):
        return self.request_public_http('POST', '/api/peppol/2/connect', data={
            'peppol_identifier': peppol_identifier,
            'dbuuid': db_uuid,
            'company_id': self.company.id,
            'public_key': public_key,
            'auth_token': auth_token,
            **company_details,
        })
