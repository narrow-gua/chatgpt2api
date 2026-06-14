# ChatGPT2API 部署接口文档

本文档记录当前部署在新服务器上的管理页面和 API 调用方式。

## 基本信息

| 项目 | 值 |
|:--|:--|
| 服务地址 | `http://45.147.167.43:3000` |
| 管理页面 | `http://45.147.167.43:3000/accounts/` |
| 配置页面 | `http://45.147.167.43:3000/settings/` |
| 认证方式 | `Authorization: Bearer <AUTH_KEY>` |
| 当前部署目录 | `/opt/chatgpt2api` |

`<AUTH_KEY>` 为管理密钥，请从当前 `config.json` 的 `auth-key` 读取，不要提交到公开仓库或发给第三方。

## 登录验证

```bash
curl -X POST http://45.147.167.43:3000/auth/login \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

成功返回：

```json
{
  "ok": true,
  "version": "1.4.1",
  "role": "admin",
  "subject_id": "admin",
  "name": "管理员"
}
```

## 模型列表

模型列表由后端动态从 ChatGPT 获取，不要在客户端写死模型 ID。

```bash
curl http://45.147.167.43:3000/v1/models \
  -H "Authorization: Bearer <AUTH_KEY>"
```

返回格式：

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-image-2",
      "object": "model",
      "created": 0,
      "owned_by": "chatgpt2api",
      "permission": [],
      "root": "gpt-image-2",
      "parent": null
    }
  ]
}
```

## 文本对话

兼容 OpenAI `POST /v1/chat/completions`。

```bash
curl http://45.147.167.43:3000/v1/chat/completions \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "messages": [
      {"role": "user", "content": "你是什么模型"}
    ],
    "stream": false
  }'
```

## 文生图

支持，接口为 OpenAI 兼容的 `POST /v1/images/generations`。

```bash
curl http://45.147.167.43:3000/v1/images/generations \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一张写实风格的未来城市夜景，霓虹灯，雨后街道",
    "n": 1,
    "quality": "auto",
    "response_format": "b64_json"
  }'
```

主要字段：

| 字段 | 说明 |
|:--|:--|
| `model` | 图片模型，建议从 `/v1/models` 动态获取 |
| `prompt` | 文生图提示词，必填 |
| `n` | 生成数量，范围 `1-4` |
| `size` | 可选，图片尺寸 |
| `quality` | 可选，默认 `auto` |
| `response_format` | 默认 `b64_json` |

返回格式：

```json
{
  "created": 1781228804,
  "data": [
    {
      "b64_json": "...",
      "revised_prompt": "..."
    }
  ]
}
```

## 图生图

支持，接口为 OpenAI 兼容的 `POST /v1/images/edits`。可用 multipart 上传本地图片，也可用 JSON 传图片 URL。

### 上传本地图片

```bash
curl http://45.147.167.43:3000/v1/images/edits \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -F "model=gpt-image-2" \
  -F "prompt=把这张图改成赛博朋克夜景风格，保留主体构图" \
  -F "n=1" \
  -F "quality=auto" \
  -F "image=@./input.png"
```

### 多图参考

```bash
curl http://45.147.167.43:3000/v1/images/edits \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -F "model=gpt-image-2" \
  -F "prompt=参考两张图片，生成统一风格的产品宣传图" \
  -F "n=1" \
  -F "image=@./reference-1.png" \
  -F "image=@./reference-2.png"
```

### 图片 URL

```bash
curl http://45.147.167.43:3000/v1/images/edits \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "把这张图改成赛博朋克夜景风格，保留主体构图",
    "n": 1,
    "quality": "auto",
    "images": [
      {"image_url": "https://example.com/input.png"}
    ]
  }'
```

主要字段：

| 字段 | 说明 |
|:--|:--|
| `model` | 图片模型，建议从 `/v1/models` 动态获取 |
| `prompt` | 图生图/图片编辑提示词，必填 |
| `image` | multipart 上传字段，可重复传多张 |
| `images` | JSON 模式下的图片输入数组 |
| `n` | 生成数量，范围 `1-4` |
| `size` | 可选，图片尺寸 |
| `quality` | 可选，默认 `auto` |

## Responses 接口

兼容 `POST /v1/responses`。

```bash
curl http://45.147.167.43:3000/v1/responses \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "input": "写一段中文产品介绍"
  }'
```

## Codex 文本代理

当前额外提供两个 Codex 文本代理接口。它们只使用账号池中 `source_type=codex` 的账号，适合验证和消耗 Codex 文本/编程会话额度。

注意：这是 MVP 代理层，不等同于完整官方 Codex 仓库任务系统；不会执行本地 shell、不会拉仓库、不会代理官方 Codex 沙箱工具。Codex 额度目前只能返回账号池可用状态，精准剩余额度取决于上游是否暴露稳定字段。

### Codex Responses

```bash
curl http://45.147.167.43:3000/codex/responses \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codex",
    "input": "写一个 Python 函数，判断字符串是否是回文。"
  }'
```

流式：

