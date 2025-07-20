# 🤖 Twitter Bot - Telegram到Twitter转发机器人

一个功能强大的Telegram机器人，可以将消息自动转发到Twitter，采用模块化架构设计，易于维护和扩展。

## ✨ 功能特性

- 📝 将Telegram消息自动转发到Twitter
- 🖼️ 图片推文发送（自动优化压缩）
- 🔄 Twitter私信接收和转发（隔离式设计）
- 🔐 用户授权验证
- 📊 消息统计和长度检查
- 🔍 服务状态监控
- 🚀 健康检查端点
- 🐳 Docker化部署
- 🛡️ 完善的错误处理
- 📦 模块化架构设计
- ⚡ 故障隔离：DM功能异常不影响Bot正常运行
- 🎛️ 按需启用：使用 /dm 命令激活私信监听

## 🏗️ 项目架构

```
TGBot/
├── src/
│   ├── config/          # 配置管理
│   │   └── settings.py
│   ├── twitter/         # Twitter API处理
│   │   └── client.py
│   ├── telegram/        # Telegram Bot处理
│   │   ├── bot.py
│   │   └── handlers.py
│   ├── auth/           # 用户授权
│   │   └── service.py
│   ├── dm/             # 私信功能（隔离模块）
│   │   ├── manager.py   # DM管理器
│   │   ├── monitor.py   # 私信监听
│   │   ├── processor.py # 私信处理
│   │   ├── notifier.py  # 通知服务
│   │   └── store.py     # 数据存储
│   └── utils/          # 工具模块
│       ├── exceptions.py
│       ├── error_handler.py
│       ├── logger.py
│       └── health_server.py
├── main.py             # 主程序入口
├── bot.py              # 兼容性入口
├── start.sh            # 启动脚本
├── deploy.sh           # 部署脚本
├── docker-compose.yml  # Docker Compose配置
└── Dockerfile          # Docker镜像配置
```

## 🚀 快速开始

### 环境要求

- Python 3.7+
- pip或pipx
- Docker (可选)

### 1. 克隆项目

```bash
git clone <repository-url>
cd TGBot
```

### 2. 配置环境

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的API密钥
```

### 3. 运行机器人

```bash
# 使用启动脚本（推荐）
./start.sh

# 或直接运行
python main.py
```

## ⚙️ 环境变量配置

| 变量名 | 描述 | 必需 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram机器人令牌 | ✅ |
| `TWITTER_API_KEY` | Twitter API密钥 | ✅ |
| `TWITTER_API_SECRET` | Twitter API密钥 | ✅ |
| `TWITTER_ACCESS_TOKEN` | Twitter访问令牌 | ✅ |
| `TWITTER_ACCESS_TOKEN_SECRET` | Twitter访问令牌密钥 | ✅ |
| `TWITTER_BEARER_TOKEN` | Twitter Bearer令牌 | ✅ |
| `AUTHORIZED_USER_ID` | 授权用户的Telegram ID | ✅ |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | ❌ (默认: INFO) |
| `HEALTH_PORT` | 健康检查端口 | ❌ (默认: 8000) |
| `TWEET_MAX_LENGTH` | 推文最大长度 | ❌ (默认: 280) |

## 🔧 API密钥获取

### Telegram Bot Token

1. 在Telegram中搜索 @BotFather
2. 发送 `/newbot` 创建新机器人
3. 按提示设置机器人名称和用户名
4. 保存获得的Bot Token

### Twitter API密钥
1. 访问 [Twitter Developer Portal](https://developer.twitter.com/)
2. **创建项目**：
   - 点击"Projects & Apps" → "Overview"
   - 点击"Create Project"
   - 填写项目信息
3. **创建/关联应用**：
   - 在项目中点击"Add App"
   - 创建新应用或关联现有应用
4. **配置App权限**：
   - App permissions设置为"Read and write and Direct message"
   - Type of App选择"Web App"
5. **获取所需密钥**：
   - API Key
   - API Secret
   - Access Token (权限修改后重新生成)
   - Access Token Secret (权限修改后重新生成)
   - **Bearer Token** (在项目的Keys and tokens页面生成)

### 获取Telegram用户ID

发送消息给 @userinfobot 或 @RawDataBot 获取你的用户ID。

### 配置Twitter私信接收（可选）

如果需要接收Twitter私信：
1. 在Twitter Developer Portal中配置webhook URL：
   - Webhook URL: `https://your-domain.com/webhook/twitter`
   - 设置webhook secret并添加到环境变量
