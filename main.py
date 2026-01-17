#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import os
import re
import sys
from gettext import gettext as _

import tornado.httpserver
import tornado.ioloop
import tornado.log
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from tornado import web
from tornado.options import define, options

import loader, models, handlers
from services import AsyncService

CONF = loader.get_settings()
define("host", default="", type=str, help=_("The host address on which to listen"))
define("port", default=8080, type=int, help=_("The port on which to listen."))
define("syncdb", default=False, type=bool, help=_("Create all tables"))


def safe_filename(filename):
    return re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_", filename)  # 替换为下划线


def bind_topdir_book_names(cache):
    old_construct_path_name = cache.backend.construct_path_name

    def new_construct_path_name(*args, **kwargs):
        s = old_construct_path_name(*args, **kwargs)
        ns = s[0] + "/" + s
        logging.debug("new str = %s" % ns)
        return ns

    cache.backend.construct_path_name = new_construct_path_name
    return


def make_app():
    auth_db_path = CONF["user_database"]
    logging.debug("Init AuthDB  with [%s]" % auth_db_path)

    # build sql session factory
    engine = create_engine(auth_db_path, **CONF["db_engine_args"])
    ScopedSession = scoped_session(sessionmaker(bind=engine, autoflush=True, autocommit=False))

    if options.syncdb:
        models.user_syncdb(engine)
        logging.info("Create tables into DB")
        sys.exit(0)

    app_settings = dict(CONF)
    app_settings.update(
        {
            "ScopedSession": ScopedSession,
        }
    )

    logging.info("Now, Running...")
    AsyncService().setup(ScopedSession)
    app = web.Application(handlers.routes(), **app_settings)
    app._engine = engine
    return app


def get_upload_size():
    n = 1
    s = CONF["MAX_UPLOAD_SIZE"].lower().strip()
    if s.endswith("k") or s.endswith("kb"):
        n = 1024
        s = s.split("k")[0]
    elif s.endswith("m") or s.endswith("mb"):
        n = 1024 * 1024
        s = s.split("m")[0]
    elif s.endswith("g") or s.endswith("gb"):
        n = 1024 * 1024 * 1024
        s = s.split("g")[0]
    s = s.strip()
    return int(s) * n


def setup_logging():
    # tornado 的 默认log 已在supervisor中配置为file了，这里再增加一个console的
    # 创建控制台处理程序并设置格式
    logger = logging.getLogger()
    if options.log_file_prefix:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(tornado.log.LogFormatter())
        logger.addHandler(console_handler)


def start_server():
    """启动服务器的核心逻辑"""
    logging.info("Starting server initialization...")
    
    # 创建应用
    app = make_app()
    
    # 创建HTTP服务器
    http_server = tornado.httpserver.HTTPServer(
        app, 
        xheaders=True, 
        max_buffer_size=get_upload_size()
    )
    
    # 绑定端口
    http_server.listen(options.port, options.host)
    logging.info(f"Server started successfully on {options.host or '0.0.0.0'}:{options.port}")
    logging.info("Press Ctrl+C to stop the server")
    
    # 获取IOLoop实例并启动
    ioloop = tornado.ioloop.IOLoop.current()
    ioloop.start()


def main():
    try:
        # 解析命令行参数
        tornado.options.parse_command_line()
        
        # 设置日志
        setup_logging()
        
        # 启动服务器
        start_server()
        
    except OSError as e:
        if "Address already in use" in str(e):
            logging.error(f"Failed to start server: Address {options.host or '0.0.0.0'}:{options.port} already in use")
            logging.error(f"Please try a different port with: python main.py --port <new_port>")
        else:
            logging.error(f"Failed to start server: {e}")
        return 1
    except KeyboardInterrupt:
        logging.info("\nReceived Ctrl+C, shutting down server...")
        logging.info("Server stopped")
        return 0
    except Exception as e:
        logging.error(f"Failed to initialize or run server: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.path.append(os.path.dirname(__file__))
    sys.exit(main())