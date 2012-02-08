# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from lxml import etree
import logging
from keystone.logic.types import fault

LOG = logging.getLogger('keystone.logic.type.token_by')

class TokenBy(object):
    key = None
    by_type = None
    def __init__(self, key, by_type):
        self.key = key
        self.by_type = by_type

    @staticmethod
    def from_json(json_str):
        try:
            obj = json.loads(json_str)
            if 'tokenByEmail' in obj:
                cred = obj['tokenByEmail']
                if not 'email' in cred:
                    raise fault.BadRequestFault('Expecting email')
                key = cred['email']
                by_type = 'email'
            elif 'tokenByEppn' in obj:
                cred = obj['tokenByEppn']
                if not 'eppn' in cred:
                    raise fault.BadRequestFault('Expecting eppn')
                key = cred['eppn']
                by_type = 'eppn'
            else:
                raise fault.BadRequestFault('Expecting tokenByEmail or tokenByEppn')
            return TokenBy(key, by_type)
        except (ValueError, TypeError) as e:
            raise fault.BadRequestFault("Cannot parse TokenBy", str(e))

    @staticmethod
    def from_xml(xml_str):
        try:
            dom = etree.Element("root")
            dom.append(etree.fromstring(xml_str))

            eppn_el = dom.find("{http://docs.openstack.org/identity/api/v2.0}"
                            "tokenByEppn")
            email_el = dom.find("{http://docs.openstack.org/identity/api/v2.0}"
                            "tokenByEmail")
           
            if email_el is not None:
                email = email_el.get("email")
                if email == None:
                    raise fault.BadRequestFault("Expecting email")
                return TokenBy(email, 'email')
            elif eppn_el is not None:
                eppn = eppn_el.get("eppn")
                if eppn == None:
                    raise fault.BadRequestFault("Expecting eppn")
                return TokenBy(eppn, 'eppn')
            else:
                raise fault.BadRequestFault('Expecting tokenByEmail or tokenByEppn')

        except etree.LxmlError as e:
            raise fault.BadRequestFault("Cannot parse TokenBy", str(e))
