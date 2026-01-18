#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import logging
import threading
import queue
from queue import Queue
import traceback


class SingletonType(type):

    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super(SingletonType, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class AsyncService(metaclass=SingletonType):
    session = None
    scoped_session = None
    running = {}  # name -> (thread, queue)
    _lock = threading.Lock()

    def __init__(self):
        self.scoped_session = lambda : 'no-session'

    def setup(self, scoped_session=None):
        if scoped_session:
            self.scoped_session = scoped_session
            self.session = scoped_session()

    def get_queue(self, service_name) -> Queue:
        with self._lock:
            if service_name not in self.running:
                return None
            return self.running[service_name][1]

    def start_service(self, service_func) -> Queue:
        name = service_func.__name__

        with self._lock:
            if name in self.running:
                return self.running[name][1]

            logging.info("** Start Thread Service <%s> ** from %s", name, self)
            q = Queue(maxsize=1000)  # 设置队列最大长度，防止内存溢出
            t = threading.Thread(target=self.loop, args=(service_func, q), daemon=True)
            t.name = self.__class__.__name__ + "." + service_func.__name__
            t.start()
            self.running[name] = (t, q)
            return q

    def loop(self, service_func, q):
        name = service_func.__name__
        while True:
            try:
                args, kwargs = q.get(timeout=3600)  # 超时机制，防止无限阻塞
                # 在子线程中重新生成session
                self.session = self.scoped_session()
                logging.info("create new session_id=%s", id(self.session))
                logging.info("call: func=%s, args=%s, kwargs=%s", name, args, kwargs)

                try:
                    service_func(self, *args, **kwargs)
                except Exception as err:
                    logging.error("run task error: %s", err)
                    logging.error(traceback.format_exc())
                finally:
                    logging.info("end : func=%s, args=%s, kwargs=%s", name, args, kwargs)
                    try:
                        self.scoped_session.remove()
                    except Exception as e:
                        logging.error("Failed to remove session: %s", e)

                q.task_done()
            except queue.Empty:
                logging.debug("Queue timeout for service: %s", name)
            except Exception as err:
                logging.error("loop error: %s", err)
                logging.error(traceback.format_exc())

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
            logging.debug("[FUNC ] service call %s(%s, %s)", name, args, kwargs)
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
                logging.debug("[FUNC ] service call %s(%s, %s)", name, args, kwargs)
                return service_func(ins, *args, **kwargs)

            logging.debug("[ASYNC] service call %s(%s, %s)", name, args, kwargs)
            try:
                q = ins.start_service(service_func)
                q.put((args, kwargs), timeout=5)  # 设置put超时，防止队列满时阻塞
            except queue.Full:
                logging.error("Queue is full for service: %s", name)
            except Exception as e:
                logging.error("Failed to queue task: %s", e)
                logging.error(traceback.format_exc())
            return None
        return func_wrapper
