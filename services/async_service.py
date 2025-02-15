#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import threading
from queue import Queue


class SingletonType(type):

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonType, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class AsyncService(metaclass=SingletonType):
    session = None
    scoped_session = None
    running = {}  # name -> (thread, queue)

    def __init__(self):
        self.scoped_session = lambda : 'no-session'

    def setup(self, scoped_session=None):
        self.scoped_session = scoped_session
        self.session = scoped_session()

    def get_queue(self, service_name) -> Queue:
        if service_name not in self.running:
            return None
        return self.running[service_name][1]

    def start_service(self, service_func) -> Queue:
        name = service_func.__name__
        if name in self.running:
            return self.running[name][1]

        logging.info("** Start Thread Service <%s> ** from %s", name, self)
        q = Queue()
        t = threading.Thread(target=self.loop, args=(service_func, q))
        t.name = self.__class__.__name__ + "." + service_func.__name__
        t.setDaemon(True)
        t.start()
        self.running[name] = (t, q)
        return q

    def loop(self, service_func, q):
        name = service_func.__name__
        while True:
            args, kwargs = q.get()
            # 在子进程中重新生成session
            self.session = AsyncService().scoped_session()
            logging.info("create new session_id=%s", self.session.hash_key)
            logging.info("call: func=%s, args=%s, kwargs=%s", name, args, kwargs)
            try:
                service_func(self, *args, **kwargs)
            except Exception as err:
                logging.exception("run task error: %s", err)
            logging.info("end : func=%s, args=%s, kwargs=%s", name, args, kwargs)
            self.scoped_session.remove()

    # 注册服务
    def async_mode(self):
        ''' for unittest '''
        return True

    @staticmethod
    def register_function(service_func):
        name = service_func.__name__
        logging.debug("service register <%s>", name)

        def func_wrapper(ins: AsyncService, *args, **kwargs):
            s = AsyncService()
            ins.setup(s.scoped_session)
            logging.error("[FUNC ] service call %s(%s, %s)", name, args, kwargs)
            return service_func(ins, *args, **kwargs)

        return func_wrapper

    @staticmethod
    def register_service(service_func):
        name = service_func.__name__
        logging.debug("service register <%s>", name)

        def func_wrapper(ins: AsyncService, *args, **kwargs):
            s = AsyncService()
            ins.setup(s.scoped_session)

            if not s.async_mode():
                logging.error("[FUNC ] service call %s(%s, %s)", name, args, kwargs)
                return service_func(ins, *args, **kwargs)

            logging.error("[ASYNC] service call %s(%s, %s)", name, args, kwargs)
            q = ins.start_service(service_func)
            q.put((args, kwargs))
            return None
        return func_wrapper
