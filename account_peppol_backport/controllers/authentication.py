# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging

from werkzeug.wrappers import Response

from odoo import SUPERUSER_ID, api, http, registry, sql_db
from odoo.exceptions import UserError
from odoo.http import request

from ..tools.signed_tokens import verify_hash_signed

_logger = logging.getLogger(__name__)


class PeppolAuthentication(http.Controller):
    @http.route('/peppol/authentication/callback', type='http', methods=['GET'], auth='user', sitemap=False)
    def peppol_authentication_callback(self, connect_token=None, auth_token=None, state=None, db=None, **kwargs):
        if db and db != request.env.cr.dbname:
            return Response('Please log in to the database that started this Peppol registration.', status=400)
        data = request.env['res.company']._peppol_decode_connect_token(connect_token)
        if not data or data['user'].id != request.env.uid:
            return Response('Invalid or expired Peppol authorization.', status=400)
        company = data['company'].with_company(data['company'])
        if state == 'pending':
            return request.redirect('/web')
        if state == 'canceled':
            company._peppol_cancel_connection(connect_token)
            return request.redirect('/web')
        if not auth_token:
            return Response('Missing Peppol authorization.', status=400)
        try:
            company._peppol_complete_connection(connect_token, auth_token=auth_token)
        except UserError as exc:
            request.env.cr.rollback()
            return Response(str(exc), status=400, content_type='text/plain; charset=utf-8')
        return request.redirect('/web')

    @http.route('/peppol/authentication/webhook', type='http', methods=['POST'], auth='none', csrf=False, sitemap=False)
    def peppol_authentication_webhook(self, connect_token=None, auth_token=None, db=None, **kwargs):
        # v15 may host test and production databases on the same server; select the
        # advertised database, then require its signed, expiring authorization token
        if not db or not auth_token or not http.db_filter([db]):
            return self._json_response({'error': 'invalid_request'}, status=400)
        try:
            with sql_db.db_connect(db).cursor() as cr:
                cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", ['database.secret'])
                secret = cr.fetchone()
                values = verify_hash_signed(None, 'account_peppol_connect', connect_token, secret=secret[0]) if secret and secret[0] else None
                if not isinstance(values, dict) or values.get('db_name') != db:
                    return self._json_response({'error': 'invalid_request'}, status=400)
            with api.Environment.manage():
                db_registry = registry(db).check_signaling()
                with db_registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    data = env['res.company']._peppol_decode_connect_token(connect_token)
                    if not data:
                        return self._json_response({'error': 'invalid_request'}, status=400)
                    company = data['company'].with_company(data['company'])
                    company._peppol_complete_connection(connect_token, auth_token=auth_token)
                    cr.commit()
        except Exception:  # isolated callback transaction, never log tokens or credentials
            _logger.warning('Peppol webhook could not complete the connection')
            return self._json_response({'status': 'failed'}, status=400)
        return self._json_response({'status': 'connected'})

    @staticmethod
    def _json_response(values, status=200):
        return Response(json.dumps(values), status=status, content_type='application/json')
