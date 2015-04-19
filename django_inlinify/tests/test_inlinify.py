from __future__ import absolute_import, unicode_literals

from contextlib import contextmanager
import os
from os.path import dirname, abspath
from os.path import join as joinpath
import re
import unittest

from django_inlinify.inlinify import Inlinify
from django_inlinify.css_tools import CSSParser

whitespace_between_tags = re.compile('>\s*<')


def compare_html(one, two):
    one = one.strip()
    two = two.strip()
    one = whitespace_between_tags.sub('>\n<', one)
    two = whitespace_between_tags.sub('>\n<', two)
    one = one.replace('><', '>\n<')
    two = two.replace('><', '>\n<')
    for i, line in enumerate(one.splitlines()):
        other = two.splitlines()[i]
        if line.lstrip() != other.lstrip():
            assert line.lstrip() == other.lstrip()

ROOT = abspath(joinpath(dirname(__file__)))


def html_path(filename):
    return os.path.join(ROOT, 'html', filename)


def css_path(filename):
    return os.path.join(ROOT, 'css', filename)


@contextmanager
def read_html_file(filename):
    file = open(html_path(filename))
    yield file.read()
    file.close()


@contextmanager
def read_css_file(filename):
    file = open(css_path(filename))
    yield file.read()
    file.close()


