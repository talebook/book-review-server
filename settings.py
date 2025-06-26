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
    "user_database" : 'sqlite:////data/brs.db',
    #"user_database" : 'mysql+pymysql://brs:brs-is-best@mysql:3306/brs',
    "site_title"    : "章评系统",

    "db_engine_args": {
        "echo": False,
    },

    # 100MB, tornado default max_buffer_size value
    "MAX_UPLOAD_SIZE": "100MB",

    # See: http://service.mail.qq.com/cgi-bin/help?subtype=1&&no=1001256&&id=28
    'smtp_server'       : os.environ.get("SMTP_SERVER", "smtp.talebook.org"),
    'smtp_encryption'   : os.environ.get("SMTP_ENCRYPTION", "TLS"),
    'smtp_username'     : os.environ.get("SMTP_USERNAME", "sender@talebook.org"),
    'smtp_password'     : os.environ.get("SMTP_PASSWORD", "password"),

    'avatar_service'    : "https://cravatar.cn",

    'RESET_MAIL_TITLE': u'欢迎使用',
    'RESET_MAIL_CONTENT': u'''
Hi, %(nickname)s！

欢迎使用 %(site_title)s。

您的新密码是: %(password)s
''',

}
