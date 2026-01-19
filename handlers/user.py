#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import hashlib
import logging
import re

import tornado.escape
from gettext import gettext as _

import loader
from services.mail import MailService
from handlers.base import BaseHandler, auth, js
from models import Reader

CONF = loader.get_settings()


class UserUpdate(BaseHandler):
    @js
    @auth
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        user = self.current_user
        # 确保user不是None
        if not user:
            return {"err": "user.need_login", "msg": _(u"请先登录")}
        
        nickname = data.get("nickname", "")
        if nickname:
            nickname = nickname.strip()
            if len(nickname) > 0:
                if len(nickname) < 3:
                    return {"err": "params.nickname.invalid", "msg": _(u"昵称无效")}
                user.nickname = nickname

        p0 = data.get("password0", "").strip()
        p1 = data.get("password1", "").strip()
        if len(p0) > 0:
            if not user.get_secure_password(p0):
                return {"err": "params.password.error", "msg": _(u"密码错误")}
            if len(p1) < 8 or len(p1) > 20 or not re.match(Reader.RE_PASSWORD, p1):
                return {"err": "params.password.invalid", "msg": _(u"密码无效")}
            logging.info(f'{user.nickname} 更改密码')
            user.set_secure_password(p1)

        self.session.add(user)

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": user.data()}


class SignUp(BaseHandler):
    def send_notice_email(self, user, password):
        # send notice email
        args = {
            "site_title": CONF["site_title"],
            "nickname": user.nickname,
            "password": password,
        }
        mail_subject = CONF["RESET_MAIL_TITLE"] % args
        mail_to = user.email
        mail_from = CONF["smtp_username"]
        mail_body = CONF["RESET_MAIL_CONTENT"] % args
        MailService().send_mail(mail_from, mail_to, mail_subject, mail_body)

    @js
    def post(self):
        # 随机生成一个默认密码，并发送邮件
        email = self.get_argument("email", "").strip()
        nickname = self.get_argument("nickname", "").strip()

        if not nickname or not email:
            return {"err": "params.invalid", "msg": _(u"用户名或密码无效")}
        if not re.match(Reader.RE_EMAIL, email):
            return {"err": "params.email.invalid", "msg": _(u"Email无效")}
        if len(nickname) < 2 or len(nickname) > 50:
            return {"err": "params.nickname.invalid", "msg": _(u"用户名无效")}

        user = self.session.query(Reader).filter(Reader.email == email).first()
        if user:
            return {"err": "params.user.exist", "msg": _(u"邮箱已被使用")}

        user = Reader()
        user.email = email
        user.nickname = nickname
        user.avatar = CONF["avatar_service"] + "/avatar/" + hashlib.md5(email.encode("UTF-8")).hexdigest()
        user.create_time = datetime.datetime.now()
        user.update_time = datetime.datetime.now()
        user.access_time = datetime.datetime.now()
        user.is_active = True
        password = user.reset_password()
        self.session.add(user)

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}

        self.send_notice_email(user, password)
        return {"err": "ok", "msg": "ok"}


class SignIn(BaseHandler):
    @js
    def post(self):
        email = self.get_argument("email", "").strip().lower()
        password = self.get_argument("password", "").strip()
        if not email or not password:
            return {"err": "params.invalid", "msg": _(u"邮箱或密码错误")}
        user = self.session.query(Reader).filter(Reader.email == email).first()
        if not user:
            return {"err": "params.no_user", "msg": _(u"无此用户")}
        if not user.get_secure_password(password):
            return {"err": "params.invalid", "msg": _(u"用户名或密码错误")}
        if not user.can_login():
            return {"err": "permission", "msg": _(u"无权登录")}
        logging.debug("PERM = %s", user.permission)

        self.login_user(user)
        return {"err": "ok", "msg": "ok", "data": user.data()}


class UserReset(SignUp):
    @js
    def post(self):
        email = self.get_argument("email", "").strip().lower()
        if not email:
            return {"err": "params.invalid", "msg": _(u"参数错误")}
        user = self.session.query(Reader).filter(Reader.email == email).first()
        if not user:
            return {"err": "params.no_user", "msg": _(u"无此用户")}
        password = user.reset_password()
        self.session.add(user)

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}

        self.send_notice_email(user, password)
        return {"err": "ok"}


class SignOut(BaseHandler):
    @js
    @auth
    def get(self):
        self.set_secure_cookie("user_id", "")
        self.set_secure_cookie("admin_id", "")
        return {"err": "ok", "msg": _(u"你已成功退出登录。")}


class UserInfo(BaseHandler):
    @js
    @auth
    def get(self):
        rsp = {
            "err": "ok",
            "msg": "ok",
            "data": self.current_user.data(),
        }
        return rsp


def routes():
    return [
        (r"/api/user/info", UserInfo),
        (r"/api/user/sign_in", SignIn),
        (r"/api/user/sign_up", SignUp),
        (r"/api/user/sign_out", SignOut),
        (r"/api/user/update", UserUpdate),
        (r"/api/user/reset", UserReset),
    ]
