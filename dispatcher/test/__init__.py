import __builtin__
import sys
import os
from ConfigParser import MissingSectionHeaderError
from StringIO import StringIO

from swift.common.utils import readconf

setattr(__builtin__, '_', lambda x: x)


# Work around what seems to be a Python bug.
# c.f. https://bugs.launchpad.net/swift/+bug/820185.
import logging
logging.raiseExceptions = False


def get_config():
    """
    Attempt to get a functional config dictionary.
    """
    config_file = 'test/dispatcher_test.conf'
    config = {}
    try:
        try:
            config = readconf(config_file, 'app:dispatcher')
        except MissingSectionHeaderError:
            config_fp = StringIO('[func_test]\n' + open(config_file).read())
            config = readconf(config_fp, 'func_test')
    except SystemExit:
        print >>sys.stderr, 'UNABLE TO READ FUNCTIONAL TESTS CONFIG FILE'
    return config
