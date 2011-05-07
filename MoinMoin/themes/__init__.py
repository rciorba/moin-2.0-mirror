# Copyright: 2003-2010 MoinMoin:ThomasWaldmann
# Copyright: 2008 MoinMoin:RadomirDopieralski
# Copyright: 2010 MoinMoin:DiogenesAugusto
# License: GNU GPL v2 (or any later version), see LICENSE.txt for details.

"""
    MoinMoin - Theme Support
"""


import urllib

from flask import current_app as app
from flask import g as flaskg
from flask import url_for, request
from flaskext.themes import get_theme, render_theme_template

from MoinMoin import log
logging = log.getLogger(__name__)

from MoinMoin.i18n import _, L_, N_
from MoinMoin import wikiutil, user
from MoinMoin.config import USERID, ADDRESS, HOSTNAME
from MoinMoin.util.interwiki import split_interwiki, resolve_interwiki, join_wiki, getInterwikiHome
from MoinMoin.util.crypto import cache_key


def get_current_theme():
    # this might be called at a time when flaskg.user is not setup yet:
    u = getattr(flaskg, 'user', None)
    if u and u.theme_name is not None:
        theme_name = u.theme_name
    else:
        theme_name = app.cfg.theme_default
    try:
        return get_theme(theme_name)
    except KeyError:
        logging.warning("theme %s was not found; using default of %s instead." % (theme_name, app.cfg.theme_default))
        theme_name = app.cfg.theme_default
        return get_theme(theme_name)



def render_template(template, **context):
    flaskg.clock.start('render_template')
    output = render_theme_template(get_current_theme(), template, **context)
    flaskg.clock.stop('render_template')
    return output

def themed_error(e):
    item_name = request.view_args.get('item_name', u'')
    if e.code == 403:
        title = L_('Access denied')
        description = L_('You are not allowed to access this resource.')
    else:
        # if we have no special code, we just return the HTTPException instance
        return e
    content = render_template('error.html',
                              item_name=item_name,
                              title=title, description=description)
    return content, e.code


