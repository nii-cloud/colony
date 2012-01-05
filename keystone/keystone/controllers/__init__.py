def get_url(req):
    return '%s://%s:%s%s' % (
        req.environ['wsgi.url_scheme'],
        req.environ.get("SERVER_NAME"),
        req.environ.get("SERVER_PORT"),
        req.environ['PATH_INFO'])


def get_marker_limit_and_url(req):
    if "marker" in req.GET:
        marker = req.GET["marker"] 
        if not marker.isdigit():
            marker = None
    else:
        marker = None

    if "limit" in req.GET:
        limit = req.GET["limit"] 
        if not limit.isdigit():
            limit = 10
    else:
        limit = 10
    url = get_url(req)
    
    return (marker, int(limit), url)
