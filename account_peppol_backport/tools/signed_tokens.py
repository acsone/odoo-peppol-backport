# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""Odoo 17 signed tokens using the HMAC helper available in Odoo 15"""

import base64
import json
import time
from hashlib import sha256
from hmac import compare_digest, new

from odoo.tools.misc import hmac


def hash_sign(env, scope, values, expiration_hours):
    expiration = int(time.time() + expiration_hours * 3600)
    message = json.dumps(values)
    signature = hmac(env, scope, '1:%s:%s' % (message, expiration))
    token = b'\x01' + expiration.to_bytes(8, 'little') + bytes.fromhex(signature) + message.encode()
    return base64.urlsafe_b64encode(token).decode().rstrip('=')


def verify_hash_signed(env, scope, payload, *, secret=None):
    if not isinstance(payload, str) or len(payload) > 8192:
        return None
    token = base64.urlsafe_b64decode(payload.encode() + b'===')
    if len(token) < 41 or token[:1] != b'\x01':
        return None
    expiration = int.from_bytes(token[1:9], byteorder='little')
    message = token[41:].decode()
    signed_message = '1:%s:%s' % (message, expiration)
    if secret is None:
        signature = hmac(env, scope, signed_message)
    else:
        # authenticate webhooks before loading an ORM registry for the requested database
        signature = new(secret.encode(), repr((scope, signed_message)).encode(), sha256).hexdigest()
    if not compare_digest(token[9:41].hex(), signature) or expiration <= time.time():
        return None
    return json.loads(message)
