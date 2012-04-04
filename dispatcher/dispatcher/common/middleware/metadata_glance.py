
from glance.client import Client
from webob import Response, Request

class GlanceMetadataConvFilter(object):
    def __init__(self, app, conf):
        self.app = app
        self.conf = conf
        # todo, logger

    def _get_glance_client(self):
        glance_host = self.conf.get('host', '127.0.0.1')
        glance_port = self.conf.get('port', '8080')
        c = Client(host=glance_host, port=glance_port)
        return c

    def images_detailed(self):
        c = _get_glance_client()
        try:
            images = c.get_images_detailed()
            if len(images) == 0:
               pass
            num_images = len(images)
            for image in images:
                print "*" * 80
                print image
        except Exception, e:
            pass

    """
    1. parse body data as xml string
    2. create options for glance
    2. call update_image 
    """
    def metadata_uploaded(self, fields):
        # derived from glance command
        image_id = 0 # FIXME 
        image_meta = {}
        nonmodifiable_fields = ['created_on', 'deleted_on', 'deleted', 
                                'updated_on', 'size', 'status']
        for field in nonmodifiable_fields:
            fields.pop(field)
        c = _get_glance_client()
        try:
            image_meta = c.update_image(image_id, image_meta=image_meta)
        except exception.NotFound:
            pass
        except Exception, e:
            pass
        

    """
    1. parse body data as xml string
    2. create options for glance
    """
    def handle_upload(self, env):
        pass

    """
    """
    def retrieve_metadata(self, env):
        pass

    '''
    TODO:
        check location path and decide the behavior
          upload - call handle_upload
          get - call retrieve_metadata
          unknown(raise Error)
    '''
    def handle_request(self, env, start_response):
        pass

    def __call__(self, env, start_response):
        # check location
        path = env.get('PATH_INFO', '')
        if path.startswith('/glance'): # should be customizable
            return handle_request(self, env, start_response)
        return self.app(env, start_response)

def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def metadata_glance_filter(app):
        return GlanceMetadataConvFilter(app, conf)
    return metadata_glance_filter
