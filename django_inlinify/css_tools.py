import re
import logging
import requests
import cssutils
from django.core.cache import get_cache, InvalidCacheBackendError
from django.conf import settings
from django_inlinify import defaults
from StringIO import StringIO
from contextlib import closing
from hashlib import md5

log = logging.getLogger('django_inlinify.css_loader')

DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME = getattr(
    settings,
    'DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME',
    defaults.DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME
)

# These pseudo selectors are ok to inline as they just filter the elements matched,
# as apposed to things like :hover or :focus which can't be inlined.
FILTER_PSEUDO_SELECTORS = [':last-child', ':first-child', ':nth-child']

# Regular expression to find number of different elements being targeted by a selector
ELEMENT_SELECTOR_REGEX = re.compile(r'(^|\s)\w')

# Regular expression to find all pseudo selectors in a selector
PSEUDO_SELECTOR_REGEX = re.compile(r':[a-z\-]+')


def load_cache(cache_name):
    """
    Tries to load the specified cache. If there is any problem, falls back to the default one

    Arguments:
        - str cache_name: the name of the cache backend to use

    Returns:
        cache object
    """
    if not cache_name:
        return get_cache(DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME)
    try:
        cache = get_cache(cache_name)
    except InvalidCacheBackendError:
        log.error('The cache you specified (%s) is not defined in settings. Falling back to '
                  'the default one (%s)', cache_name, DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME)
        cache = get_cache(DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME)
    return cache


class CSSLoader(object):
    """Class responsible for loading CSS files. Supports local and remote files
    """

    DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX = getattr(settings,
                                         'DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX',
                                         defaults.DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX)
    DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL = getattr(settings,
                                      'DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL',
                                      defaults.DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL)

    def __init__(self, files, cache_backend=None):
        self.files = files if files else []
        self.cache = load_cache(cache_backend)

    def _get_cache_key(self, filepath):
        return '%s_filecontents_%s_' % (self.DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX, filepath)

    def _get_cached_contents(self, filename):
        return self.cache.get(self._get_cache_key(filename))

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
        """Reads the contents of the file located in the provided filepath

        Arguments:
            - str filepath: the path to the file

        Returns:
            the contents of the file
        """
        cached = self._get_cached_contents(filepath)
        if cached:
            return cached
        if filepath.startswith('http://') or filepath.startswith('https://'):
            contents = self._get_file_contents_from_url(filepath)
        else:
            contents = self._get_file_contents_from_local_file(filepath)

        self.cache.set(self._get_cache_key(filepath),
                       contents,
                       self.DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL)

        return contents

    def __iter__(self):
        for f in self.files:
            yield self._read_file(f)


