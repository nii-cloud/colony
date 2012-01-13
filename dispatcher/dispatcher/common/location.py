# coding=utf-8
import os
from urlparse import urlparse
import time
import socket
import re

class Location(object):

    def __init__(self, location_str):
        self.locations = None
        self.location_str = location_str
        self.locations, self.age = self._load(location_str)
        if self.age == 0:
            raise ValueError('initialize error.')
        

    def _load(self, location_str):
        locations = None
        age = 0
        try:
            locations, age = self._parse_location_str(self.location_str)
        except Exception, err:
            if self.locations != None:
                print 'Error: %s go on using old location settings.' % err
                return self.locations, age
            print err
        return locations, age

    def reload(self):
        try:
            if self.check_file_age(self.location_str) > self.age:
                locations, age = self._load(self.location_str)
                if age == 0:
                    self.age = age
                else:
                    self.locations = locations
                    self.age = age
        except Exception, err:
            print 'Error: %s go on using old location settings.' % err

    def servers_of(self, location_str):
        if location_str:
            try:
                return self.locations[location_str]
            except KeyError:
                return None
        else:
            return self.locations['']

    def swift_of(self, location_str):
        if location_str:
            try:
                return self.locations[location_str]['swift']
            except KeyError:
                return None
        else:
            return self.locations['']['swift']

    def webcache_of(self, location_str):
        if location_str:
            try:
                return self.locations[location_str]['webcache']
            except KeyError:
                return None
        else:
            return self.locations['']['webcache']

    def is_merged(self, prefix_str):
        if prefix_str:
            try:
                if len(self.locations[prefix_str]['swift']) > 1:
                    return True
                return False
            except KeyError:
                return None
        else:
            if len(self.locations['']['swift']) > 1:
                return True
            return False

    def container_prefix_of(self, location_str, swift):
        if location_str:
            try:
                cont_prefix = self.locations[location_str]['container_prefix']
            except KeyError:
                return False
        else:
            cont_prefix = self.locations['']['container_prefix']
        p = urlparse(swift)
        key = p.scheme + '://' + p.netloc
        try:
            cont_prefix_name = cont_prefix[key]
        except KeyError:
            return False
        if cont_prefix_name:
            return cont_prefix_name
        return None

    def container_prefixes_of(self, location_str):
        if location_str:
            try:
                return self.locations[location_str]['container_prefix']
            except KeyError:
                return None
        else:
            return self.locations['']['container_prefix']

    def servers_by_container_prefix_of(self, location_str, container_prefix):
        return [k for k,v in self.container_prefixes_of(location_str).iteritems() if v == container_prefix]

    def _parse_location_str(self, location_str):

        """
        識別子A:サーバーリスト1, 識別子B: サーバリスト2 サーバーリスト3
        - 識別子はURLのPATH要素の先頭ディレクトリ名
        - コロンで接続された文字列は、接続対象のswiftサーバのリストのファイル。スペースで区切って複数のファイルを指定可能
        - 複数のサーバーリストファイルを持つ識別子は、2つ以上のswiftのコンテナリストの結果を融合するマージモード動作となる
        - サーバリストファイルの先頭に'('と')'で囲まれた文字列があった場合には、マージモード時のコンテナの修飾プリフィックスになる（省略可）
        - 識別子とサーバーリストファイルの組は、カンマで区切って複数指定する
        - サーバリストは、swiftのURL（スキーム・ホスト名・ポート番号）を1行ごとに記述したもの
        - 更に、swift URLの後にカンマで連結してそのswift URLに対するWebCacheサーバを指定できる（省略可）
        - 識別子が空文字列の場合には、デフォルト動作の指定となる
    
        :param location_str: a string like 'local:/etc/dispatcher/server0.txt, both:(cont_prefx0)/etc/dispatcher/server1.txt (cont_prefx0)/etc/dispatcher/server1.txt'
    
        :return dict: '{location_name0: {'swift': [['http://192.168.0.1:8080']],
                                         'webcache': {'http://192.168.0.0:8080': 'http://proxy.nii.sc.jp:8080'}},
                        location_name1: {'swift': [['http://192.168.0.2:8080','http://192.168.0.3:8080']],
                                         'webcache': {'http://192.168.0.2:8080': None, 'http://192.168.0.3:8080': None}},
                        location_name3(both): {'swift': [['http://192.168.0.4:8080'], ['http://192.168.10.5:8080', 'http://192.168.10.6:8080']],
                                         'webcache': {'http://192.168.0.4:8080': None, 'http://192.168.10.5:8080': None, 'http://192.168.10.6:8080: None'}}}
        :return file_age: the newest mtime of server list files
        """
        location = {}
        file_age = None
        try:
            for loc in location_str.split(','):
                loc_prefix, files = loc.split(':')
                location[loc_prefix.strip()] = {'swift': [], 'webcache': {}, 'container_prefix': {}}
                webcache_svrs = {}
                container_prefix = {}
                for f in files.split(None):
                    prefix = None
                    if f.startswith('('):
                        f_str = f.split(')')
                        prefix = f_str[0].split('(')[1]
                        f = f_str[1]
                    tmp_file_age = os.stat(f).st_mtime
                    if file_age:
                        if file_age < tmp_file_age:
                            file_age = tmp_file_age
                    else:
                        file_age = tmp_file_age
                    with open(f) as fh:
                        swift_ls = []
                        for line in fh.readlines():
                            if line.startswith('#'):
                                continue
                            svr_ls = line.split(',')
                            if len(svr_ls) == 2:
                                webcache = svr_ls[1].strip()
                                if not re.match('^http.?://.+', webcache):
                                    raise ValueError('no url string.')
                            else:
                                webcache = None
                            swift = svr_ls[0].strip()
                            if not re.match('^http.?://.+', swift):
                                raise ValueError('no url string.')
                            parsed = urlparse(swift)
                            webcache_svrs[swift] = webcache
                            container_prefix[parsed.scheme + '://' + parsed.netloc] = prefix
                            swift_ls.append(swift)
                        swift_ls = self._sock_connect_faster(swift_ls)
                        location[loc_prefix.strip()]['swift'].append(swift_ls)
                        location[loc_prefix.strip()]['webcache'] = webcache_svrs
                        location[loc_prefix.strip()]['container_prefix'] = container_prefix
        except ValueError, err:
            raise ValueError('location str format is wrong: %s' % err)
        except OSError, err:
            raise ValueError('server list file is missing: %s' % err)
        except Exception, err:
            raise ValueError('something happened: %s' % err)
        return location, file_age


    def check_file_age(self, location_str):
        """ """
        file_age = None
        for loc in location_str.split(','):
            loc_prefix, files = loc.split(':')
            for f in files.split(None):
                if f.startswith('('):
                    f_str = f.split(')')
                    f = f_str[1]
                tmp_file_age = os.stat(f).st_mtime
            if file_age:
                if file_age < tmp_file_age:
                    file_age = tmp_file_age
            else:
                file_age = tmp_file_age
        return file_age

    def _sock_connect_faster(self, urls, conn_timeout=0.1):
        """ """
        faster = []
        for url in urls:
            nl = urlparse(url).netloc.split(':')
            scheme = urlparse(url).scheme
            addr = (nl[0], nl[1]) if len(nl) == 2 \
                else (nl[0], 80 if scheme == 'http' else 443)
            now = time.time()
            try:
                sock = None
                sock = socket.create_connection(addr, conn_timeout)
                then = time.time()
            except socket.error:
                then = time.time() + 86400
            finally:
                if sock:
                    sock.close()
            delta = then - now
            faster.append((delta, url))
        faster.sort()
        return [f[1] for f in faster]

# if __name__ == "__main__":
#     location_str = ':etc/server0.txt, local:etc/server1.txt, both:(hoge)etc/server2.txt (gere)etc/server3.txt'
#     loc = Location(location_str)
