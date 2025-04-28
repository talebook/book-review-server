#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import base64
import json
import os
import sys
import shutil
import time
import unittest
import urllib
from unittest import mock
from tornado import testing, web

testdir = os.path.dirname(os.path.realpath(__file__))
projdir = os.path.realpath(testdir + "/../")
print(projdir)
sys.path.append(projdir)

import handlers
import main, models  # nosq: E402
from handlers.base import BaseHandler

_app = None
_mock_user = None
_mock_mail = None
_mock_service_async_mode = None

'''
1	EPUB	440912	Bai Nian Gu Du - Jia Xi Ya  Ma Er Ke Si
2	TXT	298421	Man Man Zi You Lu - Unknown
3	MOBI	2662851	An Tu Sheng Tong Hua - An Tu Sheng
4	AZW3	344989	Mai Ken Xi Fang Fa (Jing Guan Tu Shu De Ch - Ai Sen _La Sai Er (Ethan M.Rasiel)
5	PDF	6127496	E Yu Pa Pa Ya Yi Pa Pa - Unknown
6	EPUB	324726	Tang Shi San Bai Shou - Wei Zhi
'''
BID_EPUB = 1
BID_TXT = 2
BID_MOBI = 3
BID_AZW3 = 4
BID_PDF = 5
BIDS = list(range(1, 6))


def setup_server():
    global _app
    # copy new db
    shutil.copyfile(testdir + "/candle-reader-unittest.db", testdir + "/.unittest.db")

    # set env
    main.CONF["ALLOW_GUEST_PUSH"] = False
    main.CONF["ALLOW_GUEST_DOWNLOAD"] = False
    main.CONF["upload_path"] = "/tmp/"
    main.CONF["settings_path"] = "/tmp/"
    main.CONF["progress_path"] = "/tmp/"
    main.CONF["installed"] = True
    main.CONF["INVITE_MODE"] = False
    main.CONF["user_database"] = "sqlite:///%s/.unittest.db" % testdir
    # main.CONF["db_engine_args"] = {"echo": True}
    if _app is None:
        _app = main.make_app()


def setup_mock_user():
    global _mock_user
    _mock_user = mock.patch.object(BaseHandler, "user_id", return_value=1)


def setup_mock_sendmail():
    global _mock_mail
    _mock_mail = mock.patch("services.mail.send_by_smtp", return_value="Yo")


def setup_mock_service():
    global _mock_service_async_mode
    _mock_service_async_mode = mock.patch("services.AsyncService.async_mode")


def get_db():
    return _app.settings["ScopedSession"]


def Q(s):
    if not isinstance(s, str):
        s = str(s)
    return urllib.parse.quote(s.encode("UTF-8"))


class FakeHandler(BaseHandler):
    def __init__(h):
        h.request = h
        h.request.headers = {}
        h.request.remote_ip = "1.2.3.4"
        h.rsp_headers = {}
        h.rsp = None
        h.cookie = {}
        h.session = get_db()

    def write(self, rsp):
        self.rsp = rsp

    def finish(self):
        return None

    def set_header(self, k, v):
        self.rsp_headers[k] = v

    def set_secure_cookie(self, k, v):
        self.cookie[k] = v


class TestApp(testing.AsyncHTTPTestCase):
    def get_app(self):
        return _app

    def json(self, url, *args, **kwargs):
        if 'request_timeout' not in kwargs:
            kwargs['request_timeout'] = 60
        rsp = self.fetch(url, *args, **kwargs)
        self.assertEqual(rsp.code, 200)
        return json.loads(rsp.body)

    def gt(self, n, at_least):
        self.assertEqual(n, max(n, at_least))


class TestAppWithoutLogin(TestApp):
    def test_review(self):
        d = self.json("/api/review/book?title=unittest")
        self.assertTrue(d["data"]['id'] >= 0)


class AutoResetPermission:
    def __init__(self, arg):
        if not arg:
            arg = models.Reader.id == 1
        self.arg = arg

    def __enter__(self):
        self.user = get_db().query(models.Reader).filter(self.arg).first()
        self.user.permission = ""
        return self.user

    def __exit__(self, type, value, trace):
        self.user.permission = ""


def mock_permission(arg=None):
    return AutoResetPermission(arg)


class TestWithUserLogin(TestApp):
    @classmethod
    def setUpClass(self):
        self.user = _mock_user.start()
        self.mail = _mock_mail.start()
        self.async_service = _mock_service_async_mode.start()
        self.user.return_value = 1
        self.mail.return_value = True
        self.async_service.return_value = False

    @classmethod
    def tearDownClass(self):
        _mock_user.stop()
        _mock_mail.stop()
        _mock_service_async_mode.start()


