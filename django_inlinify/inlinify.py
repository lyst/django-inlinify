from __future__ import absolute_import, unicode_literals
import operator
import sys
if sys.version_info >= (3, ):  # pragma: no cover
    # As in, Python 3
    from urllib.parse import urljoin
    STR_TYPE = str
else:  # Python 2
    from urlparse import urljoin
    STR_TYPE = basestring

from lxml import etree
from lxml.cssselect import CSSSelector
from django_inlinify.css_tools import CSSLoader, CSSParser

__all__ = ['Inlinify']


class Inlinify(object):

    def __init__(self,
                 css_files=None,
                 base_url=None,
                 preserve_internal_links=False,
                 preserve_inline_attachments=True,
                 **kwargs):

        # attributes required by the URL parser
        self.base_url = base_url
        self.preserve_internal_links = preserve_internal_links
        self.preserve_inline_attachments = preserve_inline_attachments

        # initialize parser and loader
        self.css_parser = CSSParser(**kwargs)
        self.css_source = CSSLoader(css_files)

    def transform(self, html, pretty_print=True, **kwargs):
        """Transform CSS into inline styles and inject them in the provided html
        """
        parser = etree.HTMLParser()
        stripped = html.strip()
        tree = etree.fromstring(stripped, parser).getroottree()
        page = tree.getroot()

        # lxml inserts a doctype if none exists, so only include it in the root if it was in
        # the original html
        root = tree if stripped.startswith(tree.docinfo.doctype) else page

        assert page is not None

        # process style block
        rules = self._process_style_block(page)

        # process external style sheets
        rules.extend(self._process_external_files(page))

        # rules is a tuple of (specificity, selector, styles), where specificity is a tuple
        # ordered such that more specific rules sort larger.
        rules.sort(key=operator.itemgetter(0))

        original_styles = {}
        for __, selector, new_style in rules:
            sel = CSSSelector(selector)
            for item in sel(page):
                current_style = item.attrib.get('style', '')
                if item not in original_styles:
                    original_styles[item] = current_style
                self._update_element_style(item, current_style, new_style)

        # re-apply the original inline styles
        self._reapply_original_inline_styles(original_styles)

        # transform relative paths to absolute URLs if required
        self._transform_urls(page)

        # set some default options
        kwargs.setdefault('method', 'html')
        kwargs.setdefault('pretty_print', pretty_print)
        kwargs.setdefault('encoding', 'utf-8')
        return etree.tostring(root, **kwargs).decode(kwargs['encoding'])

    def _process_external_files(self, page):
        """Processes the provided external CSS files, if any
        """
        rules = []
        for index, css_body in enumerate(self.css_source):
            these_rules, these_leftover = self.css_parser.parse(css_body, index)
            rules.extend(these_rules)
            if these_leftover:
                style = etree.Element('style')
                style.attrib['type'] = 'text/css'
                style.text = these_leftover
                head = CSSSelector('head')(page)
                if head:
                    head[0].append(style)
        return rules

    def _process_style_block(self, page):
        """Processes the <style> block in the HTML
        """
        rules = []
        for index, element in enumerate(CSSSelector('style')(page)):
            # If we have a media attribute whose value is anything other than 'screen',
            # ignore the ruleset.
            media = element.attrib.get('media')
            if media and media != 'screen':
                continue

            css_body = element.text
            these_rules, these_leftover = self.css_parser.parse(css_body, index)
            rules.extend(these_rules)

        return rules

    def _reapply_original_inline_styles(self, original):
        """Re-applies all the initial inline styles
        """
        for item, inline_style in original.iteritems():
            if not inline_style:
                continue
            self._update_element_style(item, item.attrib.get('style', ''), inline_style)

    def _update_element_style(self, element, current, new):
        """Given an element, its current style and a new one, merges them and updates the element
        """
        new_style = self.css_parser.merge_styles(current, new)
        element.attrib['style'] = new_style
        self.css_parser.css_style_to_basic_html_attributes(element, new_style)

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
