#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# fmt: off
# flake8: noqa

import os

settings = {
    'installed'     : True,
    "autoreload"    : True,
    "static_host"   : "",
    "cookie_secret" : "cookie_secret",
    "settings_path" : "/data/books/settings/",
    # "user_database" : 'sqlite:////tmp/candle-reader.db',
    "user_database" : 'mysql+pymysql://brs:brs-is-best@mysql:3306/brs',
    "site_title"    : "奇异书屋",

    "db_engine_args": {
        "echo": False,
    },

    # 100MB, tornado default max_buffer_size value
    "MAX_UPLOAD_SIZE": "100MB",

    # See: http://service.mail.qq.com/cgi-bin/help?subtype=1&&no=1001256&&id=28
    'smtp_server'       : "smtp.talebook.org",
    'smtp_encryption'   : "TLS",
    'smtp_username'     : "sender@talebook.org",
    'smtp_password'     : "password",

    'avatar_service'    : "https://cravatar.cn",

    'SIGNUP_MAIL_TITLE': u'欢迎注册奇异书屋',
    'SIGNUP_MAIL_CONTENT': u'''
Hi, %(nickname)s！
欢迎注册%(site_title)s，这里虽然是个小小的图书馆，但是希望你找到所爱。

点击链接激活你的账号: %(active_link)s
''',

    'RESET_MAIL_TITLE': u'奇异书屋密码重置',
    'RESET_MAIL_CONTENT': u'''
Hi, %(nickname)s！

欢迎使用 %(site_title)s。

您的新密码是: %(password)s
''',

}