class TestUser(TestWithUserLogin):
    def test_userinfo(self):
        d = self.json("/api/user/info")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["data"]["id"], 1)

    def test_login(self):
        email = 'active@email.com'
        password = 'unittest'

        user = get_db().query(models.Reader).filter(models.Reader.email == email).first()
        user.permission = ""
        d = self.json("/api/user/sign_in", method="POST", body=f"email={email}&password={password}")
        self.assertEqual(d["err"], "ok")

        user = get_db().query(models.Reader).filter(models.Reader.email == email).first()
        user.set_permission("L")
        d = self.json("/api/user/sign_in", method="POST", body=f"email={email}&password={password}")
        self.assertEqual(d["err"], "permission")

        user = get_db().query(models.Reader).filter(models.Reader.email == email).first()
        user.set_permission("l")
        d = self.json("/api/user/sign_in", method="POST", body=f"email={email}&password={password}")
        self.assertEqual(d["err"], "ok")


class TestUserSignUp(TestWithUserLogin):
    @classmethod
    def setUpClass(self):
        self.user = _mock_user.start()
        self.user.return_value = 1
        self.mail = _mock_mail.start()
        self.mail.return_value = True
        self.async_service = _mock_service_async_mode.start()
        self.async_service.return_value = False

    @classmethod
    def tearDownClass(self):
        self.delete_user()
        _mock_mail.stop()

    @classmethod
    def get_user(self):
        return get_db().query(models.Reader).filter(models.Reader.email == "unittest@email.com")

    @classmethod
    def delete_user(self):
        self.get_user().delete()
        get_db().commit()

    def test_signup(self):
        self.delete_user()
        self.mail.reset_mock()

        d = self.json("/api/user/sign_up", method="POST", raise_error=True, body="")
        self.assertEqual(d["err"], "params.invalid")

        body = "email=unittest@email.com&nickname=unittest"
        d = self.json("/api/user/sign_up", method="POST", raise_error=True, body=body)
        self.assertEqual(d["err"], "ok")
        self.assertEqual(self.mail.call_count, 1)

        user = self.get_user().first()
        self.assertEqual(user.email, "unittest@email.com")
        self.assertEqual(user.nickname, "unittest")
        self.assertEqual(user.is_active, True)

        # 设置密码为 unittest
        user.set_secure_password('unittest')
        get_db().commit()

        # build fake auth header unittest:unittest
        f = FakeHandler()
        f.request.headers["Authorization"] = "xxxxx"
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        f.request.headers["Authorization"] = self.auth("username:password")
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        f.request.headers["Authorization"] = self.auth("unittest:password")
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        ts = int(time.time())
        f.request.headers["Authorization"] = self.auth("unittest@email.com:unittest")
        self.assertEqual(True, BaseHandler.process_auth_header(f))
        self.assertTrue(int(f.cookie["lt"]) >= ts)
        self.assertTrue(int(f.cookie["lt"]) >= ts)

        self.delete_user()

    def auth(self, s):
        return "Basic " + base64.encodebytes(s.encode("ascii")).decode("ascii")


class TestJsonResponse(TestApp):
    def raise_(self, err):
        raise err

    def assertHeaders(self, headers):
        self.assertEqual(
            headers,
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
                "Cache-Control": "max-age=0",
            },
        )

    def test_err(self):
        f = FakeHandler()
        with mock.patch("traceback.format_exc", return_value=""):
            handlers.base.js(lambda x: self.raise_(RuntimeError()))(f)
        self.assertTrue(isinstance(f.rsp["msg"], str))
        self.assertEqual(f.rsp["err"], "exception")
        self.assertHeaders(f.rsp_headers)

    def test_finish(self):
        f = FakeHandler()
        with mock.patch("traceback.format_exc", return_value=""):
            handlers.base.js(lambda x: self.raise_(web.Finish()))(f)
        self.assertEqual(f.rsp, "")
        self.assertHeaders(f.rsp_headers)


def setUpModule():
    os.environ["ASYNC_TEST_TIMEOUT"] = "60"
    setup_server()
    setup_mock_user()
    setup_mock_sendmail()
    setup_mock_service()


if __name__ == "__main__":
    '''
    logging.basicConfig(
        level=logging.DEBUG,
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="/data/log/unittest.log",
        format="%(asctime)s %(levelname)7s %(pathname)s:%(lineno)d %(message)s",
    )'''
    unittest.main()
