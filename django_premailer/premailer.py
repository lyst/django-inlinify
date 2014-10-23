from __future__ import absolute_import, unicode_literals
from collections import OrderedDict
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
from django_premailer.css_tools import CSSLoader, CSSParser

__all__ = ['Premailer']


class Premailer(object):

    def __init__(self,
                 css_files=None,
                 base_url=None,
                 preserve_internal_links=False,
                 preserve_inline_attachments=True,
                 keep_style_tags=False,
                 remove_classes=True,
                 base_path=None,
                 disable_basic_attributes=None,
                 **kwargs):
        self.base_url = base_url
        self.preserve_internal_links = preserve_internal_links
        self.preserve_inline_attachments = preserve_inline_attachments
        # whether to delete the <style> tag once it's been processed
        # this will always preserve the original css
        self.keep_style_tags = keep_style_tags
        self.remove_classes = remove_classes

        self.css_parser = CSSParser(**kwargs)
        self.css_source = CSSLoader(css_files)

        self.base_path = base_path
        if disable_basic_attributes is None:
            disable_basic_attributes = []
        self.disable_basic_attributes = disable_basic_attributes

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
        rules.extend(self._process_external_files(page))

        # rules is a tuple of (specificity, selector, styles), where specificity is a tuple
        # ordered such that more specific rules sort larger.
        rules.sort(key=operator.itemgetter(0))

        for __, selector, style in rules:
            sel = CSSSelector(selector)
            for item in sel(page):
                merged = self.css_parser.merge_styles(item.attrib.get('style', ''), style)
                item.attrib['style'] = merged
                style_to_basic_html_attributes(item, merged, self.disable_basic_attributes)

        # remove classes if required
        self._remove_css_classes(page)

        # transform relative paths to absolute URLs if required
        self._transform_urls(page)
        kwargs.setdefault('method', 'html')
        kwargs.setdefault('pretty_print', pretty_print)
        kwargs.setdefault('encoding', 'utf-8')  # As Ken Thompson intended
        return etree.tostring(root, **kwargs).decode(kwargs['encoding'])

    def _process_external_files(self, page):
        """Processes the provided external CSS files, if any
        """
        rules = []
        for index, css_body in enumerate(self.css_source):
            these_rules, these_leftover = self.css_parser.parse(css_body, index)
            rules.extend(these_rules)
            if these_leftover or self.keep_style_tags:
                style = etree.Element('style')
                style.attrib['type'] = 'text/css'
                if self.keep_style_tags:
                    style.text = css_body
                else:
                    style.text = these_leftover
                head = CSSSelector('head')(page)
                if head:
                    head[0].append(style)
        return rules

    def _process_style_block(self, page):
        """Processes the <style> block in the HTML
        """
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

            these_rules, these_leftover = self.css_parser.parse(css_body, index)
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
                    style.text = these_leftover

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
