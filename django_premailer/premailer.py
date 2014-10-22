from __future__ import absolute_import, unicode_literals, print_function
from collections import OrderedDict
import operator
import re
import sys
import threading
if sys.version_info >= (3, ):  # pragma: no cover
    # As in, Python 3
    from urllib.parse import urljoin
    STR_TYPE = str
else:  # Python 2
    from urlparse import urljoin
    STR_TYPE = basestring
import cssutils


from lxml import etree
from lxml.cssselect import CSSSelector
from django.core.cache import cache

__all__ = ['Premailer']


# compiled regular expresions
grouping_regex = re.compile('([:\-\w]*){([^}]+)}')
element_selector_regex = re.compile(r'(^|\s)\w')

# These selectors don't apply to all elements. Rather, they specify which elements to apply to.
FILTER_PSEUDOSELECTORS = [':last-child', ':first-child', 'nth-child']


def merge_styles(old, new, class_=''):
    """
    if ::
      old = 'font-size:1px; color: red'
    and ::
      new = 'font-size:2px; font-weight: bold'
    then ::
      return 'color: red; font-size:2px; font-weight: bold'

    In other words, the new style bits replace the old ones.

    The @class_ parameter can be something like ':hover' and if that
    is there, you split up the style with '{...} :hover{...}'
    Note: old could be something like '{...} ::first-letter{...}'

    """

    def csstext_to_pairs(csstext):
        parsed = cssutils.css.CSSVariablesDeclaration(csstext)
        for key in sorted(parsed):
            yield (key, parsed.getVariableValue(key))

    new_keys = set()
    news = []

    # The code below is wrapped in a critical section implemented via ``RLock``-class lock.
    # The lock is required to avoid ``cssutils`` concurrency issues documented in issue #65
    with merge_styles._lock:
        for k, v in csstext_to_pairs(new):
            news.append((k.strip(), v.strip()))
            new_keys.add(k.strip())

        groups = {}
        grouped_split = grouping_regex.findall(old)
        if grouped_split:
            for old_class, old_content in grouped_split:
                olds = []
                for k, v in csstext_to_pairs(old_content):
                    olds.append((k.strip(), v.strip()))
                groups[old_class] = olds
        else:
            olds = []
            for k, v in csstext_to_pairs(old):
                olds.append((k.strip(), v.strip()))
            groups[''] = olds

    # Perform the merge
    relevant_olds = groups.get(class_, {})
    merged = [style for style in relevant_olds if style[0] not in new_keys] + news
    groups[class_] = merged

    if len(groups) == 1:
        return '; '.join('%s:%s' % (k, v) for (k, v) in sorted(list(groups.values())[0]))
    else:
        all_ = []
        sorted_groups = sorted(list(groups.items()), key=lambda a: a[0].count(':'))
        for class_, mergeable in sorted_groups:
            all_.append('%s{%s}' % (class_, '; '.join('%s:%s' % (k, v) for k, v in mergeable)))
        return ' '.join(x for x in all_ if x != '{}')

# The lock is used in merge_styles function to work around threading concurrency bug of cssutils library.
# The bug is documented in issue #65. The bug's reproduction test in test_premailer.test_multithreading.
merge_styles._lock = threading.RLock()


def make_important(bulk):
    """makes every property in a string !important.
    """
    return ';'.join('%s !important' % p if not p.endswith('!important') else p for p in bulk.split(';'))


class CSSLoader(object):

    CACHE_KEY_PREFIX = 'premailer_1'

    def __init__(self, files, premailer):
        self.files = files if files else []
        self.premailer = premailer

    def _get_contents_key(self, filename, index):
        return '%s_contents_%s_%s' % (self.CACHE_KEY_PREFIX, filename, index)

    def get_cached_contents(self, filename, index):
        return cache.get(self._get_contents_key(filename, index))

    def create_and_save_contents(self, filename, index):
        with open(filename) as f:
            contents = f.read()
            parsed = list(self.premailer.parse_style_rules(contents, index))
            parsed.append(contents)
            cache.set(self._get_contents_key(filename, index), parsed)
        return parsed

    def __iter__(self):
        for index, file in enumerate(self.files):
            cached = self.get_cached_contents(file, index)
            if cached:
                yield cached
            else:
                yield self.create_and_save_contents(file, index)


