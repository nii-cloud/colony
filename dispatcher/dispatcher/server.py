# coding=utf-8
from __future__ import with_statement
try:
    import simplejson as json
except ImportError:
    import json
from base64 import urlsafe_b64encode, urlsafe_b64decode
from urllib import quote, unquote, urlencode
from urlparse import urlparse, urlunparse, parse_qs
from webob import Request, Response
from webob.exc import HTTPException, HTTPAccepted, HTTPBadRequest, \
    HTTPConflict, HTTPCreated, HTTPForbidden, HTTPMethodNotAllowed, \
    HTTPMovedPermanently, HTTPNoContent, HTTPNotFound, \
    HTTPServiceUnavailable, HTTPUnauthorized, HTTPGatewayTimeout, \
    HTTPBadGateway,  HTTPRequestEntityTooLarge, HTTPServerError
from eventlet import GreenPile, Queue, sleep, TimeoutError
from eventlet.timeout import Timeout
#from eventlet.green.httplib import HTTPConnection, HTTPResponse, HTTPSConnection
from swift.common.utils import get_logger, ContextPool
from swift.common.exceptions import ConnectionTimeout, ChunkReadTimeout, ChunkWriteTimeout
from swift.common.constraints import CONTAINER_LISTING_LIMIT, MAX_ACCOUNT_NAME_LENGTH, \
    MAX_CONTAINER_NAME_LENGTH, MAX_FILE_SIZE
from swift.common.bufferedhttp import http_connect_raw, BufferedHTTPConnection, BufferedHTTPResponse
from swift.proxy.server import update_headers
from dispatcher.common.fastestmirror import FastestMirror
from dispatcher.common.location import Location
import os
import sys
import time
from cStringIO import StringIO

