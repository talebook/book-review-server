# book-review-server
章评服务

## Talebook 插件导出

设置环境变量 `PLUGIN_EXPORT_TOKEN` 后，Talebook 可以通过只读接口增量导入文字章评：

```http
GET /api/v1/comments?cursor=0&limit=100
Authorization: Bearer <PLUGIN_EXPORT_TOKEN>
```

- `cursor` 是上次返回的 `next_cursor`，默认为 `0`。
- `limit` 默认为 `100`，最大为 `200`。
- 当 token 未配置或不匹配时，接口返回 HTTP 401。
- 导出以章评 ID 为增量游标，包含新增文字章评；现阶段不表示已有章评的编辑或删除。

## 与 Talebook 同步

Talebook 是评论的权威存储，BRS 保存它同步过来的公开评论副本：

- `POST /api/review/add`：新增评论或回复（`root_id` 为主评论，`quote_id` 为回复对象；`kind` 为 `note` 或 `book_comment`）。
- `POST /api/review/update`：作者修改评论内容（`review_id`、`content`）。
- `POST /api/review/delete`：作者删除评论，连同其下回复与投票（`review_id`）。
- `POST /api/review/vote`：赞（1）、踩（-1）或取消（0），每人每条一票（`review_id`、`value`）。

以上接口均需先 `POST /api/user/sign_in` 登录。

升级到这一版本时，评论结构有变化且旧数据不迁移，需要执行一次 `python3 main.py --reset_reviews` 清空评论与投票并重建表。
