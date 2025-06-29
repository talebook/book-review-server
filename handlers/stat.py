#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import re

from handlers.base import BaseHandler
import tornado.escape
import loader
import models

CONF = loader.get_settings()


class SystemStat(BaseHandler):
    def get(self):
        book_count = self.session.query(models.ReviewBook).count()
        chapter_count = self.session.query(models.ReviewChapter).count()
        review_count = self.session.query(models.Review).count()
        reader_count = self.session.query(models.Reader).count()

        out = f"""[Stat]
Reader:  {reader_count}
Book:    {book_count}
Chapter: {chapter_count}
Reviews: {review_count}
"""
        self.write(out)
        return


def routes():
    return [
        (r"/", SystemStat),
    ]
