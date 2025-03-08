#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import hashlib
import time
import re

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship, declarative_base

import loader

CONF = loader.get_settings()
Base = declarative_base()


def mksalt():
    import random
    import string

    # for python3, just use: crypt.mksalt(crypt.METHOD_SHA512)
    saltchars = string.ascii_letters + string.digits + "./"
    salt = []
    for c in range(32):
        idx = int(random.random() * 10000) % len(saltchars)
        salt.append(saltchars[idx])
    return "".join(salt)


def to_dict(self):
    return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}


Base.to_dict = to_dict


class Reader(Base):
    # 权限位
    SPECIAL = 0b00000001  # 未开启说明是默认权限
    LOGIN = 0b00000010  # 登录
    VIEW = 0b00000100  # 浏览
    READ = 0b00001000  # 阅读
    UPLOAD = 0b00010000  # 上传
    DOWNLOAD = 0b00100000  # 下载

    OVERSIZE_SHRINK_RATE = 0.8
    SQLITE_MAX_LENGTH = 32 * 1024.0

    RE_EMAIL = r"[^@]+@[^@]+\.[^@]+"
    RE_PASSWORD = r'[a-zA-Z0-9!@#$%^&*()_+\-=[\]{};\':",./<>?\|]*'

    __tablename__ = "readers"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True)
    avatar = Column(String(200))
    nickname = Column(String(100), unique=True)
    password = Column(String(200), default="")
    salt = Column(String(200))
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    permission = Column(String(100), default="")
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    access_time = Column(DateTime)
    last_read = Column(DateTime)

    def __str__(self):
        return "<id=%d, email=%s>" % (self.id, self.email)

    def reset_password(self):
        s = "%s%s%s" % (self.email, self.create_time.strftime("%s"), time.time())
        p = hashlib.md5(s.encode("UTF-8")).hexdigest()[:16]
        self.set_secure_password(p)
        return p

    def get_secure_password(self, raw_password):
        p1 = hashlib.sha256(raw_password.encode("UTF-8")).hexdigest()
        p2 = hashlib.sha256((self.salt + p1).encode("UTF-8")).hexdigest()
        return p2

    def set_secure_password(self, raw_password):
        self.salt = mksalt()
        self.password = self.get_secure_password(raw_password)

    def set_permission(self, operations):
        ALL = "delprsuv"
        if not isinstance(operations, str):
            raise "bug"
        v = list(self.permission)
        for p in operations:
            if p.lower() not in ALL:
                continue
            r = p.upper() if p.islower() else p.lower()
            try:
                v.remove(r)
            except:
                pass
            v.append(p)
        self.permission = "".join(sorted(v))

    def has_permission(self, operation, default=True):
        if operation.lower() in self.permission:
            return True
        if operation.upper() in self.permission:
            return False
        return default

    def can_delete(self):
        return self.has_permission("d")

    def can_edit(self):
        return self.has_permission("e")

    def can_login(self):
        return self.has_permission("l")

    def data(self):
        gravatar_url = "https://www.gravatar.com"
        avatar = self.avatar or ""
        avatar = avatar.replace("http://", "https://").replace(gravatar_url, CONF["avatar_service"])

        return {
            "id": self.id,
            "email": self.email,
            "nickname": self.nickname,
            "avatar": self.avatar,
            "permission": self.permission,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": self.update_time.strftime("%Y-%m-%d %H:%M:%S"),
        }


class ReviewType:
    text = 1
    like = 2
    dislike = 3


class ReviewStatus:
    unread = 1
    read = 2
    deleted = 3


class ReviewBook(Base):
    __tablename__ = "review_books"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), default="")
    alias = Column(String(5120), default="")


class ReviewChapter(Base):
    __tablename__ = "review_chapters"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, default=0)
    title = Column(String(255), default="")  # 章节名称，例如「第一章 绯红」
    alias = Column(String(5120), default="")  # 章节别名，例如「第一章 绯红（求月票）」
    parents = Column(String(5120), default="")  # 父章节名，例如「第一部 小丑」

    @staticmethod
    def clean_title(title):
        s = title.replace("\u3000", " ")  # 替换全角空格
        s = re.sub(r"\s\s*", " ", s)  # 多个空格合并为一个
        s = re.sub("[（（【].*[】））]", "", s)  # 删掉括号里的内容
        return s


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, default=0)  # 书籍 ID
    chapter_id = Column(Integer, default=0)  # 章节 ID
    segment_id = Column(Integer, default=0)  # 段落 ID

    cfi = Column(String(255), default="")
    cfi_base = Column(String(255), default="")
    type = Column(Integer, default=0)  # ReviewType：文字、点赞、踩
    level = Column(Integer, default=0)  # 评论楼层
    content = Column(String(1024), default="")  # 评论内容
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    geo = Column(String(255), default="")

    user_id = Column(Integer, ForeignKey("readers.id"))
    root_id = Column(Integer, ForeignKey("reviews.id"))
    quote_id = Column(Integer, ForeignKey("reviews.id"))

    # 定义关系属性
    user = relationship("Reader")

    # 定义与自身关联的关系，用于表示根评论（root）
    root = relationship(
        "Review",
        remote_side=[id],  # 指明远程端，也就是关联的另一端的主键，这里是自身的id列
        foreign_keys=[root_id],  # 指明当前关系对应的外键列
        backref="all_reply",  # 反向引用名称，方便从根评论反向获取子评论
        lazy="select",  # 设置加载策略为懒加载，按需加载关联对象，避免潜在循环依赖问题
    )

    # 定义与自身关联的关系，用于表示引用的评论（quote）
    quote = relationship("Review", remote_side=[id], foreign_keys=[quote_id], backref="sub_reply", lazy="select")

    # user = relationship(Reader, primaryjoin=user_id == Reader.id)
    # root = relationship("Review", primaryjoin="root_id == Review.id")
    # quote = relationship("Review", primaryjoin="quote_id == Review.id")

    like_count = Column(Integer, default=0)
    dislike_count = Column(Integer, default=0)

    def to_full_dict(self, current_user=None):
        row = self
        d = {}
        d["reviewId"] = row.id
        d["cbid"] = row.book_id
        d["ccid"] = row.chapter_id
        d["bookId"] = row.book_id
        d["chapterId"] = row.chapter_id
        d["content"] = row.content
        d["segmentId"] = row.segment_id
        d["type"] = row.type
        d["geo"] = row.geo
        d["level"] = row.level
        d["createTime"] = row.create_time.strftime("%Y-%m-%d %H:%M:%S")
        d["updateTime"] = row.update_time.strftime("%Y-%m-%d %H:%M:%S")
        d["userId"] = row.user.id
        d["avatar"] = row.user.avatar
        d["nickName"] = row.user.nickname
        d["rootReviewId"] = row.root_id
        d["quoteReviewId"] = row.quote_id
        d["quoteContent"] = ""
        d["quoteUserId"] = 0
        d["quoteNickName"] = ""
        d["isSelf"] = False
        if row.quote_id:
            d["quoteContent"] = row.quote.content
            d["quoteUserId"] = row.quote.user_id
            d["quoteNickName"] = row.quote.user.nickname
        if current_user:
            d["isSelf"] = row.user_id == current_user.id
        return d


def user_syncdb(engine):
    Base.metadata.create_all(engine)
