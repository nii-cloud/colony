
import rython


ctx = None

def init_ctx():
    global ctx
    if not ctx:
        ctx = rython.RubyContext(requires=['erb'], debug=True)
        ctx.load()

def get_ctx():
    global ctx
    if not ctx:
        init_ctx()
    return ctx

def dump_config(configs=None, template_path=None, path=None):

    val = ''
    for config in configs:
        val += "%s='%s'\n" % (config.name, config.value)

    ctx = get_ctx()
    erb = ctx('%sERB.new(File.read("%s")).result(binding)' % (val, template_path))

    with open(path, "w") as f:
        if erb:
            f.write(erb)

