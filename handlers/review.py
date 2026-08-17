#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import hmac
import urllib.parse
from gettext import gettext as _

import tornado.escape
import loader
from handlers.base import BaseHandler, auth, js
from models import Review, ReviewBook, ReviewChapter, ReviewType

from sqlalchemy import func, or_
from utils import super_strip

CONF = loader.get_settings()

# 引用正文只用于「一行」展示，发表时截断，避免千万级数据下的存储膨胀
REFER_TEXT_MAX = 80

# reader在获取toc后，将toc传递给server，然后构建对应的结构表；
# book_id -> [chapter_id] -> [segment_id]
# 每个toc展平，自身名称作为chapter_id，名称
# 每个p计算最近的一个chapter的距离 N 作为序号id


class ReviewSummary(BaseHandler):
    """获取「某书」+「某章节」的各个段落的评论数量"""

    @js
    def get(self):
        book_id = super_strip(self.get_argument("book_id", ""))
        chapter_name = super_strip(self.get_argument("chapter_name", ""))
        if not book_id or not chapter_name or not book_id.isdigit():
            return {"err": "params.invalid", "msg": _("参数错误")}

        # 查一下对应的章节信息是否存在
        name = ReviewChapter.clean_title(chapter_name)
        q = self.session.query(ReviewChapter)
        q = q.filter(ReviewChapter.book_id == book_id)
        q = q.filter(or_(ReviewChapter.title == name, ReviewChapter.alias == chapter_name))
        chapter = q.first()
        if chapter is None:
            return {"err": "ok", "data": {"list": []}}

        # 查询评论数量
        q = self.session.query(Review.segment_id, func.count().label("cnt"))
        q = q.filter(Review.book_id == book_id, Review.chapter_id == chapter.id)
        q = q.group_by(Review.segment_id)

        data = []
        for row in q.all():
            segment_id, cnt = row
            data.append({"segmentId": segment_id, "reviewNum": cnt})
        return {"err": "ok", "data": {"chapter_id": chapter.id, "list": data}}


class ReviewList(BaseHandler):
    """获取某个段落的所有评论"""

    @js
    def get(self):
        book_id = self.get_argument("book_id", "").strip()
        chapter_id = self.get_argument("chapter_id", "").strip()
        segment_id = self.get_argument("segment_id", "").strip()
        if not book_id or not chapter_id or not segment_id:
            return {"err": "params.invalid", "msg": _("参数错误")}

        if not book_id.isdigit() or not chapter_id.isdigit() or not segment_id.isdigit():
            return {"err": "params.invalid", "msg": _("参数错误")}

        q = self.session.query(Review).filter(
            Review.book_id == int(book_id), Review.chapter_id == int(chapter_id), Review.segment_id == int(segment_id)
        )

        data = [row.to_full_dict(self.current_user) for row in q.all()]

        demo = {
            "reviewId": "1063367226805911552",
            "cbid": "25583693309808304",
            "ccid": "69203747871449297",
            "guid": "854065516235",
            "userId": "409829755",
            "nickName": "约克君",
            "avatar": "https://qidian.gtimg.com/qd/images/ico/default_user.0.2.png",
            "segmentId": 5,
            "content": "好地方，不会饿[fn=18]",
            "status": 1,
            "createTime": "10-15 08:37:59",
            "createTimestamp": 1728952679,
            "updateTime": "2024-11-16 13:36:10",
            "quoteReviewId": "0",
            "quoteContent": "",
            "quoteGuid": "0",
            "quoteUserId": "0",
            "quoteNickName": "",
            "type": 2,
            "likeCount": 9,
            "dislikeCount": 0,
            "userLike": False,
            "userDislike": False,
            "isSelf": False,
            "essenceStatus": False,
            "riseStatus": False,
            "level": 948,
            "imagePre": "",
            "imageDetail": "",
            "rootReviewId": "1063367226805911552",
            "rootReviewReplyCount": 0,
            "ipAddress": "上海",
        }
        return {"err": "ok", "data": {"list": data}, "demo": demo}


class ReviewAdd(BaseHandler):
    """发表评论"""

    @js
    @auth
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        if not data:
            return {"err": "params.invalid", "msg": _("参数错误")}

        book_id = data['book_id']
        chapter_name = data['chapter_name']
        del data['chapter_name']

        # 查一下对应的章节信息是否存在
        name = ReviewChapter.clean_title(chapter_name)
        q = self.session.query(ReviewChapter)
        q = q.filter(ReviewChapter.book_id == book_id)
        q = q.filter(or_(ReviewChapter.title == name, ReviewChapter.alias == chapter_name))
        chapter = q.first()

        if chapter is None:
            chapter = ReviewChapter(book_id=book_id, title=name, alias=chapter_name)
            self.session.add(chapter)

        n = (
            self.session.query(Review)
            .filter(
                Review.book_id == book_id,
                Review.chapter_id == chapter.id,
                Review.segment_id == data["segment_id"],
            )
            .count()
        )

        review = Review(**data)
        if review.refer_text:
            review.refer_text = review.refer_text[:REFER_TEXT_MAX]
        review.level = n + 1
        review.chapter_id = chapter.id
        review.geo = self.request.remote_ip
        review.user_id = self.current_user.id
        review.create_time = datetime.datetime.now()
        review.update_time = review.create_time
        self.session.add(review)

        if review.quote_id:
            review.quote.update_time = datetime.datetime.now()
            self.session.add(review.quote)

        if review.root_id:
            review.root.update_time = datetime.datetime.now()
            self.session.add(review.root)

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": review.to_full_dict(self.current_user)}


