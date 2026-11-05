# DeepL 自动批量翻译

## 第一次配置

1. 从 [DeepL API 官方申请入口](https://www.deepl.com/en/signup?cta=checkout&is_api=true&productId=api-developer) 注册 API 服务；具体可选套餐、价格和注册要求以你所在地区页面为准。普通的网页翻译订阅与开发者 API 服务不同。
2. 开通后，在 [账户的 API Keys 页面](https://www.deepl.com/your-account/keys) 创建或查看密钥。
3. 双击 `D:\gallery-dl\配置DeepL.cmd`，把密钥粘贴到该窗口。输入不显示；回车后只检查连接和用量，通过后保存至本地 `tools/deepl.local.json`。
4. 双击 `测试DeepL.cmd`：翻译三段固定日语样例并显示耗时。这会消耗样例对应的 API 字符额度，不修改已有推文。

没有密钥时，可以照常抓取原文，缺少的译文以后用 `补译中文.cmd` 补齐。不要把密钥粘贴到聊天中；包含密钥的本地配置文件不要对外分享。

## 日常使用

- `补新.cmd`：沿用账号菜单，下载媒体、整理图片后，自动归档对应原创推文并翻译缺少译文的正文。
- `推文归档.cmd`：只关联已有图片、补抓原文和翻译，不下载新媒体。
- `补译中文.cmd`：只处理已有正文的缺失译文，不访问 X；支持断点继续。
- `推文归档.html`：离线阅读，页面不包含密钥，也不直接调用 DeepL。

已有的 Codex 中文译文保留，不会重新收费翻译。相同原文尽量复用本地译文；纯表情、链接、话题标签和已是中文的内容，无需调用翻译接口。

## 批量设置

`tools/deepl.local.json` 中可调整：

| 设置 | 默认值 | 含义 |
|---|---:|---|
| `batch_size` | 25 | 每批最多提交的不同正文数 |
| `workers` | 3 | 同时进行的请求数，允许 1—5 |
| `max_characters_per_run` | 10000 | 每次运行最多安排的原文字符数；到上限后下次继续 |
| `timeout_seconds` | 30 | 单次请求超时 |
| `max_retries` | 3 | 限流或临时服务故障时的最大重试次数 |
| `plan` | `auto` | 自动识别端点，也可设为 `free` 或 `pro` |
| `protected_terms` | 人名、乐队名列表 | 希望按原样保留的专有名词 |
| `enabled` | `true` | 是否自动调用 DeepL |

也支持 `DEEPL_AUTH_KEY` 环境变量，优先于本地文件。密钥只发往官方 API 的请求头，不放在网页、推文文件或日志中。翻译请求仅包含正文与格式保护标记，不包含图片、X 登录 cookie 或完整账号资料。

脚本先检查账户和密钥额度，再安排批次。每个批次成功后立即保存；失败批次不会写入假译文，重跑只处理仍缺译文的记录。HTTP 429、529、部分 5xx 或网络超时会有限次退避重试；403 和 456 会停止继续发送新批次，已经完成的译文保留。

## 常用命令

```bat
:: 预览待译数量和字符数，不联网
补译中文.cmd --translation-preview

:: 少量补译，最多处理五段不同原文
补译中文.cmd --translation-limit 5

:: 只处理账号表中的第一个账号
补译中文.cmd --index 1

:: 本次只抓原文，跳过自动翻译
推文归档.cmd --no-translate
```

后续新增推文会自动进入翻译流程。原文若发生变化，旧译文会失效，等待重新翻译。实际速度和费用取决于文本长度、网络、套餐和服务限额；`测试DeepL.cmd` 用于本机实测。

## 官方文档

- [API 认证与端点](https://developers.deepl.com/docs/getting-started/auth)
- [文本翻译接口](https://developers.deepl.com/api-reference/translate/request-translation)
- [用量及额度](https://developers.deepl.com/api-reference/usage-and-quota/check-usage-and-limits)
- [错误与重试](https://developers.deepl.com/docs/best-practices/error-handling)
