#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import hashlib
import logging
import re
import os

import tornado.escape
from gettext import gettext as _

import loader
from services.mail import MailService
from handlers.base import BaseHandler, auth, js
from models import Reader

CONF = loader.get_settings()


class UserUpdate(BaseHandler):
    @js
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        user = self.current_user
        nickname = data.get("nickname", "")
        if nickname:
            nickname = nickname.strip()
            if len(nickname) > 0:
                if len(nickname) < 3:
                    return {"err": "params.nickname.invalid", "msg": _(u"昵称无效")}
                user.name = nickname

        p0 = data.get("password0", "").strip()
        p1 = data.get("password1", "").strip()
        p2 = data.get("password2", "").strip()
        if len(p0) > 0:
            if user.get_secure_password(p0) != user.password:
                return {"err": "params.password.error", "msg": _(u"密码错误")}
            if p1 != p2 or len(p1) < 8 or len(p1) > 20 or not re.match(Reader.RE_PASSWORD, p1):
                return {"err": "params.password.invalid", "msg": _(u"密码无效")}
            user.set_secure_password(p1)

        ke = data.get("kindle_email", "").strip()
        if len(ke) > 0:
            if not re.match(Reader.RE_EMAIL, ke):
                return {"err": "params.email.invalid", "msg": _(u"Kindle地址无效")}
            user.extra["kindle_email"] = ke

        try:
            user.save()
            self.add_msg("success", _("Settings saved."))
            return {"err": "ok"}
        except:
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}


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
        if len(nickname) < 5 or len(nickname) > 50:
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
        user.active = True
        user.extra = {"kindle_email": ""}
        password = user.reset_password()

        try:
            user.save()
        except:
            import traceback

            logging.error(traceback.format_exc())
            return {"err": "db.error", "msg": _(u"系统异常，请重试或更换注册信息")}

        self.send_notice_email(user, password)

        return {"err": "ok"}


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
        if user.get_secure_password(password) != user.password:
            return {"err": "params.invalid", "msg": _(u"用户名或密码错误")}
        if not user.can_login():
            return {"err": "permission", "msg": _(u"无权登录")}
        logging.debug("PERM = %s", user.permission)

        self.login_user(user)
        return {"err": "ok", "msg": "ok"}


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

        # do save into db
        try:
            user.save()
        except:
            return {"err": "db.error", "msg": _(u"系统繁忙")}

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
    def get_sys_info(self):
        from sqlalchemy import func

        last_week = datetime.datetime.now() - datetime.timedelta(days=7)
        count_all_users = self.session.query(func.count(Reader.id)).scalar()
        count_hot_users = self.session.query(func.count(Reader.id)).filter(Reader.access_time > last_week).scalar()
        return {
            "users": count_all_users,
            "active": count_hot_users,
            "version": os.environ.get("VERSION", "0.0.0"),
            "title": CONF["site_title"],
            "footer": CONF["FOOTER"],
            "header": CONF["HEADER"],
            "allow": {
                "register": CONF["ALLOW_REGISTER"],
            },
        }

    def get_user_info(self, detail):
        user = self.current_user
        d = {
            "avatar": "https://tva1.sinaimg.cn/default/images/default_avatar_male_50.gif",
            "is_login": False,
            "is_admin": False,
            "nickname": "",
            "email": "",
            "kindle_email": "",
            "extra": {},
        }

        if not user:
            return d

        d.update(
            {
                "is_login": True,
                "is_admin": user.is_admin(),
                "is_active": user.is_active(),
                "nickname": user.nickname or "",
                "email": user.email,
                "extra": {},
                "create_time": user.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        if user.avatar:
            gravatar_url = "https://www.gravatar.com"
            d["avatar"] = user.avatar.replace("http://", "https://").replace(gravatar_url, CONF["avatar_service"])
        return d

    @js
    def get(self):
        if CONF.get("installed", None) is False:
            return {"err": "not_installed"}

        detail = self.get_argument("detail", "")
        rsp = {
            "err": "ok",
            "cdn": self.cdn_url,
            "sys": self.get_sys_info() if not detail else {},
            "user": self.get_user_info(detail),
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