class CSSParser(object):
    """Class responsible for parsing CSS
    """

    DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX = getattr(
        settings,
        'DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX',
        defaults.DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX
    )

    DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL = getattr(
        settings,
        'DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL',
        defaults.DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL
    )

    DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING = getattr(
        settings,
        'DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING',
        defaults.DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING
    )

    def __init__(self, cache_backend=None, **kwargs):
        self.cache = load_cache(cache_backend)
        self.include_star_selectors = kwargs.get('include_star_selectors', False)

    def _get_cache_key(self, css_body, index):
        h = md5(str(css_body)).hexdigest()
        return '%s_contents_%s_%s' % (self.DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX, h, index)

    def _get_cached_css(self, css_body, index):
        return self.cache.get(self._get_cache_key(css_body, index))

    def parse(self, css_body, ruleset_index):
        """Extracts the rules from a CSS string. If they are cached, return those. Otherwise,
        extract them and cache them
        """
        cached = self._get_cached_css(css_body, ruleset_index)
        if cached:
            return cached
        parsed = self._parse_style_rules(css_body, ruleset_index)
        self.cache.set(self._get_cache_key(css_body, ruleset_index), parsed,
                       self.DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL)
        return parsed

    def _parse_style_rules(self, css_body, ruleset_index):
        """Given a CSS string, extracts all its rules from it
        """
        leftover = []
        rules = []
        rule_index = 0

        # empty string
        if not css_body:
            return rules, leftover

        sheet = cssutils.parseString(css_body, validate=False)
        for rule in sheet:
            # handle media and font rules
            if rule.type in (rule.MEDIA_RULE, rule.FONT_FACE_RULE):
                leftover.append(rule)
                continue

            # only proceed for things we recognize
            if rule.type != rule.STYLE_RULE:
                continue

            bulk = ';'.join(
                u'{0}:{1}'.format(key, rule.style[key])
                for key in rule.style.keys()
            )
            selectors = (
                x.strip()
                for x in rule.selectorText.split(',')
                if x.strip() and not x.strip().startswith('@')
            )
            for selector in selectors:
                pseudos = [x.group(0) for x in PSEUDO_SELECTOR_REGEX.finditer(selector)]
                if any(pseudo not in FILTER_PSEUDO_SELECTORS for pseudo in pseudos):
                    leftover.append((selector, bulk))
                    continue
                elif '*' in selector and not self.include_star_selectors:
                    continue

                # Crudely calculate specificity
                id_count = selector.count('#')
                class_count = selector.count('.')
                element_count = len(ELEMENT_SELECTOR_REGEX.findall(selector))

                specificity = (id_count, class_count, element_count, ruleset_index, rule_index)

                rules.append((specificity, selector, bulk))
                rule_index += 1

        # we want to return a string, not those crazy CSSRule objects.
        # This will make serialization much faster
        leftover = self._css_rules_to_string(leftover)

        return rules, leftover

    def _make_important(self, bulk):
        """
        Marks every property in a string as `!important`
        """

        return ';'.join('%s !important' % p if not p.endswith('!important') else p for p in
                        bulk.split(';'))

    def _css_rules_to_string(self, rules):
        """
        Given a list of css rules returns a css string

        Arguments:
            - list rules: it can be either a list of cssutils.css.cssrule.CSSRule objects or tuples

        Returns:
            the CSS style string
        """
        lines = []
        for item in rules:
            if isinstance(item, tuple):
                k, v = item
                lines.append('%s {%s}' % (k, self._make_important(v)))
            elif item.type == item.FONT_FACE_RULE:
                lines.append(item.cssText)
            elif item.type == item.MEDIA_RULE:
                for rule in item.cssRules:
                    if isinstance(rule, cssutils.css.csscomment.CSSComment):
                        continue
                    for key in rule.style.keys():
                        rule.style[key] = (rule.style.getPropertyValue(key, False), '!important')
                lines.append(item.cssText)
        return '\n'.join(lines)

    def merge_styles(self, old_style, new_style):
        """
        Given two CSS styles, merges both so that any new style overrides the old ones

        Arguments:
            - str old_style: the old CSS style
            - str new_style: the new CSS style

        Returns:
            the new css style as a string
        """
        old_style_dict = self._css_string_to_dict(old_style)
        style_dict = self._css_string_to_dict(new_style)
        old_style_dict.update(style_dict)
        return '; '.join(['%s:%s' % (k, v) for k, v in sorted(old_style_dict.iteritems())])

    def _unbalanced(self, text):
        """
        Checks if there is an unbalanced parenthesis or braket in the provided text. Assumes that
        the text is processed left to right

        Arguments:
            - str text: the text to check

        Returns:
            true if its unbalanced, false otherwise
        """
        if text.count('(') and text.count('(') != text.count(')'):
            return True
        if text.count('{') and text.count('}') != text.count('}'):
            return True
        return False

    def _css_string_to_dict(self, css):
        """Given a string containing CSS, creates a dictionary out of it, where the keys are CSS
        properties and the values are their corresponding values

        This method assumes that CSS key-value pairs are separated by a semicolon. If this is not true,
        it can return unexpected results or even break

        Arguments:
            - str css: the css text

        Returns:
            a dictionary as described above
        """
        buff = ''
        css_properties = []
        for item in css.split(';'):
            # if we have any buffer, append the current item to the buffer
            if buff:
                item = buff + ';' + item
                buff = ''

            # if this breaks any parenthesis, brakets, buffer it and continue
            if self._unbalanced(item):
                buff = item
                continue

            # we are good to add the property
            if item.strip():
                css_properties.append(item.strip())

        # split every property into key, value and store them in a dict
        d = {}
        for css_property in css_properties:
            chunks = css_property.split(':', 1)
            d[chunks[0].strip()] = chunks[1].strip()
        return d

    def css_style_to_basic_html_attributes(self, element, style_content):
        """Given an element and styles like 'background-color:red; font-family:Arial' turn some of
        that into HTML attributes

        Note, the style_content can contain pseudoclasses like:
        '{color:red; border:1px solid green} :visited{border:1px solid green}'
        """
        if style_content.count('}') and style_content.count('{') == style_content.count('}'):
            style_content = style_content.split('}')[0][1:]

        mappings = self.DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING

        for key, value in [
            x.split(':')
            for x in style_content.split(';') if len(x.split(':')) == 2
        ]:
            try:
                new_key, new_value = mappings.get(key.strip())
            except TypeError:
                continue
            else:
                element.attrib[new_key] = new_value(value)