```bash
curl http://45.147.167.43:3000/codex/responses \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codex",
    "input": "解释这段代码可能的问题。",
    "stream": true
  }'
```

### Codex Chat Completions

```bash
curl http://45.147.167.43:3000/codex/chat/completions \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codex",
    "messages": [
      {"role": "user", "content": "用 Go 写一个 HTTP health check handler。"}
    ],
    "stream": false
  }'
```

### Codex 账号池状态

```bash
curl http://45.147.167.43:3000/codex/accounts \
  -H "Authorization: Bearer <AUTH_KEY>"
```

返回字段说明：

| 字段 | 说明 |
|:--|:--|
| `total` | Codex 来源账号数量 |
| `available` | 本地状态可用的 Codex 账号数量 |
| `items[].status` | 本地账号状态，可能为 `正常`、`限流`、`异常`、`禁用` |
| `items[].quota_state` | 当前为本地估算状态，不代表官方精准剩余额度 |
| `items[].token_prefix` | 脱敏 token 前缀，便于排查 |

## Anthropic Messages 接口

兼容 `POST /v1/messages`，支持使用 `Authorization: Bearer <AUTH_KEY>` 或 `x-api-key: <AUTH_KEY>`。

```bash
curl http://45.147.167.43:3000/v1/messages \
  -H "x-api-key: <AUTH_KEY>" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "max_tokens": 512,
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ]
  }'
```

## 账号池管理 API

以下接口都需要管理员密钥。

### 获取账号列表

```bash
curl http://45.147.167.43:3000/api/accounts \
  -H "Authorization: Bearer <AUTH_KEY>"
```

### 添加账号

```bash
curl -X POST http://45.147.167.43:3000/api/accounts \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["<CHATGPT_ACCESS_TOKEN>"],
    "accounts": []
  }'
```

也可以传完整账号对象到 `accounts`，用于导入包含 refresh token / id token 的账号数据。

### 删除账号

```bash
curl -X DELETE http://45.147.167.43:3000/api/accounts \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "tokens": ["<CHATGPT_ACCESS_TOKEN>"]
  }'
```

### 更新账号

```bash
curl -X POST http://45.147.167.43:3000/api/accounts/update \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "access_token": "<CHATGPT_ACCESS_TOKEN>",
    "status": "正常",
    "quota": 10,
    "proxy": ""
  }'
```

可更新字段：

| 字段 | 说明 |
|:--|:--|
| `type` | 账号类型 |
| `status` | `正常`、`限流`、`异常`、`禁用` |
| `quota` | 当前额度 |
| `proxy` | 单账号代理 |

### 刷新账号状态

不传 `access_tokens` 时会刷新全部账号。

```bash
curl -X POST http://45.147.167.43:3000/api/accounts/refresh \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "access_tokens": ["<CHATGPT_ACCESS_TOKEN>"]
  }'
```

返回：

```json
{"progress_id": "..."}
```

查询进度：

```bash
curl http://45.147.167.43:3000/api/accounts/refresh/progress/<PROGRESS_ID> \
  -H "Authorization: Bearer <AUTH_KEY>"
```

### 重新登录账号

```bash
curl -X POST http://45.147.167.43:3000/api/accounts/re-login \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "access_tokens": ["<CHATGPT_ACCESS_TOKEN>"]
  }'
```

查询进度：

```bash
curl http://45.147.167.43:3000/api/accounts/re-login/progress/<PROGRESS_ID> \
  -H "Authorization: Bearer <AUTH_KEY>"
```

### OAuth 添加账号

开始 OAuth 登录：

```bash
curl -X POST http://45.147.167.43:3000/api/accounts/oauth/start \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"email_hint": ""}'
```

完成 OAuth 登录：

```bash
curl -X POST http://45.147.167.43:3000/api/accounts/oauth/finish \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<SESSION_ID>",
    "callback": "<CALLBACK_URL_OR_CODE>"
  }'
```

## 配置 API

获取配置：

```bash
curl http://45.147.167.43:3000/api/settings \
  -H "Authorization: Bearer <AUTH_KEY>"
```

更新配置：

```bash
curl -X POST http://45.147.167.43:3000/api/settings \
  -H "Authorization: Bearer <AUTH_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "proxy": "",
    "base_url": "",
    "refresh_account_interval_minute": 60,
    "image_retention_days": 15
  }'
```

## 注意事项

- 管理密钥权限很高，不要写入前端仓库、公开文档、日志或第三方配置中心。
- 模型 ID 应以 `/v1/models` 的实时返回为准。
- 文生图和图生图都支持，推荐优先使用 `gpt-image-2`，实际可用模型以当前账号池和上游返回为准。
- Codex 文本接口只会选择 `source_type=codex` 的账号；如果返回 `no available codex account`，先在账号池导入 Codex 认证 JSON。
- 如果接口返回 `bootstrap failed: status=403`，通常是服务器所在地区访问 ChatGPT 上游被拦截或风控，需要更换出口或配置代理。
- 图片返回默认是 `b64_json`，客户端需要自行解码保存为图片文件。
