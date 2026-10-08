#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import hmac
import urllib.parse
from gettext import gettext as _

import tornado.escape
import loader
from handlers.base import BaseHandler, auth, js
from models import Review, ReviewBook, ReviewChapter, ReviewType, ReviewVote

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
    """发表评论或回复。只接受下列字段，其他字段（如 refer_text）忽略。"""

    @js
    @auth
    def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict) or not data.get("book_id") or not str(data.get("content") or "").strip():
            return {"err": "params.invalid", "msg": _("参数错误")}

        book_id = int(data["book_id"])
        root = None
        if data.get("root_id"):
            # 回复：挂在同一本书的顶层评论下，位置跟随主评论。
            root = self.session.query(Review).get(int(data["root_id"]))
            if root is None or root.book_id != book_id or root.root_id:
                return {"err": "review.not_found", "msg": _("要回复的评论不存在")}
            quote_id = int(data.get("quote_id") or root.id)
            quote = self.session.query(Review).get(quote_id)
            if quote is None or (quote.id != root.id and quote.root_id != root.id):
                return {"err": "review.not_found", "msg": _("要回复的评论不存在")}

        if root is None:
            chapter_name = str(data.get("chapter_name") or "")
            name = ReviewChapter.clean_title(chapter_name)
            q = self.session.query(ReviewChapter)
            q = q.filter(ReviewChapter.book_id == book_id)
            q = q.filter(or_(ReviewChapter.title == name, ReviewChapter.alias == chapter_name))
            chapter = q.first()
            if chapter is None:
                chapter = ReviewChapter(book_id=book_id, title=name, alias=chapter_name)
                self.session.add(chapter)
                self.session.flush()
            chapter_id, segment_id, cfi = chapter.id, int(data.get("segment_id") or 0), str(data.get("cfi") or "")
        else:
            chapter_id, segment_id, cfi = root.chapter_id, root.segment_id, root.cfi

        now = datetime.datetime.now()
        review = Review(
            book_id=book_id,
            chapter_id=chapter_id,
            segment_id=segment_id,
            cfi=cfi[:255],
            type=1,
            kind="book_comment" if data.get("kind") == "book_comment" and root is None else "note",
            content=str(data["content"])[:1024],
            refer_text=str(data.get("refer_text") or "")[:REFER_TEXT_MAX],
            geo=self.request.remote_ip,
            user_id=self.current_user.id,
            create_time=now,
            update_time=now,
            root_id=root.id if root else None,
            quote_id=quote_id if root else None,
        )
        review.level = (
            self.session.query(Review)
            .filter(Review.book_id == book_id, Review.chapter_id == chapter_id, Review.segment_id == segment_id)
            .count()
            + 1
        )
        self.session.add(review)
        if root is not None:
            root.update_time = now
            if quote.id != root.id:
                quote.update_time = now

        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": review.to_full_dict(self.current_user)}


class ReviewOwnedMixin:
    def _owned_review(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
            review = self.session.query(Review).get(int(data.get("review_id")))
        except (TypeError, ValueError, AttributeError):
            return None, None
        if review is None or review.user_id != self.current_user.id:
            return None, data
        return review, data


class ReviewUpdate(ReviewOwnedMixin, BaseHandler):
    """修改自己的评论内容。"""

    @js
    @auth
    def post(self):
        review, data = self._owned_review()
        if review is None:
            return {"err": "review.not_found", "msg": _("评论不存在")}
        content = str((data or {}).get("content") or "").strip()
        if not content:
            return {"err": "params.invalid", "msg": _("参数错误")}
        review.content = content[:1024]
        review.update_time = datetime.datetime.now()
        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": review.to_full_dict(self.current_user)}


class ReviewDelete(ReviewOwnedMixin, BaseHandler):
    """删除自己的评论：主评论连同全部回复，回复连同回复它的回复；投票一并删除。"""

    @js
    @auth
    def post(self):
        review, _data = self._owned_review()
        if review is None:
            return {"err": "review.not_found", "msg": _("评论不存在")}
        if review.root_id:
            # 收集直接或间接回复这条回复的记录。
            replies = self.session.query(Review).filter(Review.root_id == review.root_id).all()
            ids, changed = {review.id}, True
            while changed:
                changed = False
                for item in replies:
                    if item.id not in ids and item.quote_id in ids:
                        ids.add(item.id)
                        changed = True
        else:
            ids = {review.id} | {item.id for item in self.session.query(Review.id).filter(Review.root_id == review.id)}
        self.session.query(ReviewVote).filter(ReviewVote.review_id.in_(ids)).delete(synchronize_session=False)
        # 先断开回复之间的引用，再删除，避免外键顺序问题。
        self.session.query(Review).filter(Review.id.in_(ids)).update(
            {Review.quote_id: None, Review.root_id: None}, synchronize_session=False
        )
        self.session.query(Review).filter(Review.id.in_(ids)).delete(synchronize_session=False)
        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {"err": "ok", "data": {"deleted": len(ids)}}


class ReviewVoteHandler(BaseHandler):
    """赞（1）、踩（-1）或取消（0）。每人每条一票，计数随之更新。"""

    @js
    @auth
    def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
            review = self.session.query(Review).get(int(data.get("review_id")))
            value = int(data.get("value"))
        except (TypeError, ValueError, AttributeError):
            return {"err": "params.invalid", "msg": _("参数错误")}
        if review is None:
            return {"err": "review.not_found", "msg": _("评论不存在")}
        if value not in (1, -1, 0):
            return {"err": "params.invalid", "msg": _("参数错误")}
        user_id = self.current_user.id
        vote = self.session.query(ReviewVote).filter(ReviewVote.review_id == review.id, ReviewVote.user_id == user_id).first()
        if value == 0:
            if vote:
                self.session.delete(vote)
        elif vote:
            vote.value = value
        else:
            self.session.add(ReviewVote(review_id=review.id, user_id=user_id, value=value))
        self.session.flush()
        counts = dict(
            self.session.query(ReviewVote.value, func.count(ReviewVote.id))
            .filter(ReviewVote.review_id == review.id)
            .group_by(ReviewVote.value)
            .all()
        )
        review.like_count = counts.get(1, 0)
        review.dislike_count = counts.get(-1, 0)
        if not self.commit():
            return {"err": "db.error", "msg": _(u"数据库操作异常，请重试")}
        return {
            "err": "ok",
            "data": {"likeCount": review.like_count, "dislikeCount": review.dislike_count, "userVote": value},
        }


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
        (r"/api/review/update", ReviewUpdate),
        (r"/api/review/delete", ReviewDelete),
        (r"/api/review/vote", ReviewVoteHandler),
        (r"/api/review/me", ReviewMe),
        (r"/api/v1/comments", ReviewCommentExport),
    ]
