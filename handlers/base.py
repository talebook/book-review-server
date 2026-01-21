#!/usr/bin/env python3
# -*- coding: UTF-8 -*-


import base64
import datetime
import logging
import time
import urllib.parse
from gettext import gettext as _

from tornado import web

import loader

# import social_tornado.handlers
from models import Reader

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
        # 根据err字段设置HTTP状态码
        if isinstance(rsp, dict):
            if rsp.get("err") != "ok":
                # 对于错误响应，返回400状态码
                self.set_status(400)
            else:
                # 对于成功响应，返回200状态码
                self.set_status(200)
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

        # 解码URI，显示中文而不是URL编码
        decoded_uri = urllib.parse.unquote(self.request.uri)

        return '%s %s (%s) "%d %s"' % (
            self.request.method,
            decoded_uri,
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
        super(BaseHandler, self).set_secure_cookie(
            key,
            val,
            samesite="none",  # 支持跨站调用
            secure=True,        # SameSite=None必须同时设置secure=True
            httponly=True,      # 防止XSS攻击
            expires_days=30     # 设置30天过期时间
        )
        return None

    def head(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def options(self, *args, **kwargs):
        return self.finish()

    def process_auth_header(self):
        auth_header = self.request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        try:
            auth_decoded = base64.decodebytes(auth_header[6:].encode("ascii")).decode("UTF-8")
            email, password = auth_decoded.split(":", 2)
            user = self.session.query(Reader).filter(Reader.email == email).first()
            if not user:
                return False
            if not user.get_secure_password(password):
                return False
            self.login_user(user)
            return True
        except Exception as e:
            logging.error(f"Basic auth failed: {e}")
            return False

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
        # 更安全的CORS设置，只允许指定来源
        allowed_origins = CONF.get('allowed_origins', ['*'])
        origin = self.request.headers.get("origin", "*")

        # 处理CORS Origin，支持通配符
        if allowed_origins != ['*']:
            # 检查origin是否在允许列表中，支持通配符
            origin_allowed = False
            for allowed_origin in allowed_origins:
                if allowed_origin == '*':
                    origin_allowed = True
                    break
                elif allowed_origin.startswith('*.'):
                    # 处理通配符情况，如*.talebook.org
                    domain = allowed_origin[2:]  # 去掉*.前缀
                    if origin.endswith(domain) or origin == domain:
                        origin_allowed = True
                        break
                elif origin == allowed_origin:
                    origin_allowed = True
                    break

            if not origin_allowed:
                origin = allowed_origins[0] if allowed_origins else '*'

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
        self.session.add(user)
        self.session.commit()

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

    def commit(self):
        try:
            self.session.commit()
            return True
        except:
            logging.exception("db commit fail")
            self.session.rollback()
            return False
