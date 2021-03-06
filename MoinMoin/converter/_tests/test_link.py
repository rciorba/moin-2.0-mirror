# Copyright: 2007 MoinMoin:BastianBlank
# License: GNU GPL v2 (or any later version), see LICENSE.txt for details.

"""
MoinMoin - Tests for MoinMoin.converter.link
"""


import pytest

from emeraldtree import tree as ET

from flask import current_app as app

from MoinMoin.converter.link import *
from MoinMoin.util.iri import Iri


class TestConverterExternOutput(object):
    def setup_class(self):
        self.conv = ConverterExternOutput()

    def test_wiki(self):
        assert 'MoinMoin' in app.cfg.interwiki_map
        pairs = [
            # note: result URLs assume test wiki running at /
            ('wiki:///Test',
                '/Test'),
            ('wiki:///Test?mode=raw',
                '/Test?mode=raw'),
            ('wiki:///Test#anchor',
                '/Test#anchor'),
            ('wiki:///Test?mode=raw#anchor',
                '/Test?mode=raw#anchor'),
            ('wiki://MoinMoin/Test',
                'http://moinmo.in/Test'),
        ]
        for i in pairs:
            yield (self._do_wiki, ) + i

    def test_wikilocal(self):
        pairs = [
            # note: result URLs assume test wiki running at /
            ('wiki.local:',
                'wiki:///Root',
                '/Root'),
            ('wiki.local:Test',
                'wiki:///Root',
                '/Test'),
            ('wiki.local:Test',
                'wiki:///Root/Sub',
                '/Test'),
            ('wiki.local:/Test',
                'wiki:///Root',
                '/Root/Test'),
            ('wiki.local:/Test',
                'wiki:///Root/Sub',
                '/Root/Sub/Test'),
            ('wiki.local:../Test',
                'wiki:///Root',
                '/Test'),
            ('wiki.local:../Test',
                'wiki:///Root/Sub',
                '/Root/Test'),
        ]
        for i in pairs:
            yield (self._do_wikilocal, ) + i

    def test_wikiexternal(self):
        pairs = [
            ('http://moinmo.in/',
             'http://moinmo.in/'),
            ('mailto:foo.bar@example.org',
             'mailto:foo.bar@example.org'),
        ]
        for i in pairs:
            yield (self._do_wikiexternal, ) + i

    def _do_wiki(self, input, output, skip=None):
        if skip:
            pytest.skip(skip)
        elem = ET.Element(None)
        self.conv.handle_wiki_links(elem, Iri(input))
        assert elem.get(xlink.href) == output

    def _do_wikilocal(self, input, page, output, skip=None):
        if skip:
            pytest.skip(skip)
        elem = ET.Element(None)
        self.conv.handle_wikilocal_links(elem, Iri(input), Iri(page))
        assert elem.get(xlink.href) == output

    def _do_wikiexternal(self, input, output, skip=None):
        if skip:
            pytest.skip(skip)
        elem = ET.Element(None)
        self.conv.handle_external_links(elem, Iri(input))
        href = elem.get(xlink.href)
        assert href == output


class TestConverterRefs(object):
    def setup_class(self):
        self.converter = ConverterItemRefs()

    def testItems(self):
        tree_xml = u"""
        <ns0:page ns0:page-href="wiki:///Home" xmlns:ns0="http://moinmo.in/namespaces/page" xmlns:ns1="http://www.w3.org/2001/XInclude" xmlns:ns2="http://www.w3.org/1999/xlink">
        <ns0:body><ns0:p><ns1:include ns1:href="wiki.local:moin_transcluded?" />
        <ns1:include ns1:href="wiki.local:moin2_transcluded?" />
        <ns0:a ns2:href="wiki.local:moin_linked">moin_linked</ns0:a>
        <ns0:a ns2:href="wiki.local:moin2_linked">moin2_linked</ns0:a></ns0:p>
        <ns0:p>safas\nafsfasfas\nfas\nfassaf</ns0:p>
        <ns0:p><ns1:include ns1:href="wiki.local:moin_transcluded?" />
        <ns1:include ns1:href="wiki.local:moin2_transcluded?" />
        <ns0:a ns2:href="wiki.local:moin_linked">moin_linked</ns0:a>
        <ns0:a ns2:href="wiki.local:moin2_linked">moin2_linked</ns0:a></ns0:p></ns0:body></ns0:page>
        """
        transclusions_expected = [u"moin_transcluded", u"moin2_transcluded"]
        links_expected = [u"moin_linked", u"moin2_linked"]
        external_expected = []

        self.runItemTest(tree_xml, links_expected, transclusions_expected, external_expected)

    def testRelativeItems(self):
        tree_xml = u"""
        <ns0:page ns0:page-href="wiki:///Home/Subpage" xmlns:ns0="http://moinmo.in/namespaces/page" xmlns:ns1="http://www.w3.org/1999/xlink" xmlns:ns2="http://www.w3.org/2001/XInclude">
        <ns0:body><ns0:p><ns0:a ns1:href="wiki.local:../../moin_linked">../../moin_linked</ns0:a>
        <ns0:a ns1:href="wiki.local:/moin2_linked">/moin2_linked</ns0:a>
        <ns2:include ns2:href="wiki.local:../../moin_transcluded?" />
        <ns2:include ns2:href="wiki.local:/moin2_transcluded?" /></ns0:p></ns0:body></ns0:page>
        """
        transclusions_expected = [u"Home/Subpage/moin2_transcluded", u"moin_transcluded"]
        links_expected = [u"moin_linked", u"Home/Subpage/moin2_linked"]
        external_expected = []

        self.runItemTest(tree_xml, links_expected, transclusions_expected, external_expected)

    def testExternal(self):
        tree_xml = u"""
        <ns0:page ns0:page-href="wiki:///Home/Subpage" xmlns:ns0="http://moinmo.in/namespaces/page" xmlns:ns1="http://www.w3.org/1999/xlink" xmlns:ns2="http://www.w3.org/2001/XInclude">
        <ns0:body><ns0:p><ns0:a ns1:href="http://example.org/">test</ns0:a>
        <ns0:a ns1:href="mailto:foo.bar@example.org">test</ns0:a>
        </ns0:p></ns0:body></ns0:page>
        """
        transclusions_expected = []
        links_expected = []
        external_expected = [u"http://example.org/", u"mailto:foo.bar@example.org"]

        self.runItemTest(tree_xml, links_expected, transclusions_expected, external_expected)

    def runItemTest(self, tree_xml, links_expected, transclusions_expected, external_expected):
        tree = ET.XML(tree_xml)
        self.converter(tree)
        links_result = self.converter.get_links()
        transclusions_result = self.converter.get_transclusions()
        external_result = self.converter.get_external_links()

        # sorting instead of sets
        # so that we avoid deduplicating duplicated items in the result
        assert sorted(links_result) == sorted(links_expected)
        assert sorted(transclusions_result) == sorted(transclusions_expected)
        assert sorted(external_result) == sorted(external_expected)
