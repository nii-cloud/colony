import json
import logging
import re
from keystone import utils
from keystone.common import wsgi
import keystone.config as config
from keystone.logic.types import fault
from keystone.logic.types import token_by

LOG = logging.getLogger('keystone.controller.token_by')

class TokenByController(wsgi.Controller):
    """Controller for token picking by email or other keys"""

    def __init__(self, options):
        self.options = options

    @utils.wrap_error
    def get_token_by(self, req):
        try:
            cred = utils.get_normalized_request_content(
                token_by.TokenBy, req)
            if cred.by_type == 'email':
                return self.get_token_by_email(req, cred.key)
            elif cred.by_type == 'eppn':
                return self.get_token_by_eppn(req, cred.key)
        except KeyError:
            raise fault.UnauthorizedFault("bad request email or eppn")

    @utils.wrap_error
    def get_token_by_email(self, req, email):
        auth = config.SERVICE.get_token_by_email(
            utils.get_auth_token(req), email)
        return utils.send_result(200, req, auth)

    @utils.wrap_error
    def get_token_by_eppn(self, req, eppn):
        auth = config.SERVICE.get_token_by_eppn(
            utils.get_auth_token(req), eppn)
        return utils.send_result(200, req, auth)
