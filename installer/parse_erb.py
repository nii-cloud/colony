
import rython


def get_ctx():
    ctx = rython.RubyContext(requires=['erb'], debug=True)
    ctx.load()
    return ctx

def end_ctx(ctx):
    ctx.unload()

def dump_config(configs=None, template_path=None, path=None):

    val = ''
    for config in configs:
        val += "%s='%s'\n" % (config.name, config.value)

    ctx = get_ctx()
    erb = ctx('%sERB.new(File.read("%s")).result(binding)' % (val, template_path))

    with open(path, "w") as f:
        if erb:
            f.write(erb)
    end_ctx(ctx)
