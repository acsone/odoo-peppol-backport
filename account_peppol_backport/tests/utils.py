import logging
from unittest.mock import _patch, patch

import requests
import werkzeug.urls
from requests import PreparedRequest, Session

from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
_super_send = requests.Session.send


class BlockedRequest(requests.exceptions.ConnectionError):
    pass


class RequestHandlerTransactionCase(TransactionCase):
    @classmethod
    def _request_handler(cls, s: Session, r: PreparedRequest, /, **kw):
        # allow localhost requests
        # TODO: also check port?
        url = werkzeug.urls.url_parse(r.url)
        timeout = kw.get("timeout")
        if timeout and timeout < 10:
            _logger.getChild("requests").info(
                "request %s with timeout %s increased to 10s during tests", url, timeout
            )
            kw["timeout"] = 10
        if url.host in (HOST, "localhost"):
            return _super_send(s, r, **kw)
        if url.scheme == "file":
            return _super_send(s, r, **kw)

        _logger.getChild("requests").info(
            "Blocking un-mocked external HTTP request %s %s", r.method, r.url
        )
        raise BlockedRequest(f"External requests verboten (was {r.method} {r.url})")

    @classmethod
    def setUpClass(cls):
        def check_remaining_patchers():
            for patcher in _patch._active_patches:
                _logger.warning("A patcher (targeting %s.%s) was remaining active at the end of %s, disabling it...", patcher.target, patcher.attribute, cls.__name__)
                patcher.stop()
        cls.addClassCleanup(check_remaining_patchers)
        super().setUpClass()
        if 'standard' in cls.test_tags:
            # if the method is passed directly `patch` discards the session
            # object which we need
            # pylint: disable=unnecessary-lambda
            patcher = patch.object(
                requests.sessions.Session,
                'send',
                lambda s, r, **kwargs: cls._request_handler(s, r, **kwargs),
            )
            patcher.start()
            cls.addClassCleanup(patcher.stop)
