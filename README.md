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