class ThemeSupport(object):
    """
    Support code for template feeding.
    """
    def __init__(self, cfg):
        self.cfg = cfg
        self.user = flaskg.user
        self.storage = flaskg.storage
        self.ui_lang = 'en' # XXX
        self.ui_dir = 'ltr' # XXX
        self.content_lang = flaskg.content_lang # XXX
        self.content_dir = 'ltr' # XXX
        self.meta_items = [] # list of (name, content) for html head <meta>

    def location_breadcrumbs(self, item_name):
        """
        Assemble the location using breadcrumbs (was: title)

        :rtype: list
        :returns: location breadcrumbs items in tuple (segment_name, item_name, exists)
        """
        breadcrumbs = []
        current_item = ''
        for segment in item_name.split('/'):
            current_item += segment
            breadcrumbs.append((segment, current_item, self.storage.has_item(current_item)))
            current_item += '/'
        return breadcrumbs

    def path_breadcrumbs(self):
        """
        Assemble the path breadcrumbs (a.k.a.: trail)

        :rtype: list
        :returns: path breadcrumbs items in tuple (wiki_name, item_name, url, exists, err)
        """
        user = self.user
        breadcrumbs = []
        trail = user.getTrail()
        for interwiki_item_name in trail:
            wiki_name, item_name = split_interwiki(interwiki_item_name)
            wiki_name, wiki_base_url, item_name, err = resolve_interwiki(wiki_name, item_name)
            href = join_wiki(wiki_base_url, item_name)
            if wiki_name in [self.cfg.interwikiname, 'Self', ]:
                exists = self.storage.has_item(item_name)
                wiki_name = ''  # means "this wiki" for the theme code
            else:
                exists = True  # we can't detect existance of remote items
            breadcrumbs.append((wiki_name, item_name, href, exists, err))
        return breadcrumbs

    def userhome(self):
        """
        Assemble arguments used to build user homepage link

        :rtype: tuple
        :returns: arguments of user homepage link in tuple (wiki_href, aliasname, title, exists)
        """
        user = self.user
        name = user.name
        aliasname = user.aliasname
        if not aliasname:
            aliasname = name

        wikiname, itemname = getInterwikiHome(name)
        title = "%s @ %s" % (aliasname, wikiname)
        # link to (interwiki) user homepage
        if wikiname == "Self":
            exists = self.storage.has_item(itemname)
        else:
            # We cannot check if wiki pages exists in remote wikis
            exists = True
        wiki_name, wiki_base_url, item_name, err = resolve_interwiki(wikiname, itemname)
        wiki_href = join_wiki(wiki_base_url, item_name)
        return wiki_href, aliasname, title, exists

    def split_navilink(self, text):
        """
        Split navibar links into pagename, link to page

        Admin or user might want to use shorter navibar items by using
        the [[page|title]] or [[url|title]] syntax.

        Supported syntax:
            * PageName
            * WikiName:PageName
            * wiki:WikiName:PageName
            * url
            * all targets as seen above with title: [[target|title]]

        :param text: the text used in config or user preferences
        :rtype: tuple
        :returns: pagename or url, link to page or url
        """
        title = None
        wiki_local = ''  # means local wiki

        # Handle [[pagename|title]] or [[url|title]] formats
        if text.startswith('[[') and text.endswith(']]'):
            text = text[2:-2]
            try:
                target, title = text.split('|', 1)
                target = target.strip()
                title = title.strip()
            except (ValueError, TypeError):
                # Just use the text as is.
                target = text.strip()
        else:
            target = text

        if wikiutil.is_URL(target):
            if not title:
                title = target
            return target, title, wiki_local

        # remove wiki: url prefix
        if target.startswith("wiki:"):
            target = target[5:]

        # try handling interwiki links
        wiki_name, item_name = split_interwiki(target)
        wiki_name, wiki_base_url, item_name, err = resolve_interwiki(wiki_name, item_name)
        href = join_wiki(wiki_base_url, item_name)
        if wiki_name not in [self.cfg.interwikiname, 'Self', ]:
            if not title:
                title = item_name
            return href, title, wiki_name

        # Handle regular pagename like "FrontPage"
        item_name = wikiutil.normalize_pagename(item_name, self.cfg)

        if not title:
            title = item_name
        href = url_for('frontend.show_item', item_name=item_name)
        return href, title, wiki_local

    def navibar(self, item_name):
        """
        Assemble the navibar

        :rtype: list
        :returns: list of tuples (css_class, url, link_text, title)
        """
        flaskg.clock.start('navibar')
        current = item_name
        # Process config navi_bar
        items = [(cls, url_for(endpoint, **args), link_text, title)
                 for cls, endpoint, args, link_text, title in self.cfg.navi_bar]

        # Add user links to wiki links.
        userlinks = self.user.getQuickLinks()
        for text in userlinks:
            url, link_text, title = self.split_navilink(text)
            items.append(('userlink', url, link_text, title))

        # Add sister pages (see http://usemod.com/cgi-bin/mb.pl?SisterSitesImplementationGuide )
        for sistername, sisterurl in self.cfg.sistersites:
            if sistername == self.cfg.interwikiname:  # it is THIS wiki
                items.append(('sisterwiki current', sisterurl, sistername))
            else:
                cid = cache_key(usage="SisterSites", sistername=sistername)
                sisteritems = app.cache.get(cid)
                if sisteritems is None:
                    uo = urllib.URLopener()
                    uo.version = 'MoinMoin SisterItem list fetcher 1.0'
                    try:
                        sisteritems = {}
                        f = uo.open(sisterurl)
                        for line in f:
                            line = line.strip()
                            try:
                                item_url, item_name = line.split(' ', 1)
                                sisteritems[item_name.decode('utf-8')] = item_url
                            except:
                                pass # ignore invalid lines
                        f.close()
                        app.cache.set(cid, sisteritems)
                        logging.info("Site: %s Status: Updated. Pages: %d" % (sistername, len(sisteritems)))
                    except IOError as err:
                        (title, code, msg, headers) = err.args # code e.g. 304
                        logging.warning("Site: %s Status: Not updated." % sistername)
                        logging.exception("exception was:")
                if current in sisteritems:
                    url = sisteritems[current]
                    items.append(('sisterwiki', url, sistername, ''))
        flaskg.clock.stop('navibar')
        return items

    def parent_item(self, item_name):
        """
        Return name of parent item for the current item

        :rtype: unicode
        :returns: parent item name
        """
        parent_item_name = wikiutil.ParentItemName(item_name)
        if item_name and parent_item_name:
            return parent_item_name

    # TODO: reimplement on-wiki-page sidebar definition with MoinMoin.converter

    # Properties ##############################################################

    def login_url(self):
        """
        Return URL usable for user login

        :rtype: unicode (or None, if no login url is supported)
        :returns: url for user login
        """
        url = None
        if self.cfg.auth_login_inputs == ['special_no_input']:
            url = url_for('frontend.login', login=1)
        if self.cfg.auth_have_login:
            url = url or url_for('frontend.login')
        return url


