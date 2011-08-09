# Copyright: 2011 Prashant Kumar <contactprashantat AT gmail DOT com>
# License: GNU GPL v2 (or any later version), see LICENSE.txt for details.

"""
Test for auth.__init__
"""

from flask import g as flaskg

from MoinMoin.auth import GivenAuth, handle_login
from MoinMoin.user import create_user
import pytest

class TestGivenAuth(object):
    """ Test: GivenAuth """
    def test_decode_username(self):
        givenauth_obj = GivenAuth()
        result1 = givenauth_obj.decode_username('test_name')
        assert result1 == u'test_name'
        result2 = givenauth_obj.decode_username(123.45)
        assert result2 == 123.45

    def test_transform_username(self):
        givenauth_obj = GivenAuth()
        givenauth_obj.strip_maildomain = True
        givenauth_obj.strip_windomain = True
        givenauth_obj.titlecase = True
        givenauth_obj.remove_blanks = True
        result = givenauth_obj.transform_username(u'testDomain\\test name@moinmoin.org')
        assert result == 'TestName'

    def test_request(self):
        givenauth_obj = GivenAuth()
        flaskg.user.auth_method = 'given'
        givenauth_obj.user_name = u'testDomain\\test_user@moinmoin.org'
        givenauth_obj.strip_maildomain = True
        givenauth_obj.strip_windomain = True
        givenauth_obj.titlecase = True
        givenauth_obj.remove_blanks = True
        create_user('Test_User', 'test_pass', 'test@moinmoin.org')
        test_user, bool_value = givenauth_obj.request(flaskg.user)
        assert test_user.valid
        assert test_user.name == u'Test_User'

def test_handle_login():
    result = handle_login(flaskg.user, login_username = 'test_user', login_password = 'test_password', stage = 'moin')
    test_login_message = [u'Invalid username or password.']
    assert flaskg._login_messages == test_login_message

