#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import base64
import datetime
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
        # 保存原始的raise_error值
        original_raise_error = kwargs.pop('raise_error', False)
        try:
            # 不检查状态码，让测试代码通过err字段判断结果
            rsp = self.fetch(url, *args, **kwargs)
            return json.loads(rsp.body)
        except Exception as e:
            if original_raise_error:
                # 如果原始参数要求抛出异常，则重新抛出
                raise e
            # 否则忽略异常，尝试解析响应体
            if hasattr(e, 'response') and e.response:
                return json.loads(e.response.body)

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
        _mock_service_async_mode.stop()


class TestUser(TestWithUserLogin):
    def test_userinfo(self):
        d = self.json("/api/user/info")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["data"]["id"], 1)

    def test_login(self):
        email = 'active@email.com'
        password = 'unittest'

        user = get_db().query(models.Reader).filter(
            models.Reader.email == email
        ).first()
        user.permission = ""
        # 更新用户密码为bcrypt格式
        user.set_secure_password(password)
        get_db().commit()
        d = self.json(
            "/api/user/sign_in",
            method="POST",
            body=f"email={email}&password={password}"
        )
        self.assertEqual(d["err"], "ok")

        user = get_db().query(models.Reader).filter(models.Reader.email == email).first()
        user.set_permission("L")
        get_db().commit()
        d = self.json(
            "/api/user/sign_in",
            method="POST",
            body=f"email={email}&password={password}"
        )
        self.assertEqual(d["err"], "permission")

        user = get_db().query(models.Reader).filter(models.Reader.email == email).first()
        user.set_permission("l")
        get_db().commit()
        d = self.json("/api/user/sign_in", method="POST", body=f"email={email}&password={password}")
        self.assertEqual(d["err"], "ok")


class TestUserSignUp(TestWithUserLogin):
    @classmethod
    def tearDownClass(self):
        self.delete_user()
        super(TestUserSignUp, self).tearDownClass()

    @classmethod
    def get_user(self):
        return get_db().query(models.Reader).filter(
            models.Reader.email == "unittest@email.com"
        )

    @classmethod
    def delete_user(self):
        self.get_user().delete()
        get_db().commit()

    def test_signup(self):
        self.delete_user()
        self.mail.reset_mock()

        d = self.json(
            "/api/user/sign_up",
            method="POST",
            raise_error=True,
            body=""
        )
        self.assertEqual(d["err"], "params.invalid")

        body = "email=unittest@email.com&nickname=unittest"
        d = self.json(
            "/api/user/sign_up",
            method="POST",
            raise_error=True,
            body=body
        )
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
        f.request.headers["Authorization"] = self.auth(
            "unittest@email.com:unittest"
        )
        self.assertEqual(True, BaseHandler.process_auth_header(f))
        self.assertTrue(int(f.cookie["lt"]) >= ts)
        self.assertTrue(int(f.cookie["lt"]) >= ts)

        self.delete_user()

    def auth(self, s):
        return "Basic " + base64.encodebytes(s.encode("ascii")).decode("ascii")


class TestReviewBookList(TestApp):
    def test_book_list(self):
        # 缺 book_id 参数校验
        d = self.json("/api/review/book/list")
        self.assertEqual(d["err"], "params.invalid")

        # 准备一本书 + 两条评论：old-hot（旧、高赞）、new-cold（新、低赞）
        import datetime
        db = get_db()
        book = models.ReviewBook(title="booklist-ut", alias="booklist-ut")
        db.add(book)
        db.flush()
        now = datetime.datetime.now()
        r1 = models.Review(
            book_id=book.id, chapter_id=0, segment_id=0, type=models.ReviewType.text,
            content="old-hot", like_count=100, user_id=1,
            create_time=now - datetime.timedelta(hours=2), update_time=now - datetime.timedelta(hours=2),
        )
        r2 = models.Review(
            book_id=book.id, chapter_id=0, segment_id=0, type=models.ReviewType.text,
            content="new-cold", like_count=1, user_id=1, create_time=now, update_time=now,
        )
        db.add_all([r1, r2])
        db.commit()

        try:
            # 最新：new-cold 在前
            d = self.json(f"/api/review/book/list?book_id={book.id}&sort=latest")
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["data"]["total"], 2)
            self.assertEqual(d["data"]["list"][0]["content"], "new-cold")
            self.assertEqual(d["data"]["list"][0]["likeCount"], 1)

            # 热门：old-hot 在前
            d = self.json(f"/api/review/book/list?book_id={book.id}&sort=hot")
            self.assertEqual(d["data"]["list"][0]["content"], "old-hot")
            self.assertEqual(d["data"]["list"][0]["likeCount"], 100)

            # 分页：size=1 只返回一条，total 仍为 2
            d = self.json(f"/api/review/book/list?book_id={book.id}&sort=latest&size=1")
            self.assertEqual(len(d["data"]["list"]), 1)
            self.assertEqual(d["data"]["total"], 2)
        finally:
            db.query(models.Review).filter(models.Review.book_id == book.id).delete()
            db.query(models.ReviewBook).filter(models.ReviewBook.id == book.id).delete()
            db.commit()