2. 确保你的应用有私信权限
3. 测试webhook连接

## 🐳 Docker部署

### 使用Docker Compose（推荐）

```bash
# 构建并启动
./deploy.sh

# 或手动操作
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 使用Docker

```bash
# 构建镜像
docker build -t twitter-bot .

# 运行容器
docker run -d \
  --name twitter-bot \
  --env-file .env \
  -p 8000:8000 \
  twitter-bot
```

## 📱 使用方法

### 基本命令

- `/start` - 开始使用机器人
- `/help` - 显示帮助信息
- `/status` - 检查服务状态
- `/stats <消息>` - 查看消息统计信息
- `/dm` - 按需启用私信监听功能

### 发送推文

1. 与你的机器人开始对话
2. 发送 `/start` 命令开始
3. 直接发送文本消息即可发布到Twitter
4. 发送图片（可带文字描述），机器人会上传图片到Twitter
5. 机器人会返回推文链接和详细信息

### 功能特点

- ✅ 支持中英文混合内容
- ✅ 文本推文发送
- ✅ 图片推文发送（自动优化压缩）
- ✅ Twitter私信接收和转发到Telegram（隔离式设计）
- ✅ 自动验证消息长度
- ✅ 实时状态反馈
- ✅ 错误处理和重试
- ✅ 推文链接生成
- ✅ DM功能故障不影响主要功能
- ✅ 按需启用私信监听（/dm 命令）

## 🔍 健康检查

机器人提供健康检查端点：

```bash
# 检查服务状态
curl http://localhost:8000/health
curl http://localhost:8000/
```

## 📊 监控和日志

### 查看日志

```bash
# Docker Compose
docker-compose logs -f

# Docker
docker logs -f twitter-bot

# 直接运行
tail -f logs/twitter-bot.log
```

### 日志级别

- `DEBUG`: 详细调试信息
- `INFO`: 一般信息（默认）
- `WARNING`: 警告信息
- `ERROR`: 错误信息

## 🛠️ 开发指南

### 添加新功能

1. 在对应的模块中添加功能
2. 更新处理器和路由
3. 添加相应的测试
4. 更新文档

### 模块说明

- **config**: 配置管理和验证
- **twitter**: Twitter API交互
- **telegram**: Telegram Bot处理
- **auth**: 用户授权验证
- **dm**: 私信功能（隔离模块）- DM管理、监听、处理和通知
- **utils**: 通用工具和异常处理

## ❗ 故障排除

### 常见问题

1. **配置错误**: 检查 `.env` 文件中的API密钥
2. **网络问题**: 确保服务器可以访问Twitter和Telegram API
3. **权限问题**: 验证Twitter API权限和Telegram机器人权限
4. **依赖问题**: 重新安装依赖包
5. **私信功能问题**: 检查webhook配置和公网访问，私信API失败不会影响推文发送功能

### 获取帮助

```bash
# 检查配置
python -c "from src.config.settings import get_config; print('配置正常')"

# 测试Twitter连接
python -c "from src.config.settings import get_config; from src.twitter.client import TwitterClient; import asyncio; asyncio.run(TwitterClient(get_config().twitter_credentials).test_connection())"
```

## 🚀 部署到云平台

支持任何支持Docker的云平台部署。

## 📄 许可证

MIT License

## 📝 注意事项

- 消息长度不能超过280字符
- 图片会自动压缩优化以符合Twitter要求
- 确保Twitter API有发推和私信权限
- 私信功能需要配置webhook和公网访问
- 私信API失败不会影响推文发送功能
- 使用 `/dm` 命令可按需启用私信监听
- 保护好你的API密钥
- 请确保遵守Twitter和Telegram的使用条款和API限制