class Premailer(object):

    def __init__(self,
                 css_files=None,
                 base_url=None,
                 preserve_internal_links=False,
                 preserve_inline_attachments=True,
                 exclude_pseudoclasses=True,
                 keep_style_tags=False,
                 include_star_selectors=False,
                 remove_classes=True,
                 base_path=None,
                 disable_basic_attributes=None,
                 enable_validation=True):
        self.base_url = base_url
        self.preserve_internal_links = preserve_internal_links
        self.preserve_inline_attachments = preserve_inline_attachments
        self.exclude_pseudoclasses = exclude_pseudoclasses
        # whether to delete the <style> tag once it's been processed
        # this will always preserve the original css
        self.keep_style_tags = keep_style_tags
        self.remove_classes = remove_classes
        # whether to process or ignore selectors like '* { foo:bar; }'
        self.include_star_selectors = include_star_selectors
        self.css_source = CSSLoader(css_files, self)
        self.base_path = base_path
        if disable_basic_attributes is None:
            disable_basic_attributes = []
        self.disable_basic_attributes = disable_basic_attributes

        # enable validation on the cssutils.CSSParser
        self.enable_validation = enable_validation

    def parse_style_rules(self, css_body, ruleset_index):
        leftover = []
        rules = []
        rule_index = 0

        # empty string
        if not css_body:
            return rules, leftover

        sheet = cssutils.parseString(css_body, validate=self.enable_validation)
        for rule in sheet:
            # handle media rule
            if rule.type == rule.MEDIA_RULE:
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
                if (':' in selector and self.exclude_pseudoclasses
                        and ':' + selector.split(':', 1)[1] not in FILTER_PSEUDOSELECTORS):
                    # a pseudoclass
                    leftover.append((selector, bulk))
                    continue
                elif '*' in selector and not self.include_star_selectors:
                    continue

                # Crudely calculate specificity
                id_count = selector.count('#')
                class_count = selector.count('.')
                element_count = len(element_selector_regex.findall(selector))

                specificity = (id_count, class_count, element_count, ruleset_index, rule_index)

                rules.append((specificity, selector, bulk))
                rule_index += 1

        return rules, leftover

    def transform(self, html, pretty_print=True, **kwargs):
        """Transform CSS into inline styles and inject them in the provided html
        """
        parser = etree.HTMLParser()
        stripped = html.strip()
        tree = etree.fromstring(stripped, parser).getroottree()
        page = tree.getroot()

        # lxml inserts a doctype if none exists, so only include it in
        # the root if it was in the original html.
        root = tree if stripped.startswith(tree.docinfo.doctype) else page

        assert page is not None

        # process style block
        rules = self._process_style_block(page)

        # process external style sheets
        for these_rules, these_leftover, css_body in self.css_source:
            rules.extend(these_rules)
            if these_leftover or self.keep_style_tags:
                style = etree.Element('style')
                style.attrib['type'] = 'text/css'
                if self.keep_style_tags:
                    style.text = css_body
                else:
                    style.text = css_rules_to_string(these_leftover)
                head = CSSSelector('head')(page)
                if head:
                    head[0].append(style)

        # rules is a tuple of (specificity, selector, styles), where specificity is a tuple
        # ordered such that more specific rules sort larger.
        rules.sort(key=operator.itemgetter(0))

        first_time = []
        first_time_styles = []
        for __, selector, style in rules:
            new_selector = selector
            class_ = ''
            if ':' in selector:
                new_selector, class_ = re.split(':', selector, 1)
                class_ = ':%s' % class_
            # Keep filter-type selectors untouched.
            if class_ in FILTER_PSEUDOSELECTORS:
                class_ = ''
            else:
                selector = new_selector

            sel = CSSSelector(selector)
            for item in sel(page):
                old_style = item.attrib.get('style', '')
                if item in first_time:
                    new_style = merge_styles(old_style, style, class_)
                    first_time.append(item)
                    first_time_styles.append((item, old_style))
                else:
                    new_style = merge_styles(old_style, style, class_)
                item.attrib['style'] = new_style
                style_to_basic_html_attributes(item, new_style, self.disable_basic_attributes)

        # remove classes if required
        self._remove_css_classes(page)

        # transform relative paths to absolute URLs if required
        self._transform_urls(page)
        kwargs.setdefault('method', 'html')
        kwargs.setdefault('pretty_print', pretty_print)
        kwargs.setdefault('encoding', 'utf-8')  # As Ken Thompson intended
        return etree.tostring(root, **kwargs).decode(kwargs['encoding'])

    def _process_style_block(self, page):
        index = 0
        rules = []
        for element in CSSSelector('style,link[rel~=stylesheet]')(page):
            # If we have a media attribute whose value is anything other than
            # 'screen', ignore the ruleset.
            media = element.attrib.get('media')
            if media and media != 'screen':
                continue

            is_style = element.tag == 'style'
            if is_style:
                css_body = element.text
            else:
                # we don't load any css files at this point
                continue

            these_rules, these_leftover = self.parse_style_rules(css_body, index)
            index += 1
            rules.extend(these_rules)

            parent_of_element = element.getparent()
            if these_leftover or self.keep_style_tags:
                if is_style:
                    style = element
                else:
                    style = etree.Element('style')
                    style.attrib['type'] = 'text/css'
                if self.keep_style_tags:
                    style.text = css_body
                else:
                    style.text = css_rules_to_string(these_leftover)

                if not is_style:
                    element.addprevious(style)
                    parent_of_element.remove(element)

            elif not self.keep_style_tags or not is_style:
                parent_of_element.remove(element)
        return rules

    def _remove_css_classes(self, page):
        if self.remove_classes:
            for item in page.xpath('//@class'):
                parent = item.getparent()
                del parent.attrib['class']
        return page

    def _transform_urls(self, page):
        if self.base_url:
            for attr in ('href', 'src'):
                for item in page.xpath("//@%s" % attr):
                    parent = item.getparent()
                    if (attr == 'href' and self.preserve_internal_links
                            and parent.attrib[attr].startswith('#')):
                        continue
                    if (attr == 'src' and self.preserve_inline_attachments
                            and parent.attrib[attr].startswith('cid:')):
                        continue
                    if not self.base_url.endswith('/'):
                        self.base_url += '/'
                    parent.attrib[attr] = urljoin(self.base_url, parent.attrib[attr].lstrip('/'))
        return page