class TestReviewCommentExport(TestApp):
    def setUp(self):
        super().setUp()
        self.old_token = main.CONF.get("plugin_export_token", "")
        main.CONF["plugin_export_token"] = "export-test-token"
        db = get_db()
        now = datetime.datetime(2026, 8, 17, 12, 0, 0)
        self.rows = [
            models.Review(
                book_id=91001, chapter_id=92001, segment_id=index,
                type=review_type, content=content, user_id=1,
                create_time=now, update_time=now,
            )
            for index, review_type, content in (
                (1, models.ReviewType.text, "first export comment"),
                (2, models.ReviewType.like, "not exported"),
                (3, models.ReviewType.text, "second export comment"),
            )
        ]
        db.add_all(self.rows)
        db.commit()
        self.row_ids = [row.id for row in self.rows]

    def tearDown(self):
        db = get_db()
        db.query(models.Review).filter(models.Review.id.in_(self.row_ids)).delete(synchronize_session=False)
        db.commit()
        main.CONF["plugin_export_token"] = self.old_token
        super().tearDown()

    @staticmethod
    def auth_headers(token="export-test-token"):
        return {"Authorization": "Bearer " + token}

    def test_requires_configured_bearer_token(self):
        rsp = self.fetch("/api/v1/comments")
        self.assertEqual(rsp.code, 401)
        self.assertEqual(json.loads(rsp.body)["err"], "auth.invalid")

        rsp = self.fetch("/api/v1/comments", headers=self.auth_headers("wrong"))
        self.assertEqual(rsp.code, 401)

        main.CONF["plugin_export_token"] = ""
        rsp = self.fetch("/api/v1/comments", headers=self.auth_headers())
        self.assertEqual(rsp.code, 401)

    def test_exports_only_text_comments_with_cursor_pagination(self):
        cursor = self.row_ids[0] - 1
        first = self.json(
            "/api/v1/comments?cursor=%s&limit=1" % cursor,
            headers=self.auth_headers(),
        )
        self.assertEqual(first["err"], "ok")
        self.assertEqual([row["content"] for row in first["comments"]], ["first export comment"])
        self.assertEqual(first["next_cursor"], str(self.row_ids[0]))

        second = self.json(
            "/api/v1/comments?cursor=%s&limit=200" % first["next_cursor"],
            headers=self.auth_headers(),
        )
        self.assertEqual([row["content"] for row in second["comments"]], ["second export comment"])
        exported = second["comments"][0]
        self.assertEqual(exported["id"], str(self.row_ids[2]))
        self.assertEqual(exported["book_id"], "91001")
        self.assertEqual(exported["chapter_id"], "92001")
        self.assertEqual(exported["segment_id"], "3")
        self.assertEqual(exported["summary"], "second export comment")
        self.assertEqual(exported["created_at"], "2026-08-17T12:00:00")
        self.assertIn("/api/review/list?book_id=91001&chapter_id=92001&segment_id=3", exported["url"])
        self.assertEqual(second["next_cursor"], str(self.row_ids[2]))


class TestReviewAddTruncate(TestWithUserLogin):
    def test_refer_text_truncated(self):
        long_refer = "字" * 200
        body = json.dumps({
            "book_id": 1, "chapter_name": "trunc-ut-chapter",
            "segment_id": 0, "cfi": "", "content": "c",
            "type": models.ReviewType.text, "refer_text": long_refer,
        })
        d = self.json("/api/review/add", method="POST", body=body,
                      headers={"Content-Type": "application/json"})
        self.assertEqual(d["err"], "ok")
        self.assertEqual(len(d["data"]["referText"]), 80)
        # 清理
        db = get_db()
        db.query(models.Review).filter(models.Review.id == d["data"]["reviewId"]).delete()
        db.query(models.ReviewChapter).filter(models.ReviewChapter.title == "trunc-ut-chapter").delete()
        db.commit()


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
        format="%(asctime)s %(levelname)7s "
        "%(pathname)s:%(lineno)d %(message)s",
    )'''
    unittest.main()