def get_editor_info(rev, external=False):
    addr = rev.get(ADDRESS)
    hostname = rev.get(HOSTNAME)
    text = _('anonymous')  # link text
    title = ''  # link title
    css = 'editor'  # link/span css class
    name = None  # author name
    uri = None  # author homepage uri
    email = None  # pure email address of author
    if app.cfg.show_hosts and addr:
        # only tell ip / hostname if show_hosts is True
        if hostname:
            text = hostname[:15]  # 15 = len(ipaddr)
            name = title = '%s[%s]' % (hostname, addr)
            css = 'editor host'
        else:
            name = text = addr
            title = '[%s]' % (addr, )
            css = 'editor ip'

    userid = rev.get(USERID)
    if userid:
        u = user.User(userid)
        name = u.name
        text = name
        aliasname = u.aliasname
        if not aliasname:
            aliasname = name
        if title:
            # we already have some address info
            title = "%s @ %s" % (aliasname, title)
        else:
            title = aliasname
        if u.mailto_author and u.email:
            email = u.email
            css = 'editor mail'
        else:
            homewiki = app.cfg.user_homewiki
            if homewiki in ('Self', app.cfg.interwikiname):
                homewiki = u'Self'
                css = 'editor homepage local'
                uri = url_for('frontend.show_item', item_name=name, _external=external)
            else:
                css = 'editor homepage interwiki'
                wt, wu, tail, err = resolve_interwiki(homewiki, name)
                uri = join_wiki(wu, tail)

    result = dict(name=name, text=text, css=css, title=title)
    if uri:
        result['uri'] = uri
    if email:
        result['email'] = email
    return result


def shorten_item_name(name, length=25):
    """
    Shorten item names

    Shorten very long item names that tend to break the user
    interface. The short name is usually fine, unless really stupid
    long names are used (WYGIWYD).

    :param name: item name, unicode
    :param length: maximum length for shortened item names, int
    :rtype: unicode
    :returns: shortened version.
    """
    # First use only the sub page name, that might be enough
    if len(name) > length:
        name = name.split('/')[-1]
        # If it's not enough, replace the middle with '...'
        if len(name) > length:
            half, left = divmod(length - 3, 2)
            name = u'%s...%s' % (name[:half + left], name[-half:])
    return name


MIMETYPE_TO_CLASS = {
    'application/pdf': 'pdf',
}

def contenttype_to_class(contenttype):
    """
    Convert a contenttype string to a css class.
    """
    cls = MIMETYPE_TO_CLASS.get(contenttype)
    if not cls:
        # just use the major part of mimetype
        cls = contenttype.split('/', 1)[0]
    return 'moin-mime-%s' % cls


def setup_jinja_env():
    app.jinja_env.filters['shorten_item_name'] = shorten_item_name
    app.jinja_env.filters['contenttype_to_class'] = contenttype_to_class
    # please note that these filters are installed by flask-babel:
    # datetimeformat, dateformat, timeformat, timedeltaformat

    app.jinja_env.globals.update({
                            # please note that flask-babel/jinja2.ext installs:
                            # _, gettext, ngettext
                            'isinstance': isinstance,
                            'list': list,
                            # please note that flask-themes installs:
                            # theme, theme_static
                            'theme_supp': ThemeSupport(app.cfg),
                            'user': flaskg.user,
                            'storage': flaskg.storage,
                            'clock': flaskg.clock,
                            'cfg': app.cfg,
                            'item_name': 'handlers need to give it',
                            'get_editor_info': lambda rev: get_editor_info(rev),
                            })

