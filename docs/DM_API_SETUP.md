# Twitter DM API 设置指南

本指南将帮助你配置 Twitter DM API，使用官方的 OAuth 2.0 PKCE 授权流程。

## 📋 前提条件

1. **Twitter Developer Account**: 确保你有 Twitter 开发者账户
2. **App with Project**: 你的 App 必须附加到一个 Project（不是独立的 App）
3. **API 权限**: 确保启用了以下权限：
   - `dm.read` - 读取私信
   - `dm.write` - 发送私信
   - `tweet.read` - 读取推文
   - `users.read` - 读取用户信息
   - `offline.access` - 获取刷新令牌

## 🔧 配置步骤

### 1. Twitter Developer Portal 设置

1. 访问 [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. 创建或选择一个 **Project**
3. 在 Project 中创建或选择一个 **App**
4. 在 App 设置中：
   - 启用 OAuth 2.0
   - 设置 Callback URL: `http://localhost:8080/callback`
   - 启用所需的 scopes（见上方列表）
   - 获取 **Client ID** 和 **Client Secret**

### 2. 环境配置

在 `.env` 文件中添加 OAuth 2.0 配置：

```bash
# OAuth 2.0 Configuration (for DM API)
TWITTER_OAUTH2_CLIENT_ID=你的Client_ID
TWITTER_OAUTH2_CLIENT_SECRET=你的Client_Secret

# OAuth 2.0 User Context Access Token (for DM API)
TWITTER_USER_ACCESS_TOKEN=
TWITTER_USER_REFRESH_TOKEN=

# OAuth 2.0 PKCE Configuration
TWITTER_REDIRECT_URI=http://localhost:8080/callback
```

### 3. 获取用户访问令牌

运行授权设置工具：

```bash
python tools/oauth_setup.py
```

按照脚本提示：

1. 在浏览器中打开授权链接
2. 登录你的 Twitter 账户
3. 授权应用访问你的账户
4. 从重定向 URL 中复制授权码
5. 将授权码输入到脚本中

脚本会自动获取并保存访问令牌到 `.env` 文件。

## 📡 API 使用方法

### 获取私信

```python
# 1. 获取所有 DM 事件（过去30天）
result = await twitter_client.get_all_dm_events(max_results=50)
messages = result['data']
meta = result['meta']  # 包含分页信息

# 2. 获取与特定用户的对话
result = await twitter_client.get_dm_with_user('用户ID', max_results=50)

# 3. 获取特定对话的消息
result = await twitter_client.get_dm_conversation_events('对话ID', max_results=50)

# 向后兼容的方法
messages = await twitter_client.get_direct_messages(max_results=50)
```

### 发送私信

```python
# 发送私信到指定对话
result = await twitter_client.send_direct_message('对话ID', '消息内容')

# 创建新对话并发送消息
result = await twitter_client.create_dm_conversation('用户ID', '消息内容')

# 发送带媒体的私信
result = await twitter_client.send_direct_message('对话ID', '消息内容', media_id='媒体ID')
```

## 🔄 令牌刷新

如果访问令牌过期，可以使用刷新令牌自动刷新：

```python
if twitter_client.oauth2_handler and twitter_client.credentials.get('user_refresh_token'):
    new_tokens = twitter_client.oauth2_handler.refresh_access_token(
        twitter_client.credentials['user_refresh_token']
    )
    # 更新 .env 文件中的令牌
```

## ⚠️ 重要注意事项

1. **用户上下文**: DM API 只能使用用户上下文的访问令牌，不能使用应用专用的 Bearer Token
2. **权限要求**: 确保用户已授权必要的 scopes
3. **频率限制**: DM API 有频率限制（每15分钟300次请求）
4. **数据范围**: 只能获取过去30天内的私信数据
5. **令牌安全**: 妥善保管访问令牌和刷新令牌

## 🛠 故障排除

### 403 Forbidden
- 检查 App 是否附加到 Project
- 确认已启用正确的 scopes
- 验证用户已完成授权流程

### 401 Unauthorized
- 检查访问令牌是否有效
- 确认令牌未过期
- 验证 Client ID 和 Client Secret

### 网络错误
- 检查网络连接
- 确认防火墙设置
- 验证 API 端点 URL

## 📚 参考资料

- [Twitter API v2 DM Documentation](https://developer.twitter.com/en/docs/twitter-api/direct-messages)
- [OAuth 2.0 PKCE Flow](https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code)
- [API Rate Limits](https://developer.twitter.com/en/docs/twitter-api/rate-limits)