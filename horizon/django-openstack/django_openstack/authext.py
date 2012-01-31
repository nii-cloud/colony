
from openstackx.api import base
import openstackx.admin
import openstackx.api.exceptions as api_exceptions


class UserExt(base.Resource):
    def __repr__(self):
        return "<User %s>" % self._info

    def delete(self):
        self.manager.delete(self)

class GakuninAuth(base.Resource):
    def __repr__(self):
        return "<Token %s>" % self._info

    @property
    def id(self):
        return self._info['token']['id']

    @property
    def username(self):
        try:
            return self._info['user']['username']
        except:
            return "?"

    @property
    def tenant_id(self):
        try:
            return self._info['user']['tenantId']
        except:
            return "?"

    def delete(self):
        self.manager.delete(self)

class UserManagerExt(base.ManagerWithFind):
    resource_class = UserExt

    def update_eppn(self, user_id, eppn):
        params = {"user": {"id": user_id,
                           "eppn": eppn }}
        self._update("/users/%s/eppn" % user_id, params)


class GakuninAuthManager(base.ManagerWithFind):
    resource_class = GakuninAuth

    def create_token_by_email(self, email):
        params = {"auth": {"tokenByEmail": {"email": email}}}
        return self._create('token_by/email', params, "access")

    def create_token_by_eppn(self, eppn):
        params = {"auth": {"tokenByEppn": {"eppn": eppn}}}
        return self._create('token_by/eppn', params, "access")

class AdminExt(openstackx.admin.Admin):

    def __init__(self, **kwargs):
        super(AdminExt, self).__init__(self, **kwargs)
        self.gakunin = GakuninAuthManager(self)
        self.userext = UserManagerExt(self)
