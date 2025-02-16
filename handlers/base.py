#!/usr/bin/env python3
# -*- coding: UTF-8 -*-


import base64
import datetime
import logging
import time
from collections import defaultdict
from gettext import gettext as _

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func as sql_func
from tornado import web

import loader

# import social_tornado.handlers
from models import Reader

messages = defaultdict(list)
CONF = loader.get_settings()


def day_format(value, format="%Y-%m-%d"):
    try:
        return value.strftime(format)
    except:
        return "1990-01-01"


def js(func):
    def do(self, *args, **kwargs):
        try:
            rsp = func(self, *args, **kwargs)
            rsp["msg"] = rsp.get("msg", "")
        except Exception as e:
            import traceback

            logging.error(traceback.format_exc())
            msg = (
                'Exception:<br><pre style="white-space:pre-wrap;word-break:keep-all">%s</pre>' % traceback.format_exc()
            )
            rsp = {"err": "exception", "msg": msg}
            if isinstance(e, web.Finish):
                rsp = ""
        self.prepare_headers()
        self.set_header("Cache-Control", "max-age=0")
        self.write(rsp)
        self.finish()
        return

    return do


def auth(func):
    def do(self, *args, **kwargs):
        if not self.current_user:
            return {"err": "user.need_login", "msg": _(u"请先登录")}
        return func(self, *args, **kwargs)

    return do


