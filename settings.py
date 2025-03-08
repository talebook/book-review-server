#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# fmt: off
# flake8: noqa

import os

settings = {
    'installed'     : True,
    "autoreload"    : True,
    "xsrf_cookies"  : False,
    "static_host"   : "",
    "nuxt_env_path" : os.path.join(os.path.dirname(__file__), "../app/.env"),
    "html_path"     : os.path.join(os.path.dirname(__file__), "../app/dist"),
    "i18n_path"     : os.path.join(os.path.dirname(__file__), "i18n"),
    "static_path"   : os.path.join(os.path.dirname(__file__), "../app/dist"),
    "resource_path" : os.path.join(os.path.dirname(__file__), "resources"),
    "settings_path" : "/data/books/settings/",
    "extract_path"  : "/data/books/extract/",
    "cookie_secret" : "cookie_secret",
    "cookie_expire" : 7*86400,
    "login_url"     : "/login",
    "user_database" : 'sqlite:////tmp/candle-reader.db',
    # "user_database" : 'mysql+pymysql://brs:brs-is-best@mysql:3306/brs',
    "site_title"    : "奇异书屋",


    # https://analytics.google.com/
    "google_analytics_id" : "G-LLF01B5ZZ8",

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

    'ALLOW_REGISTER' : True,
    'HEADER': '欢迎访问！如果你喜欢此项目，请前往 Github <a target="_blank" href="https://github.com/talebook/talebook"> 给 talebook 点击一个Star！</a>',
    'FOOTER': '所有资源搜集于互联网，如有侵权请邮件联系。',

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
