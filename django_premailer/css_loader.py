import logging
import requests
from django.core.cache import get_cache, InvalidCacheBackendError
from django.conf import settings
from StringIO import StringIO
from contextlib import closing

log = logging.getLogger('django_premailer.css_loader')

DEFAULT_CACHE_BACKEND_NAME = getattr(settings, 'DEFAULT_CACHE_BACKEND_NAME', 'default')


def load_cache(cache_name):
    """
    Tries to load the specified cache. If there is any problem, falls back to the default one

    Arguments:
        - str cache_name: the name of the cache backend to use

    Returns:
        cache object
    """
    if not cache_name:
        return get_cache(DEFAULT_CACHE_BACKEND_NAME)
    try:
        cache = get_cache(cache_name)
    except InvalidCacheBackendError:
        log.error('The cache you specified (%s) is not defined in settings. Falling back to '
                  'the default one (%s)', cache_name, DEFAULT_CACHE_BACKEND_NAME)
        cache = get_cache(DEFAULT_CACHE_BACKEND_NAME)
    return cache


class CSSLoader(object):
    """Class responsible of loading CSS files. Supports local and remote files
    """

    CACHE_KEY_PREFIX = 'premailer_cache_'
    CACHE_KEY_TTL = 60 * 60 * 12

    def __init__(self, files, premailer, cache_backend=None):
        self.files = files if files else []
        self.premailer = premailer
        self.cache = load_cache(cache_backend)

    def _get_contents_key(self, filename, index):
        return '%s_contents_%s_%s' % (self.CACHE_KEY_PREFIX, filename, index)

    def get_cached_contents(self, filename, index):
        return self.cache.get(self._get_contents_key(filename, index))

    def _get_file_contents_from_url(self, filepath):
        """Reads a remote file and returns its contents
        """
        response = requests.get(filepath, stream=True)
        if response.status_code != 200:
            raise ValueError('The CSS file you specified (%s) does not exist. Response (%s - %s)' %
                             (filepath, response.status_code, response.reason))

        with closing(StringIO()) as contents:
            for chunk in response.iter_content(512):
                contents.write(chunk)
        return contents.getvalue()

    def _get_file_contents_from_local_file(self, filepath):
        """Reads a file stored locally and returns its contents
        """
        with open(filepath) as f:
            contents = f.read()
        return contents

    def _read_file(self, filepath):
        """
        Read file contents

        Arguments:
            - str filepath: the path to the file

        Returns:
            the contents of the file
        """
        if filepath.startswith('http://') or filepath.startswith('https://'):
            return self._get_file_contents_from_url(filepath)
        return self._get_file_contents_from_local_file(filepath)

    def _get_parsed_css(self, filepath, index):
        """
        Returns the parsed css from the provided filename. Caches it

        Arguments:
            - str filepath: the path to the file (either a URL or local file system path)
            - int index: index used to establish the precedence of CSS rules when parsing them

        Returns:
            parsed css and the raw css
        """
        contents = self._read_file(filepath)
        print contents
        parsed = list(self.premailer.parse_style_rules(contents, index))
        parsed.append(contents)
        print parsed
        self.cache.set(self._get_contents_key(filepath, index), parsed, self.CACHE_KEY_TTL)
        return parsed

    def __iter__(self):
        for index, file in enumerate(self.files):
            cached = self.get_cached_contents(file, index)
            if cached:
                yield cached
            else:
                yield self._get_parsed_css(file, index)