class BaseHandler(web.RequestHandler):
    _path_to_env = {}

    def _request_summary(self) -> str:
        userid = 0
        email = "-"
        if self.current_user:
            userid = self.current_user.id
            email = self.current_user.email

        return '%s %s (%s) "%d %s"' % (
            self.request.method,
            self.request.uri,
            self.request.remote_ip,
            userid,
            email,
        )

    def get_secure_cookie(self, key):
        if not self.cookies_cache.get(key, ""):
            self.cookies_cache[key] = super(BaseHandler, self).get_secure_cookie(key)
        return self.cookies_cache[key]

    def set_secure_cookie(self, key, val):
        self.cookies_cache[key] = val
        super(BaseHandler, self).set_secure_cookie(key, val)
        return None

    def head(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def options(self, *args, **kwargs):
        return self.finish()

    def process_auth_header(self):
        auth_header = self.request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        auth_decoded = base64.decodebytes(auth_header[6:].encode("ascii")).decode("UTF-8")
        email, password = auth_decoded.split(":", 2)
        user = self.session.query(Reader).filter(Reader.email == email).first()
        if not user:
            return False
        if user.get_secure_password(password) != str(user.password):
            return False
        self.login_user(user)
        return True

    def set_hosts(self):
        # site_url为完整路径，用于发邮件等
        host = self.request.headers.get("X-Forwarded-Host", self.request.host)
        self.site_url = self.request.protocol + "://" + host

        # 默认情况下，访问站内资源全部采用相对路径
        self.api_url = ""  # API动态请求地址
        self.cdn_url = ""  # 可缓存的资源，图片，文件

        # 如果设置有static_host配置，则改为绝对路径
        if CONF["static_host"]:
            self.api_url = self.request.protocol + "://" + host
            self.cdn_url = self.request.protocol + "://" + CONF["static_host"]

    def prepare_headers(self):
        origin = self.request.headers.get("origin", "*")
        self.set_header("Access-Control-Allow-Origin", origin)
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE')
        self.set_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.set_header("Access-Control-Allow-Credentials", "true")

    def prepare(self):
        self.prepare_headers()
        self.set_hosts()
        self.set_i18n()
        self.process_auth_header()

    def set_i18n(self):
        return
        # TODO set correct language package
        # import gettext
        # accept = self.request.headers.get("Accept-Language", "")
        # langs = [v.strip().split(";")[0] for v in accept.split(",") if v.strip()]
        # logging.debug("choose lang: %s" % langs)
        # if not langs: langs = ["zh_CN"]
        # lang = gettext.translation('messages', localedir=CONF['i18n_path'], languages=langs, fallback=True)
        # lang.install(unicode=True)

    def initialize(self):
        ScopedSession = self.settings["ScopedSession"]
        self.session = ScopedSession()  # new sql session
        self.admin_user = None
        self.cookies_cache = {}

    def on_finish(self):
        ScopedSession = self.settings["ScopedSession"]
        self.session.close()
        ScopedSession.remove()

    def static_url(self, path, **kwargs):
        if path.endswith("/"):
            prefix = self.settings.get("static_url_prefix", "/static/")
            return self.cdn_url + prefix + path
        else:
            return self.cdn_url + super(BaseHandler, self).static_url(path, **kwargs)

    def user_id(self):
        login_time = self.get_secure_cookie("lt")
        if not login_time or int(login_time) < int(time.time()) - 7 * 86400:
            return None
        uid = self.get_secure_cookie("user_id")
        return int(uid) if uid and uid.isdigit() else None

    def get_current_user(self):
        user_id = self.user_id()
        if user_id:
            user_id = int(user_id)
        return self.session.get(Reader, user_id) if user_id else None

    def is_admin(self):
        if self.admin_user:
            return True
        if not self.current_user:
            return False
        return self.current_user.is_admin

    def login_user(self, user):
        logging.info("LOGIN: %s - %d - %s" % (self.request.remote_ip, user.id, user.email))
        self.set_secure_cookie("user_id", str(user.id))
        self.set_secure_cookie("lt", str(int(time.time())))
        user.access_time = datetime.datetime.now()
        user.extra["login_ip"] = self.request.remote_ip
        user.save()

    def last_modified(self, updated):
        """
        Generates a locale independent, english timestamp from a datetime
        object
        """
        lm = updated.strftime("day, %d month %Y %H:%M:%S GMT")
        day = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
        lm = lm.replace("day", day[int(updated.strftime("%w"))])
        month = {
            1: "Jan",
            2: "Feb",
            3: "Mar",
            4: "Apr",
            5: "May",
            6: "Jun",
            7: "Jul",
            8: "Aug",
            9: "Sep",
            10: "Oct",
            11: "Nov",
            12: "Dec",
        }
        return lm.replace("month", month[updated.month])

    def get_template_path(self):
        """获取模板路径"""
        return CONF.get("resource_path", "templates")

    def create_template_loader(self, template_path):
        """根据template_path创建相对应的Jinja2 Environment"""
        temp_path = template_path
        if isinstance(template_path, (list, tuple)):
            temp_path = template_path[0]

        env = BaseHandler._path_to_env.get(temp_path)
        if not env:
            logging.debug("create template env for [%s]" % template_path)
            _loader = FileSystemLoader(template_path)
            env = Environment(loader=_loader)
            env.filters["day"] = day_format
            # env.globals['gettext'] = _
            BaseHandler._path_to_env[temp_path] = env
        return env

    def render_string(self, template_name, **kwargs):
        """使用Jinja2模板引擎"""
        env = self.create_template_loader(self.get_template_path())
        t = env.get_template(template_name)
        namespace = self.get_template_namespace()
        namespace.update(kwargs)
        return t.render(**namespace)

    def html_page(self, template, *args, **kwargs):
        self.set_header("Cache-Control", "max-age=0")
        request = self.request
        request.user = self.current_user
        request.user_extra = {}
        request.admin_user = self.admin_user
        if request.user:
            request.user_extra = self.current_user.extra
            if not request.user.avatar:
                request.user.avatar = "//tva1.sinaimg.cn/default/images/default_avatar_male_50.gif"
            else:
                request.user.avatar = request.user.avatar.replace("http://", "//")

        last_week = datetime.datetime.now() - datetime.timedelta(days=7)
        page_vars = {
            "db": self.db,
            "count_all_users": self.session.query(sql_func.count(Reader.id)).scalar(),
            "count_hot_users": self.session.query(sql_func.count(Reader.id))
            .filter(Reader.access_time > last_week)
            .scalar(),
            "IMG": self.cdn_url,
            "SITE_TITLE": CONF["site_title"],
        }
        vals = dict(*args, **kwargs)
        vals.update(page_vars)
        vals.update(vars())
        del vals["self"]
        self.write(self.render_string(template, **vals))