class ReviewMe(BaseHandler):
    """获取「与我相关」的「最新」评论"""

    @js
    @auth
    def get(self):
        is_count = self.get_argument("count", "").strip() != ""
        last_read = self.current_user.last_read
        q = self.session.query(Review).filter(Review.user_id == self.current_user.id)
        if last_read:
            q = q.filter(Review.update_time > last_read)
        else:
            q = q.filter(Review.update_time > Review.create_time)

        if is_count:
            return {"err": "ok", "data": {"count": q.count()}}

        data = [row.to_full_dict(self.current_user) for row in q.all()]
        return {"err": "ok", "data": {"list": data}}


class ReviewGetBook(BaseHandler):
    """获取本书的信息（新书自动生成ID）"""

    @js
    def get(self):
        title = self.get_argument("title", "").strip().lower()

        if not title:
            return {"err": "params.invalid", "msg": _("参数错误")}

        row = self.session.query(ReviewBook).filter(ReviewBook.title == title).first()
        if row:
            return {"err": "ok", "data": row.to_dict()}

        row = self.session.query(ReviewBook).filter(ReviewBook.alias.like(f"%{title}%")).first()
        if row:
            return {"err": "ok", "data": row.to_dict()}

        row = ReviewBook()
        row.title = title
        row.alias = title
        self.session.add(row)

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": row.to_dict()}


class ReviewBookList(BaseHandler):
    """获取「整本书」的评论列表，支持「最新 / 热门」排序与分页"""

    @js
    def get(self):
        book_id = self.get_argument("book_id", "").strip()
        sort = self.get_argument("sort", "latest").strip()
        if not book_id or not book_id.isdigit():
            return {"err": "params.invalid", "msg": _("参数错误")}

        try:
            page = max(1, int(self.get_argument("page", "1")))
        except ValueError:
            page = 1
        try:
            size = min(50, max(1, int(self.get_argument("size", "20"))))
        except ValueError:
            size = 20

        # 整本书的「顶层文字评论」：排除点赞/踩，排除回复（只取 root）
        q = self.session.query(Review).filter(
            Review.book_id == int(book_id),
            Review.type == ReviewType.text,
            Review.root_id.is_(None),
        )

        total = q.count()

        if sort == "hot":
            q = q.order_by(Review.like_count.desc(), Review.create_time.desc())
        else:
            q = q.order_by(Review.create_time.desc())

        q = q.offset((page - 1) * size).limit(size)
        data = [row.to_full_dict(self.current_user) for row in q.all()]
        return {"err": "ok", "data": {"list": data, "total": total, "page": page, "size": size}}


class ReviewCommentExport(BaseHandler):
    """Export text comments incrementally for trusted integrations."""

    def write_json(self, status, payload):
        self.set_status(status)
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.write(payload)

    def get(self):
        configured_token = str(CONF.get("plugin_export_token", ""))
        authorization = self.request.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied_token = authorization[len(prefix):] if authorization.startswith(prefix) else ""
        if not configured_token or not hmac.compare_digest(supplied_token, configured_token):
            self.write_json(401, {"err": "auth.invalid", "msg": _("无效的访问令牌")})
            return

        try:
            cursor = max(0, int(self.get_argument("cursor", "0") or "0"))
            limit = min(200, max(1, int(self.get_argument("limit", "100") or "100")))
        except ValueError:
            self.write_json(400, {"err": "params.invalid", "msg": _("参数错误")})
            return

        rows = (
            self.session.query(Review)
            .filter(Review.type == ReviewType.text, Review.id > cursor)
            .order_by(Review.id.asc())
            .limit(limit)
            .all()
        )
        comments = []
        for row in rows:
            query = urllib.parse.urlencode(
                {"book_id": row.book_id, "chapter_id": row.chapter_id, "segment_id": row.segment_id}
            )
            comments.append(
                {
                    "id": str(row.id),
                    "book_id": str(row.book_id),
                    "chapter_id": str(row.chapter_id),
                    "segment_id": str(row.segment_id),
                    "content": row.content or "",
                    "summary": row.content or "",
                    "created_at": row.create_time.isoformat() if row.create_time else "",
                    "updated_at": row.update_time.isoformat() if row.update_time else "",
                    "url": "%s/api/review/list?%s" % (self.site_url, query),
                }
            )

        next_cursor = str(rows[-1].id if rows else cursor)
        self.write_json(200, {"err": "ok", "comments": comments, "next_cursor": next_cursor})


def routes():
    return [
        (r"/api/review/book", ReviewGetBook),
        (r"/api/review/book/list", ReviewBookList),
        (r"/api/review/summary", ReviewSummary),
        (r"/api/review/list", ReviewList),
        (r"/api/review/add", ReviewAdd),
        (r"/api/review/me", ReviewMe),
        (r"/api/v1/comments", ReviewCommentExport),
    ]