class RelayRequest(object):
    """ """
    def __init__(self, conf, req, url, proxy=None, conn_timeout=None, node_timeout=None, chunk_size=65536):
        self.req = req
        self.method = req.method
        self.url = url
        self.headers = req.headers
        self.proxy = proxy
        self.chunk_size = chunk_size
        self.conn_timeout = conn_timeout if conn_timeout else 0.5
        self.client_timeout = 60
        self.node_timeout = node_timeout if node_timeout else 60
        self.retry_times_get_response_from_swift = 10
        self.logger = get_logger(conf, log_route='dispatcher.RelayRequest')

    def proxy_request_check(self, proxy, method, path):
        """
        using WebCache when 'Get Object' only.

        """
        if proxy and method == 'GET' and len(path.split('/')) >= 5:
            return True
        else:
            return False

    def split_netloc(self, parsed_url):
        host, port = parsed_url.netloc.split(':')
        if not port:
            if parsed_url.scheme == 'http':
                port = 80
            elif parsed_url.scheme == 'https':
                port = 443
            else:
                return None, None
        return host, port

    def _send_file(self, conn, path):
        """Method for a file PUT coro"""
        while True:
            chunk = conn.queue.get()
            if not conn.failed:
                try:
                    with ChunkWriteTimeout(self.node_timeout):
                        conn.send(chunk)
                        self.logger.debug('Sending...')
                except (Exception, ChunkWriteTimeout):
                    conn.failed = True
                    self.logger.debug('Trying to write to %s' % path)
            conn.queue.task_done()

    def _connect_server(self,  host, port, method, path, headers, query_string):
        with ConnectionTimeout(self.conn_timeout):
            conn = http_connect_raw(host, port, method, path, 
                                    headers=headers, query_string=query_string)
            return conn

    def _connect_put_node(self, host, port, method, path, headers, query_string):
        """Method for a file PUT connect"""
        try:
            with ConnectionTimeout(self.app.conn_timeout):
                conn = http_connect_raw(host, port, method, path, 
                                        headers=headers, query_string=query_string)
            with Timeout(self.app.node_timeout):
                resp = conn.getexpect()
            if resp.status == 100:
                conn.node = node
                return conn
            elif resp.status == 507:
                self.error_limit(node)
        except:
            print 'Expect: 100-continue on %s' % path


    def __call__(self):
        """
        :return httplib.HTTP(S)Connection in success, and webob.exc.HTTPException in failure
        """

        if self.headers.has_key('content-length'):
            if int(self.headers['content-length']) >= MAX_FILE_SIZE:
                return HTTPRequestEntityTooLarge(request=self.req)

        parsed = urlparse(self.url)
        if self.proxy:
            proxy_parsed = urlparse(self.proxy)

        if self.proxy_request_check(self.proxy, self.method, parsed.path):
            host, port = self.split_netloc(proxy_parsed)
            path = self.url
        else:
            host, port = self.split_netloc(parsed)
            path = parsed.path
        self.headers['host'] = '%s:%s' % (host, port)

        if self.method == 'PUT' and len(parsed.path.split('/')) == 5:
            chunked = self.req.headers.get('transfer-encoding')
            reader = self.req.environ['wsgi.input'].read
            data_source = iter(lambda: reader(self.chunk_size), '')
            bytes_transferred = 0
            # pile = GreenPile()
            # pile.spawn(self._connect_server, host, port, self.method, path, self.headers, parsed.query)
            # conns = [conn for conn in pile if conn]
            # conn = conns[0]
            with ConnectionTimeout(self.conn_timeout):
                conn = http_connect_raw(host, port, self.method, path, 
                                        headers=self.headers, query_string=parsed.query)
            with ContextPool(1) as pool:
                conn.failed = False
                conn.queue = Queue(10)
                pool.spawn(self._send_file, conn, path)
                while True:
                    with ChunkReadTimeout(self.client_timeout):
                        try:
                            chunk = next(data_source)
                        except StopIteration:
                            if chunked:
                                conn.queue.put('0\r\n\r\n')
                            break
                        except Exception, err:
                            self.logger.debug('Chunk Read Error: %s' % err)
                    bytes_transferred += len(chunk)
                    if bytes_transferred > MAX_FILE_SIZE:
                        return HTTPRequestEntityTooLarge(request=self.req)
                    if not conn.failed:
                        conn.queue.put('%x\r\n%s\r\n' % (len(chunk), chunk) if chunked else chunk)
                while True:
                    if conn.queue.empty():
                        break
                    else:
                        sleep(0.1)
                if conn.queue.unfinished_tasks:
                    conn.queue.join()
            # In heavy condition, getresponse() may fails, so it causes 'timed out' in eventlet.greenio.
            # Checking a result of response and retrying prevent it. But is this reason of the error really?
            resp = None
            with Timeout(self.node_timeout):
                for i in range(self.retry_times_get_response_from_swift):
                    self.logger.debug('Retry counter: %s' % i)
                    try:
                        resp = conn.getresponse()
                    except Exception, err:
                        self.logger.debug('get response of PUT Error: %s' % err)
                    if isinstance(resp, BufferedHTTPResponse):
                        break
                    else:
                        sleep(0.1)
            return resp
            # except ChunkReadTimeout, err:
            #     print "ChunkReadTimeout: %s" % err
            #     return HTTPRequestTimeout(request=self.req)
            # except (Exception, TimeoutError), err:
            #     print "Error: %s" % err
            #     return HTTPGatewayTimeout(request=self.req)
        else:
            try:
                with ConnectionTimeout(self.conn_timeout):
                    conn = http_connect_raw(host, port, self.method, path, 
                                            headers=self.headers, query_string=parsed.query)
                with Timeout(self.node_timeout):
                    return conn.getresponse()
            except (Exception, TimeoutError), err:
                self.logger.debug("get response of GET or misc Error: %s" % err)
                return HTTPGatewayTimeout(request=self.req)


