
import argparse
import glob
import os
import subprocess
import sys
import yaml
from parse_erb import dump_config

def die(message, *args):
    print >> sys.stderr, message % args
    sys.exit(1)

def run_command(cmd, redirect_output=True, check_exit_code=True):
    """
    Runs a command in an out-of-process shell, returning the
    output of that command.  Working directory is ROOT.
    """
    if redirect_output:
        stdout = subprocess.PIPE
    else:
        stdout = open("install.log", "a+")

    proc = subprocess.Popen(cmd, cwd=os.path.curdir, stdout=stdout)
    output = proc.communicate()[0]
    if check_exit_code and proc.returncode != 0:
        die('Command "%s" failed.\n%s', ' '.join(cmd), output)
    return output


class ConfigItem(object):
    def __init__(self, name, def_value, *args, **kwargs):
        self._name = name
        self._default_value = def_value
        self._value = None
        self._install = False

    @property
    def name(self):
        return self._name

    @property
    def value(self):
        return self._value

    @property
    def default_value(self):
        return self._default_value

    @property
    def install(self):
        return self._install

    def ask(self):
        try:
            v = raw_input('%s : [%s]' % (self._name, self._value if self._value else self._default_value))
            if not v:
                v = self._default_value
        except EOFError:
            print ""
            v = self._default_value
        self._value = v
        # validator
        self._install = True

    def to_dict(self):
        return { self._name : self._value }

class PathConfigItem(ConfigItem):
    pass

class Config(object):
    def __init__(self, filename):
        self._yml = filename
        self._configs = []
        self._components_configs = []

    def _load_config(self):
        items = self._ymlobj['config_item_defaults']
        for item in items:
            config = ConfigItem(item['name'], item['value'])
            self._configs.append(config)

    @property
    def config(self):
        return self._configs

    @property
    def components(self):
        res = {}
        for item in self._components_configs:
            if not res.get(item.name, None):
                res[item.name] = []
            res[item.name].append(item)
        return res

    def _load_components_config(self):
        items = self._ymlobj['component_config_defaults']
        for item in items:
            config = PathConfigItem(item['component'], item['path'])
            self._components_configs.append(config)
        # dodai-deploy needs hostname for component
        for comp_name, value in self.components.iteritems():
            config = ConfigItem(comp_name, '127.0.0.1')
            self._configs.append(config)

    def load(self, filename = None):
        if not self._yml and not filename:
            raise Exception('fuga')
        value = open(self._yml).read()
        self._ymlobj = yaml.load(value)
        self._load_config()
        self._load_components_config()
    
    def _ask(self, name):
        try:
            v = raw_input('installing :%s y/N ?' % name)
            if v in ['Y', 'y']:
                return True
        except EOFError:
            print ""

        return False

    def _ask_item(self):
        conflen = len(self._configs)
        try:
            v = raw_input('Choose Item number: ')
            item = int(v)
            if item == conflen:
                return False
            if item >= 0 and item <= conflen:
                self._configs[item].ask()
        except (EOFError, ValueError):
            print ""
        return True

    def _menu(self):
        for x in range(len(self._configs)):
            c = self._configs[x]
            print "%d: %s [%s]" % (x, c.name, c.value if c.value else c.default_value)
        # put last value
        print "%d: Quit" % (len(self._configs))
  
    def ask(self):
        for comp_name, components_configs in self.components.iteritems():
            # check install components
            if self._ask(comp_name):
                for config in components_configs:
                    config.ask()
        while True:
            self._menu()
            if not self._ask_item():
                break



class ConfigManager(object):

    templates = 'templates'
    scripts = 'scripts'

    def _get_templates_path(self, name, path):
        filename = os.path.basename(path)
        return '%s/softwares/%s/%s/%s.erb' % ( os.path.curdir, name, ConfigManager.templates, filename)

    def _get_install_scripts(self, name, component_name, install=True):
        if install:
            return '%s/softwares/%s/%s/install-%s.sh' % ( os.path.curdir, name, ConfigManager.scripts, component_name)
        else:
            return '%s/softwares/%s/%s/uninstall-%s.sh' % ( os.path.curdir, name, ConfigManager.scripts, component_name)

    def __init__(self):
        files = glob.glob('./softwares/*/data.yml')
        self._softwares = {}
        for file in files:
            name = os.path.abspath(os.path.dirname(file)).split(os.path.sep)[-1]
            c = Config(file)
            c.load()
            self._softwares[name] = c

    def _ask(self, name, install=True):
        try:
             if install:
                 v = raw_input('installing :%s y/N ?' % name)
             else:
                 v = raw_input('Uninstalling :%s y/N ?' % name)
             if v in ['Y', 'y']:
                 return True
        except EOFError:
            print ''

        return False
        
    def ask(self, components, install=True):
        for name, value in self._softwares.iteritems():
            if self._ask(name, install):
                if install:
                    value.ask()
                for comp_name, comp_configs in value.components.iteritems():
                    scripts = self._get_install_scripts(name, comp_name, install)
                    if os.path.exists(scripts):
                        print 'executing scripts %s' % scripts
                        if not run_command(scripts, redirect_output=False):
                            print "installing failure"
                    for comp_config in comp_configs:
                        if comp_config.install:
                            template_path = self._get_templates_path(name, comp_config.default_value)
                            dump_config(value.config, template_path, comp_config.value)


#parse arg
argparser = argparse.ArgumentParser()
argparser.add_argument('--version', action='version', version='%(prog)s 1.0')
argparser.add_argument('--components', action='append', dest='installs', default=[],
                       help='component name which to be installed')
argparser.add_argument('--uninstall', action='store_false', default=True, dest='install')
argparser.add_argument('--local', action='store_true', default=False, dest='local')
args = argparser.parse_args()

if args.local:
   os.environ['PIP_FIND_LINKS'] = "file:///%s/downloads" % os.path.realpath(os.path.dirname(sys.argv[0]))

try:
    cm = ConfigManager()
    cm.ask(args.installs, args.install)
except KeyboardInterrupt:
    print "install intruppted\n"
except Exception as e:
    print e
    raise e