CSS_HTML_ATTRIBUTE_MAPPING = {
    'text-align': ('align', lambda value: value.strip()),
    'vertical-align': ('valign', lambda value: value.strip()),
    'background-color': ('bgcolor', lambda value: value.strip()),
    'width': ('width', lambda value: value.strip().replace('px', '')),
    'height': ('height', lambda value: value.strip().replace('px', ''))
}


def style_to_basic_html_attributes(element, style_content, disable_basic_attributes):
    """Given an element and styles like 'background-color:red; font-family:Arial' turn some of
    that into HTML attributes

    Note, the style_content can contain pseudoclasses like:
    '{color:red; border:1px solid green} :visited{border:1px solid green}'
    """
    if style_content.count('}') and style_content.count('{') == style_content.count('{'):
        style_content = style_content.split('}')[0][1:]
    attributes = OrderedDict()
    for key, value in [
        x.split(':')
        for x in style_content.split(';') if len(x.split(':')) == 2
    ]:
        try:
            new_key, new_value = CSS_HTML_ATTRIBUTE_MAPPING.get(key.strip(), None)
        except TypeError:
            continue
        else:
            attributes[new_key] = new_value(value)
    for key, value in attributes.items():
        if key in disable_basic_attributes:
            # already set, don't dare to overwrite
            continue
        element.attrib[key] = value


def css_rules_to_string(rules):
    """Given a list of css rules returns a css string
    """
    lines = []
    for item in rules:
        if isinstance(item, tuple):
            k, v = item
            lines.append('%s {%s}' % (k, make_important(v)))
        # media rule
        else:
            for rule in item.cssRules:
                if isinstance(rule, cssutils.css.csscomment.CSSComment):
                    continue
                for key in rule.style.keys():
                    rule.style[key] = (rule.style.getPropertyValue(key, False), '!important')
            lines.append(item.cssText)
    return '\n'.join(lines)