class Dispatcher(object):
    """ """
    def __init__(self, conf):
        self.conf = conf
        self.logger = get_logger(conf, log_route='dispatcher')
        self.dispatcher_addr = conf.get('bind_ip', '127.0.0.1')
        self.dispatcher_port = int(conf.get('bind_port', 8000))
        self.ssl_enabled = True if 'cert_file' in conf else False
        self.relay_rule = conf.get('relay_rule')
        self.combinater_char = conf.get('combinater_char', ':')
        self.node_timeout = int(conf.get('node_timeout', 11))
        self.conn_timeout = float(conf.get('conn_timeout', 0.5))
        self.client_timeout = int(conf.get('client_timeout', 60))
        self.req_version_str = 'v1.0'
        self.req_auth_str = 'auth'
        self.merged_combinator_str = '__@@__'
        self.no_split_copy_max_size = int(conf.get('no_split_copy_max_size', MAX_FILE_SIZE))
        self.loc = Location(self.relay_rule)

    def __call__(self, env, start_response):
        """ """
        req = Request(env)
        self.loc.reload()
        loc_prefix = self.location_check(req)
        if self.loc.is_merged(loc_prefix):
            self.logger.debug('enter merge mode')
            resp = self.dispatch_in_merge(req, loc_prefix)
        else:
            self.logger.debug('enter normal mode')
            resp = self.dispatch_in_normal(req, loc_prefix)
        resp.headers['x-colony-dispatcher'] = 'dispatcher processed'
        start_response(resp.status, resp.headerlist)
        if req.method in ('PUT', 'POST'):
            return resp.body
        return resp.app_iter if resp.app_iter is not None else resp.body


    def dispatch_in_normal(self, req, location):
        """ request dispatcher in normal mode """
        resp = self.relay_req(req, req.url, 
                              self._get_real_path(req),
                              self.loc.swift_of(location)[0],
                              self.loc.webcache_of(location))
        resp.headerlist = self._rewrite_storage_url_header(resp.headerlist, location)
        header_names = [h for h, v in resp.headerlist]
        if 'x-storage-url' in header_names \
                and 'x-auth-token' in header_names \
                and 'x-storage-token' in header_names:
            if resp.content_length > 0:
                resp.body = self._rewrite_storage_url_body(resp.body, location)
        return resp

    def dispatch_in_merge(self, req, location):
        """ request dispatcher in merge mode """
        if not self._auth_check(req):
            self.logger.debug('get_merged_auth')
            return self.get_merged_auth_resp(req, location)

        parsed = urlparse(req.url)
        query = parse_qs(parsed.query)
        marker = query['marker'][0] if query.has_key('marker') else None
        account, cont_prefix, container, obj = self._get_merged_path(req)

        if account and cont_prefix and container and obj \
                and req.method == 'PUT' \
                and 'x-copy-from' in req.headers \
                and req.headers['content-length'] == '0':
            cp_cont_prefix, cp_cont, cp_obj = self._get_copy_from(req)
            if not cp_cont_prefix:
                return HTTPNotFound(request=req)
            if cont_prefix == cp_cont_prefix:
                self.logger.debug('copy_in_same_account')
                return self.copy_in_same_account_resp(req, location, 
                                                      cp_cont_prefix, cp_cont, cp_obj,
                                                      cont_prefix, container, obj)
            self.logger.debug('copy_across_accounts')
            return self.copy_across_accounts_resp(req, location, 
                                                  cp_cont_prefix, cp_cont, cp_obj,
                                                  cont_prefix, container, obj)
        if account and cont_prefix and container:
            self.logger.debug('get_merged_container_and_object')
            return self.get_merged_container_and_object_resp(req, location, cont_prefix, container)
        if account and container:
            return HTTPNotFound(request=req)
        if account and marker:
            self.logger.debug('get_merged_containers_with_marker')
            return self.get_merged_containers_with_marker_resp(req, location, marker)
        if account:
            self.logger.debug('get_merged_containers')
            return self.get_merged_containers_resp(req, location)
        return HTTPNotFound(request=req)


    # return Response object

    def get_merged_auth_resp(self, req, location):
        """ """
        resps = []
        for swift in self.loc.swift_of(location):
            resps.append(self.relay_req(req, req.url, 
                                        self._get_real_path(req),
                                        swift,
                                        self.loc.webcache_of(location)))
        error_resp = self.check_error_resp(resps)
        if error_resp:
            return error_resp
        ok_resps = []
        for resp in resps:
            if resp.status_int == 200:
                ok_resps.append(resp)
        resp = Response(status='200 OK')
        resp.headerlist = self._merge_headers(ok_resps, location)
        resp.body = self._merge_storage_url_body([r.body for r in ok_resps], location)
        return resp

    def get_merged_containers_resp(self, req, location):
        """ """
        each_tokens = self._get_each_tokens(req)
        if not each_tokens:
            return HTTPUnauthorized(request=req)
        cont_prefix_ls = []
        real_path = '/' + '/'.join(self._get_real_path(req))
        each_swift_cluster = self.loc.swift_of(location)
        query = parse_qs(urlparse(req.url).query)
        each_urls = [self._combinate_url(req, s[0],  real_path, query) for s in each_swift_cluster]
        resps = []
        for each_url, each_token, each_swift_svrs in zip(each_urls, each_tokens, each_swift_cluster):
            req.headers['x-auth-token'] = each_token
            resp = self.relay_req(req, each_url,
                                  self._get_real_path(req),
                                  each_swift_svrs, 
                                  self.loc.webcache_of(location))
            resps.append((each_url, resp))
        error_resp = self.check_error_resp([r for u, r in resps])
        if error_resp:
            return error_resp
        ok_resps = []
        ok_cont_prefix = []
        for url, resp in resps:
            if resp.status_int >= 200 and resp.status_int <= 299:
                ok_resps.append(resp)
                ok_cont_prefix.append(self.loc.container_prefix_of(location, url))
        m_body = ''
        m_headers = self._merge_headers(ok_resps, location)
        if req.method == 'GET':
            if self._has_header('content-type', ok_resps):
                content_type = [v for k,v in m_headers if k == 'content-type'][0]
                m_body = self._merge_container_lists(content_type, 
                                                    [r.body for r in ok_resps], 
                                                    ok_cont_prefix)
        resp = Response(status='200 OK')
        resp.headerlist = m_headers
        resp.body = m_body
        return resp

    def get_merged_containers_with_marker_resp(self, req, location, marker):
        """ """
        if marker.find(self.combinater_char) == -1:
            return HTTPNotFound(request=req)
        marker_prefix = self._get_container_prefix(marker)
        if not self.loc.servers_by_container_prefix_of(location, marker_prefix):
            return HTTPNotFound(request=req)
        real_marker = marker.split(marker_prefix + ':')[1]
        swift_svrs = self.loc.servers_by_container_prefix_of(location, marker_prefix)
        swift_server_subscript = self._get_servers_subscript_by_prefix(location, marker_prefix)
        each_tokens = self._get_each_tokens(req)
        query = parse_qs(urlparse(req.url).query)
        query['marker'] = real_marker
        real_path = '/' + '/'.join(self._get_real_path(req))
        url = self._combinate_url(req, swift_svrs[0], real_path, query)
        req.headers['x-auth-token'] = each_tokens[swift_server_subscript]
        resp = self.relay_req(req, url,
                              self._get_real_path(req),
                              swift_svrs,
                              self.loc.webcache_of(location))
        m_headers = self._merge_headers([resp], location)
        m_body = ''
        if req.method == 'GET':
            if self._has_header('content-type', [resp]):
                content_type = [v for k,v in m_headers if k == 'content-type'][0]
                m_body = self._merge_container_lists(content_type, [resp.body], [marker_prefix])
        resp = Response(status='200 OK')
        resp.headerlist = m_headers
        resp.body = m_body
        return resp

    def get_merged_container_and_object_resp(self, req, location, cont_prefix, container):
        """ """
        if not self.loc.servers_by_container_prefix_of(location, cont_prefix):
            return HTTPNotFound(request=req)
        swift_svrs = self.loc.servers_by_container_prefix_of(location, cont_prefix)
        swift_server_subscript = self._get_servers_subscript_by_prefix(location, cont_prefix)
        each_tokens = self._get_each_tokens(req)
        query = parse_qs(urlparse(req.url).query)
        real_path_ls = self._get_real_path(req)
        real_path_ls[2] = container
        real_path = '/' + '/'.join(real_path_ls)
        url = self._combinate_url(req, swift_svrs[0], real_path, query)
        req.headers['x-auth-token'] = each_tokens[swift_server_subscript]
        resp = self.relay_req(req, url,
                              real_path_ls,
                              swift_svrs,
                              self.loc.webcache_of(location))
        resp.headerlist = self._rewrite_object_manifest_header(resp.headerlist, cont_prefix)
        return resp

    def copy_in_same_account_resp(self, req, location, cp_cont_prefix, cp_cont, cp_obj,
                                  cont_prefix, container, obj):
        """ """
        if not self.loc.servers_by_container_prefix_of(location, cont_prefix):
            return HTTPNotFound(request=req)
        swift_svrs = self.loc.servers_by_container_prefix_of(location, cont_prefix)
        swift_server_subscript = self._get_servers_subscript_by_prefix(location, cont_prefix)
        each_tokens = self._get_each_tokens(req)
        query = parse_qs(urlparse(req.url).query)
        req.headers['x-auth-token'] = each_tokens[swift_server_subscript]
        real_path_ls = self._get_real_path(req)
        real_path_ls[2] = container
        real_path = '/' + '/'.join(real_path_ls)
        url = self._combinate_url(req, swift_svrs[0], real_path, query)
        req.headers['x-copy-from'] = '/%s/%s' % (cp_cont, cp_obj)
        resp = self.relay_req(req, url,
                              real_path_ls,
                              swift_svrs,
                              self.loc.webcache_of(location))
        return resp

    def copy_across_accounts_resp(self, req, location, cp_cont_prefix, cp_cont, cp_obj,
                                  cont_prefix, container, obj):
        """
        TODO: use resp.app_iter rather than resp.body.
        """
        # GET object from account A
        each_tokens = self._get_each_tokens(req)
        query = parse_qs(urlparse(req.url).query)
        from_req = req
        from_swift_svrs = self.loc.servers_by_container_prefix_of(location, cp_cont_prefix)
        from_token = each_tokens[self._get_servers_subscript_by_prefix(location, cp_cont_prefix)]
        from_real_path_ls = self._get_real_path(req)
        from_real_path_ls[2] = container
        from_real_path = '/' + '/'.join(from_real_path_ls)
        from_url = self._combinate_url(req, from_swift_svrs[0], from_real_path, None)
        from_req.headers['x-auth-token'] = from_token
        del from_req.headers['content-length']
        del from_req.headers['x-copy-from']
        from_req.method = 'GET'
        from_resp = self.relay_req(from_req, from_url,
                                   from_real_path_ls,
                                   from_swift_svrs,
                                   self.loc.webcache_of(location))
        if from_resp.status_int != 200:
            return self.check_error_resp([from_resp])

        # PUT object to account B
        to_req = req
        obj_size = int(from_resp.headers['content-length'])
        # if smaller then MAX_FILE_SIZE
        if obj_size < self.no_split_copy_max_size:
            return self._create_put_req(to_req, location, 
                                        cont_prefix, each_tokens, 
                                        from_real_path_ls[1], container, obj, query,
                                        from_resp.body,
                                        from_resp.headers['content-length'])
        """
        if large object, split object and upload them.
        (swift 1.4.3 api: Direct API Management of Large Objects)
        """
        max_segment = obj_size / self.no_split_copy_max_size + 1
        cur = str(time.time())
        body = StringIO(from_resp.body)
        for seg in range(max_segment):
            """ 
            <name>/<timestamp>/<size>/<segment> 
            server_modified-20111115.py/1321338039.34/79368/00000075
            """
            split_obj = '%s/%s/%s/%08d' % (obj, cur, obj_size, seg)
            split_obj_name = quote(split_obj, '')
            chunk = body.read(self.no_split_copy_max_size)
            to_resp = self._create_put_req(to_req, location, 
                                           cont_prefix, each_tokens, 
                                           from_real_path_ls[1], container, 
                                           split_obj_name, None,
                                           chunk,
                                           len(chunk))
            if to_resp.status_int != 201:
                body.close() 
                return self.check_error_resp([to_resp])
        # upload object manifest
        body.close() 
        to_req.headers['x-object-manifest'] = '%s/%s/%s/%s/' % (container, obj, cur, obj_size)
        return self._create_put_req(to_req, location, 
                                    cont_prefix, each_tokens, 
                                    from_real_path_ls[1], container, obj, query,
                                    None,
                                    0)


    # utils

    def check_error_resp(self, resps):
        status_ls = [r.status_int for r in resps]
        if [s for s in status_ls if not str(s).startswith('20')]:
            error_status = max(status_ls)
            for resp in resps:
                if resp.status_int == error_status:
                    return resp
        return None

    def location_check(self, req):
        loc_prefix = req.path.split('/')[1].strip()
        if loc_prefix == self.req_version_str:
            return None
        if loc_prefix == self.req_auth_str:
            return None
        return loc_prefix

    def _get_real_path(self, req):
        if self.location_check(req):
            path = req.path.split('/')[2:]
        else:
            path = req.path.split('/')[1:]
        return [p for p in path if p]


    def _auth_check(self, req):
        if 'x-auth-token' in req.headers or 'x-storage-token' in req.headers:
            return True
        return False

    def  _get_merged_path(self, req):
        path = self._get_real_path(req)[1:]
        if len(path) >= 3:
            account = path[0]
            container = unquote(path[1])
            obj = '/'.join(path[2:])
            cont_prefix = self._get_container_prefix(container)
            real_container = container.split(cont_prefix + self.combinater_char)[1] if cont_prefix else container
            return account, cont_prefix, real_container, obj
        if len(path) == 2:
            account, container = path
            container = unquote(container)
            cont_prefix = self._get_container_prefix(container)
            real_container = container.split(cont_prefix + self.combinater_char)[1] if cont_prefix else container
            return account, cont_prefix, real_container, None
        if len(path) == 1:
            account = path
            return account, None, None, None
        return None, None, None, None

    def _get_container_prefix(self, container):
        if container.find(self.combinater_char) > 0:
            cont_prefix = container.split(self.combinater_char)[0]
            return cont_prefix
        return None

    def _get_copy_from(self, req):
        cont, obj = [c for c in req.headers['x-copy-from'].split('/') if c]
        cont_prefix = self._get_container_prefix(cont)
        real_cont = cont.split(cont_prefix + ':')[1] if cont_prefix else cont
        return cont_prefix, real_cont, obj


    def _merge_headers(self, resps, location):
        """ """
        storage_urls = []
        tokens = []
        if self._has_header('x-storage-url', resps):
            storage_urls = [r.headers['x-storage-url'] for r in resps]
        if self._has_header('x-auth-token', resps):
            tokens = [r.headers['x-auth-token'] for r in resps]
        ac_byte_used = 0
        ac_cont_count = 0
        ac_obj_count = 0
        if self._has_header('X-Account-Bytes-Used', resps):
            ac_byte_used = sum([int(r.headers['X-Account-Bytes-Used']) for r in resps])
        if self._has_header('X-Account-Container-Count', resps):
            ac_cont_count = sum([int(r.headers['X-Account-Container-Count']) for r in resps])
        if self._has_header('X-Account-Object-Count', resps):
            ac_obj_count = sum([int(r.headers['X-Account-Object-Count']) for r in resps])
        misc = {}
        for r in resps:
            for h, v in r.headers.iteritems():
                if not h in ('x-storage-url', 
                             'x-auth-token', 'x-storage-token', 
                             'x-account-bytes-used', 
                             'x-account-container-count', 
                             'x-account-object-count'):
                    misc[h] = v
        merged = []
        if len(storage_urls) > 0:
            merged.append(('x-storage-url', 
                           self._get_merged_storage_url(storage_urls, location)))
        if len(tokens) > 0:
            merged.append(('x-auth-token', 
                           self.merged_combinator_str.join(tokens)))
            merged.append(('x-storage-token', 
                           self.merged_combinator_str.join(tokens)))
        if ac_byte_used:
            merged.append(('x-account-bytes-used', str(ac_byte_used)))
        if ac_cont_count:
            merged.append(('x-account-container-count', str(ac_cont_count)))
        if ac_obj_count:
            merged.append(('x-account-object-count', str(ac_obj_count)))
        for header in misc.keys():
            merged.append((header, misc[header]))
        return merged

    def _get_merged_common_path(self, urls):
        paths = [urlparse(u).path for u in urls]
        if not filter(lambda a: paths[0] != a, paths):
            return paths[0]
        return None

    def _get_merged_storage_url(self, urls, location):
        scheme = 'https' if self.ssl_enabled else 'http'
        common_path = self._get_merged_common_path(urls)
        if not common_path: # swauth case
            common_path = urlsafe_b64encode(self.merged_combinator_str.join(urls))
        if location:
            path = '/' + location + common_path
        else:
            path = common_path
        return urlunparse((scheme, 
                           '%s:%s' % (self.dispatcher_addr, self.dispatcher_port),
                           path, None, None, None))

    def _has_header(self, header, resps):
        return sum([1 for r in resps if r.headers.has_key(header)])

    def _merge_storage_url_body(self, bodies, location):
        """ """
        storage_merged = {'storage': {}}
        storage_urls = []
        for body in bodies:
            storage = json.loads(body)
            for k, v in storage['storage'].iteritems():
                parsed = urlparse(v)
                if parsed.scheme == '':
                    storage_merged['storage'][k] = v
                else:
                    storage_urls.append(v)
        storage_merged['storage'][k] = \
            self._get_merged_storage_url(storage_urls, location)
        return json.dumps(storage_merged)

    def _get_each_tokens(self, req):
        auth_token = req.headers.get('x-auth-token') or req.headers.get('x-storage-token')
        if auth_token.find(self.merged_combinator_str) == -1:
            return None
        return auth_token.split(self.merged_combinator_str)


    def _get_servers_subscript_by_prefix(self, location, prefix):
        swift_svrs = self.loc.servers_by_container_prefix_of(location, prefix)
        i = 0
        found = None
        for svrs in self.loc.swift_of(location):
            for svr in svrs:
                if svr in swift_svrs:
                    found = True
                    break
            if found:
                break
            i += 1
        return i


    def _combinate_url(self, req, swift_svr, real_path, query):
        parsed = urlparse(req.url)
        choiced = urlparse(swift_svr)
        url = (choiced.scheme, 
               choiced.netloc, 
               real_path, 
               parsed.params, 
               urlencode(query, True) if query else None,
               parsed.fragment)
        return urlunparse(url)

    def _create_put_req(self, to_req, location, prefix, each_tokens, 
                       account, cont, obj, query, body, to_size):
        """ """
        to_swift_svrs = self.loc.servers_by_container_prefix_of(location, prefix)
        to_token = each_tokens[self._get_servers_subscript_by_prefix(location, prefix)]
        to_real_path = '/%s/%s/%s/%s' % (self.req_version_str,
                                         account, cont, obj)
        to_real_path_ls = to_real_path.split('/')[1:]
        to_url = self._combinate_url(to_req, to_swift_svrs[0], to_real_path, query)
        to_req.headers['x-auth-token'] = to_token
        to_req.headers['content-length'] = to_size
        if to_req.headers.has_key('x-copy-from'):
            del to_req.headers['x-copy-from'] 
        to_req.method = 'PUT'
        if isinstance(body, file):
            to_req.body_file = body
        else:
            to_req.body = body
        to_resp = self.relay_req(to_req, to_url,
                                 to_real_path_ls,
                                 to_swift_svrs,
                                 self.loc.webcache_of(location))
        return to_resp

    def _rewrite_object_manifest_header(self, headers, container_prefix):
        rewrited = []
        for h, v in headers:
            if h == 'x-object-manifest':
                v = container_prefix + ':' + v
            rewrited.append((h, v))
        return rewrited

    def _rewrite_storage_url_header(self, headers, path_location_prefix=None):
        """ """
        rewrited = []
        for header, value in headers:
            if header == 'x-storage-url':
                parsed = urlparse(value)
                if path_location_prefix:
                    path = '/' + path_location_prefix + parsed.path
                else:
                    path = parsed.path
                scheme = 'https' if self.ssl_enabled else 'http'
                rewrite_url = (scheme, '%s:%s' % (self.dispatcher_addr, self.dispatcher_port),\
                                   path, parsed.params, parsed.query, parsed.fragment)
                rewrited.append(('x-storage-url', urlunparse(rewrite_url)))
            else:
                rewrited.append((header, value))
        return rewrited

    def _rewrite_storage_url_body(self, body, path_location_prefix=None):
        """ """
        # some auth filter (includes tempauth) doesn't return json body
        try:
            storage = json.loads(body)
        except ValueError:
            return body
        storage_rewrite = {'storage': {}}
        for k, v in storage['storage'].iteritems():
            parsed = urlparse(v)
            if parsed.scheme == '':
                storage_rewrite['storage'][k] = v
            else:
                if path_location_prefix:
                    path = '/' + path_location_prefix + parsed.path
                else:
                    path = parsed.path
                scheme = 'https' if self.ssl_enabled else 'http'
                rewrite_url = (scheme, '%s:%s' % (self.dispatcher_addr, self.dispatcher_port),\
                                   path, parsed.params, parsed.query, parsed.fragment)
                storage_rewrite['storage'][k] = urlunparse(rewrite_url)
        return json.dumps(storage_rewrite)

    def _merge_container_lists(self, content_type, bodies, prefixes):
        """ """
        if content_type.startswith('text/plain'):
            merge_body = []
            for prefix, body in zip(prefixes, bodies):
                for b in body.split('\n'):
                    if b != '':
                        merge_body.append(str(prefix) + self.combinater_char + b)
            merge_body.sort(cmp)
            return '\n'.join(merge_body)
        elif content_type.startswith('application/json'):
            merge_body = []
            for prefix, body in zip(prefixes, bodies):
                tmp_body = json.loads(body)
                for e in tmp_body:
                    e['name'] = prefix + self.combinater_char + e['name']
                    merge_body.append(e)
            return json.dumps(merge_body)
        elif content_type.startswith('application/xml'):
            pass
        else:
            pass


    # relay request

    def relay_req(self, req, req_url, path_str_ls, relay_servers, webcaches):
        """ """
        # util
        def get_relay_netloc(relay_server):
            parsed = urlparse(relay_server)
            svr = parsed.netloc.split(':')
            if len(svr) == 1:
                relay_addr = svr[0]
                relay_port = '443' if parsed.scheme == 'https' else '80'
            else:
                relay_addr, relay_port = svr
            return relay_addr, relay_port

        parsed_req_url = urlparse(req_url)
        relay_servers_count = len(relay_servers)
        for relay_server in relay_servers:
            relay_addr, relay_port = get_relay_netloc(relay_server)
            connect_url = urlunparse((parsed_req_url.scheme, 
                                      relay_addr + ':' + relay_port, 
                                      '/' + '/'.join(path_str_ls),
                                      parsed_req_url.params, 
                                      parsed_req_url.query, 
                                      parsed_req_url.fragment))
            if webcaches[relay_server]:
                proxy = webcaches[relay_server]
            else:
                proxy = None

            self.logger.debug('Req: %s %s, Connect to %s via %s' % 
                             (req.method, req.url, connect_url, proxy))

            result = RelayRequest(self.conf, req, connect_url, proxy=proxy, 
                                  conn_timeout=self.conn_timeout, node_timeout=self.node_timeout)()

            if isinstance(result, HTTPException):
                if relay_servers_count > 1:
                    relay_servers_count -= 1
                    self.logger.info('Retry Req: %s %s, Connect to %s via %s' %
                                     (req.method, req.url, connect_url, proxy))
                    continue
                else:
                    return result

            response = Response(status='%s %s' % (result.status, result.reason))
            response.bytes_transferred = 0

            def response_iter():
                try:
                    while True:
                        with ChunkReadTimeout(60):
                            chunk = result.read(65535)
                        if not chunk:
                            break
                        yield chunk
                        response.bytes_transferred += len(chunk)
                except GeneratorExit:
                    pass
                except (Exception, TimeoutError):
                    raise
            response.headerlist = result.getheaders()
            response.content_length = result.getheader('Content-Length')
            if response.content_length < 4096:
                response.body = result.read()
            else:
                response.app_iter = response_iter()
                update_headers(response, {'accept-ranges': 'bytes'})
                response.content_length = result.getheader('Content-Length')
            update_headers(response, result.getheaders())
            if req.method == 'HEAD':
                update_headers(response, {'Content-Length': 
                                          result.getheader('Content-Length')})
            response.status = result.status
        return response

def app_factory(global_conf, **local_conf):
    """paste.deploy app factory for creating WSGI proxy apps."""
    conf = global_conf.copy()
    conf.update(local_conf)
    return Dispatcher(conf)