class Tests(unittest.TestCase):

    def test_merge_styles_basic(self):
        """
        merge_styles should be able to merge basic CSS.
        """
        old = 'font-size:1px; color: red'
        new = 'font-size:2px; font-weight: bold'
        expect = 'color:red;', 'font-size:2px;', 'font-weight:bold'
        parser = CSSParser()
        result = parser.merge_styles(old, new)
        for each in expect:
            assert each in result

    def test_merge_styles_non_trivial(self):
        """
        merge_styles should be able to merge non-trivial CSS
        """
        old = 'background-image:url("data:image/png;base64,iVBORw0KGg")'
        new = 'font-size:2px; font-weight: bold'
        expect = (
            'background-image:url("data:image/png;base64,iVBORw0KGg")',
            'font-size:2px;',
            'font-weight:bold'
        )
        parser = CSSParser()
        result = parser.merge_styles(old, new)
        for each in expect:
            assert each in result

    def test_basic_html(self):
        """
        CSS defined in the <head> should be in-lined where possible.
        """

        with read_html_file('test_basic_html_input.html') as html:
            with read_html_file('test_basic_html_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_empty_style_tag(self):
        """
        An empty <style> tag in the <head> should be ignored.
        """

        with read_html_file('test_empty_style_tag_input.html') as html:
            with read_html_file('test_empty_style_tag_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_include_star_selector(self):
        """
        '*' selectors should work if the include_star_selectors option is True
        """

        with read_html_file('test_include_star_selector_input.html') as html:
            with read_html_file('test_include_star_selector_expected.html') as expected_output:
                compare_html(html, Inlinify().transform(html))
                compare_html(expected_output, Inlinify(include_star_selectors=True).transform(html))

    def test_pseudo_selectors_are_not_inlined(self):
        """
        Pseudo selectors should not be in-lined.
        """
        with read_html_file('test_pseudo_selectors_are_not_inlined_input.html') as html:
            with read_html_file('test_pseudo_selectors_are_not_inlined_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_parse_style_rules(self):
        """
        CSS should be parsed correctly.
        """
        p = Inlinify()  # won't need the html
        func = p.css_parser.parse

        with read_css_file('test_parse_style_rules.css') as css:
            rules, leftover = func(css, 0)

        # 'rules' is a list, turn it into a dict for
        # easier assertion testing
        rules_dict = {}
        rules_specificity = {}
        for specificity, k, v in rules:
            rules_dict[k] = v
            rules_specificity[k] = specificity

        assert 'h1' in rules_dict
        assert 'h2' in rules_dict
        assert 'strong' in rules_dict
        assert 'ul li' in rules_dict
        assert rules_dict['h1'] == 'color:red'
        assert rules_dict['h2'] == 'color:red'
        assert rules_dict['strong'] == 'text-decoration:none'
        assert rules_dict['ul li'] == 'list-style:2px'
        assert 'a:hover' not in rules_dict
        assert leftover == 'a:hover {text-decoration:underline !important}'

    def test_precedence_comparison(self):
        """
        The correct specificity should be determined for a selector.
        """

        p = Inlinify()

        with read_css_file('test_precedence_comparison.css') as css:
            rules, leftover = p.css_parser.parse(css, 0)

        # 'rules' is a list, turn it into a dict for easier assertion testing
        rules_specificity = {k: specificity for specificity, k, v in rules}

        # Last in file wins
        assert rules_specificity['h1'] < rules_specificity['h2']

        # More elements wins
        assert rules_specificity['strong'] < rules_specificity['ul li']

        # IDs trump everything
        assert rules_specificity['div li.example p.sample'] < rules_specificity['#identified']

        # Classes trump multiple elements
        assert rules_specificity['ul li'] < rules_specificity['.class-one']

        # An element with a class is more specific than just an element
        assert rules_specificity['div'] < rules_specificity['div.with-class']

        # Two classes is better than one
        assert rules_specificity['.class-one'] < rules_specificity['.class-one.class-two']

    def test_base_url_option(self):
        """
        If using the base_url option URL's in the HTML should be updated.
        """

        with read_html_file('test_base_url_option_input.html') as html:
            with read_html_file('test_base_url_option_expected.html') as expected_output:
                p = Inlinify(
                    base_url='http://kungfupeople.com',
                    preserve_internal_links=True
                )
                result_html = p.transform(html)
                compare_html(expected_output, result_html)

    def test_style_block_with_external_urls(self):
        """
        CSS rules with external URL's should be handled correctly.
        """

        with read_html_file('test_style_block_with_external_urls_input.html') as html:
            with read_html_file('test_style_block_with_external_urls_expected.html') as expected_output:
                result_html = Inlinify().transform(html)
                compare_html(expected_output, result_html)

    def test_css_with_html_attributes(self):
        """
        HTML attributes should be applied where appropriate.
        """

        with read_html_file('test_style_block_with_external_urls_input.html') as html:
            with read_html_file('test_style_block_with_external_urls_expected.html') as expected_output:
                result_html = Inlinify().transform(html)
                compare_html(expected_output, result_html)

    def test_mailto_url(self):
        """
        'mailto:' links should not be affected when using the base_url option.
        """

        with read_html_file('test_mailto_url.html') as html:
            p = Inlinify(base_url='http://kungfupeople.com')
            compare_html(html, p.transform(html))

    def test_last_child(self):
        """
        :last-child selector should work correctly.
        """

        with read_html_file('test_last_child_input.html') as html:
            with read_html_file('test_last_child_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_nth_child(self):
        """
        :nth-child selector should work correctly.
        """

        with read_html_file('test_nth_child_input.html') as html:
            with read_html_file('test_nth_child_expected.html') as expected_output:
                compare_html(expected_output,
                             Inlinify(css_files=[css_path('test_nth_child.css')]).transform(html))

    def test_child_selector(self):
        """
        CSS child selectors should work correctly.
        """

        with read_html_file('test_child_selector_input.html') as html:
            with read_html_file('test_child_selector_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_doctype(self):
        """
        If the HTML contains a doctype it should not be removed.
        """
        with read_html_file('test_doctype.html') as html:
            compare_html(html, Inlinify().transform(html))

    def test_multiple_style_elements(self):
        """
        If the HTML has multiple <style> tags they should all be processed.
        """

        with read_html_file('test_multiple_style_elements_input.html') as html:
            with read_html_file('test_multiple_style_elements_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_parsing_from_css_local_file(self):
        """
        CSS from a local file should be correctly handled.
        """

        with read_html_file('test_parsing_from_css_local_file_input.html') as html:
            with read_html_file('test_parsing_from_css_local_file_expected.html') as expected_output:

                p = Inlinify(css_files=[css_path('test_parsing_from_css_local_file.css')])
                result_html = p.transform(html)
                compare_html(expected_output, result_html)

    def test_style_attribute_specificity(self):
        """
        Styles already present in an elements 'style' tag should win over all else.
        """

        with read_html_file('test_style_attribute_specificity_input.html') as html:
            with read_html_file('test_style_attribute_specificity_expected.html') as expected_output:
                compare_html(expected_output, Inlinify().transform(html))

    def test_xml(self):
        """
        Styles already present in an elements 'style' tag should win over all else.
        """
        with read_html_file('test_xml.html') as html:
            with read_html_file('test_xml_expected.html') as expected_output:
                css_style_path = css_path('test_xml.css')
                compare_html(expected_output, Inlinify(method='xml',
                                                       css_files=[css_style_path]).transform(html))

    def test_external_css(self):
        """
        Styles already present in an elements 'style' tag should win over all else.
        """
        with read_html_file('test_external_css_input.html') as html:
            with read_html_file('test_external_css_expected.html') as expected_output:
                css_style_path = css_path('test_external_css.css')
                compare_html(expected_output, Inlinify(css_files=[css_style_path]).transform(html))
