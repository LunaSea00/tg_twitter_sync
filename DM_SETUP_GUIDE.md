# Twitter DM 功能设置指南

本指南将帮助您设置和使用 Twitter 私信 (DM) 功能。

## 前置条件

1. **Twitter Developer Account**: 您需要有一个 Twitter 开发者账户
2. **OAuth 2.0 应用**: 需要创建一个启用了 OAuth 2.0 的 Twitter 应用

## 步骤 1: 创建 Twitter OAuth 2.0 应用

1. 访问 [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. 创建一个新的应用或编辑现有应用
3. 在应用设置中启用 OAuth 2.0
4. 设置回调 URL 为: `http://localhost:8080/callback`
5. 确保应用有以下权限:
   - Read and write (读写推文)
   - Direct messages (私信权限)

## 步骤 2: 配置环境变量

在 `.env` 文件中设置以下变量:

```env
# OAuth 2.0 客户端凭据 (从 Twitter Developer Portal 获取)
TWITTER_CLIENT_ID=your_oauth2_client_id
TWITTER_OAUTH2_CLIENT_ID=your_oauth2_client_id
TWITTER_OAUTH2_CLIENT_SECRET=your_oauth2_client_secret

# 回调 URL (通常不需要修改)
TWITTER_REDIRECT_URI=http://localhost:8080/callback

# DM 监听配置
ENABLE_DM_MONITORING=true
DM_POLL_INTERVAL=60
DM_TARGET_CHAT_ID=your_telegram_user_id
```

## 步骤 3: 获取用户访问令牌

### 方法 1: 使用自动授权脚本 (推荐)

```bash
python tools/twitter_dm_client.py
```

这个脚本会：
- 自动打开浏览器进行授权
- 启动本地回调服务器
- 自动获取并保存访问令牌到 `.env` 文件

### 方法 2: 使用 OAuth 设置工具

```bash
python tools/oauth_setup.py
```

选择自动授权流程 (y) 或手动授权流程 (n)。

### 方法 3: 手动设置

如果自动流程失败，您可以：
1. 运行上述任一脚本
2. 选择手动授权流程
3. 复制授权链接到浏览器
4. 从回调 URL 中提取授权码
5. 将授权码输入到脚本中

## 步骤 4: 验证设置

运行 DM 客户端脚本来验证设置：

```bash
python tools/twitter_dm_client.py
```

如果设置正确，您应该看到：
- ✅ Twitter客户端初始化成功
- ✅ DM API权限测试成功
- 📋 找到的对话列表
- ✅ 测试消息发送成功

## 使用 API

### 获取对话列表

```python
conversations = await twitter_client.get_dm_conversations()
for conv in conversations['data']:
    print(f"对话ID: {conv['dm_conversation_id']}")
    print(f"参与者: {[p['username'] for p in conv['participants']]}")
```

### 发送私信

```python
# 向指定对话发送消息
result = await twitter_client.send_dm_by_conversation_id(
    conversation_id="conversation_id_here",
    text="Hello from bot!"
)

# 向用户发送私信 (自动创建对话)
result = await twitter_client.send_dm_to_user(
    username_or_id="username_or_user_id",
    text="Hello!"
)
```

### 获取 DM 事件

```python
# 获取所有最近的 DM 事件
events = await twitter_client.get_all_dm_events(max_results=50)

# 获取与特定用户的对话
user_dm = await twitter_client.get_dm_with_user(user_id="123456789")

# 获取特定对话的消息
conv_messages = await twitter_client.get_dm_conversation_events(
    conversation_id="conversation_id_here"
)
```

## 故障排除

### 常见错误

1. **"没有权限访问DM API"**
   - 确保应用已启用私信权限
   - 确保用户已授权您的应用访问私信

2. **"授权失败"**
   - 检查 CLIENT_ID 是否正确
   - 确保回调 URL 设置正确
   - 尝试重新创建应用凭据

3. **"端口被占用"**
   - 确保端口 8080 没有被其他程序使用
   - 可以在脚本中修改端口号

### 检查配置

运行以下命令检查您的配置：

```bash
python -c "
from src.config.settings import get_config
config = get_config()
print('Client ID:', bool(config.twitter_oauth2_client_id))
print('User Token:', bool(config.twitter_user_access_token))
print('DM Monitoring:', config.enable_dm_monitoring)
"
```

## 安全注意事项

1. **保护您的凭据**: 不要将 `.env` 文件提交到版本控制
2. **定期刷新令牌**: 访问令牌可能会过期，使用刷新令牌自动更新
3. **最小权限原则**: 只请求您需要的权限

## 集成到现有项目

DM 功能已完全集成到现有的机器人架构中：

- **监听模式**: 自动监听新私信并转发到 Telegram
- **手动发送**: 通过 Telegram 命令发送私信
- **API 访问**: 程序化访问所有 DM 功能

启动主程序时，如果启用了 DM 监听，机器人会自动开始监听新私信：

```bash
python main.py
```