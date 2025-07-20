# 兼容性文件 - 重定向到main.py
# 保持向后兼容，同时集成DM隔离功能

import sys
import os
import asyncio

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    """主入口函数，优先使用高级架构，降级到兼容模式"""
    try:
        # 尝试使用高级架构（OAuth2 PKCE）
        from main import main as advanced_main
        asyncio.run(advanced_main())
    except ImportError as e:
        print(f"⚠️ 高级架构不可用，降级到兼容模式: {e}")
        # 降级到兼容模式
        bot = TwitterBot()
        asyncio.run(bot.run())
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

class TwitterBot:
    """兼容模式的TwitterBot实现，包含DM功能"""
    
    def __init__(self):
        import os
        import logging
        import tweepy
        from dotenv import load_dotenv
        
        load_dotenv()
        
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
        self.logger = logging.getLogger(__name__)
        
        # 基本配置
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.twitter_api_key = os.getenv('TWITTER_API_KEY')
        self.twitter_api_secret = os.getenv('TWITTER_API_SECRET')
        self.twitter_access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.twitter_access_token_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
        self.twitter_bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        self.authorized_user_id = os.getenv('AUTHORIZED_USER_ID')
        self.app_url = os.getenv('APP_URL')
        self.webhook_secret = os.getenv('TWITTER_WEBHOOK_SECRET')
        
        # 私信功能管理器（支持隔离加载）
        self.dm_manager = None
        
        if not all([self.telegram_token, self.twitter_api_key, self.twitter_api_secret, 
                   self.twitter_access_token, self.twitter_access_token_secret, 
                   self.twitter_bearer_token, self.authorized_user_id]):
            raise ValueError("Missing required environment variables")
        
        # 初始化Twitter客户端，优雅处理失败
        try:
            self.twitter_client = tweepy.Client(
                bearer_token=self.twitter_bearer_token,
                consumer_key=self.twitter_api_key,
                consumer_secret=self.twitter_api_secret,
                access_token=self.twitter_access_token,
                access_token_secret=self.twitter_access_token_secret,
                wait_on_rate_limit=True
            )
            self.logger.info("✅ Twitter客户端初始化成功")
        except Exception as e:
            self.logger.error(f"❌ Twitter客户端初始化失败: {e}")
            self.twitter_client = None
            
        # 初始化DM配置对象
        self.dm_config = self._create_dm_config()
    
    def _create_dm_config(self):
        """创建DM配置对象"""
        import os
        
        class DMConfig:
            def __init__(self):
                self.enable_dm_monitoring = os.getenv('ENABLE_DM_MONITORING', 'false').lower() == 'true'
                self.dm_poll_interval = int(os.getenv('DM_POLL_INTERVAL', '60'))
                self.dm_target_chat_id = os.getenv('DM_TARGET_CHAT_ID', os.getenv('AUTHORIZED_USER_ID'))
                self.dm_store_file = os.getenv('DM_STORE_FILE', 'data/processed_dm_ids.json')
                self.dm_store_max_age_days = int(os.getenv('DM_STORE_MAX_AGE_DAYS', '7'))
        
        return DMConfig()
    
    def is_authorized_user(self, user_id: int) -> bool:
        return str(user_id) == self.authorized_user_id
    
    async def dm_command(self, update, context):
        """处理/dm命令 - 启用或查看私信功能状态"""
        from telegram import Update
        from telegram.ext import ContextTypes
        
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        try:
            # 如果DM管理器未初始化，先初始化
            if not self.dm_manager:
                await self._initialize_dm_manager()
            
            # 尝试唤醒DM功能
            result = await self.dm_manager.wake_up()
            
            status_emoji = {
                'success': '✅',
                'error': '❌', 
                'info': 'ℹ️'
            }.get(result['status'], '❓')
            
            response_text = f"{status_emoji} {result['message']}"
            
            # 如果成功启动，显示详细状态
            if result['status'] == 'success':
                dm_status = self.dm_manager.get_status()
                response_text += f"\n\n📊 **私信监听状态**\n"
                response_text += f"🔄 轮询间隔: {dm_status.get('poll_interval', 'N/A')}秒\n"
                response_text += f"📱 目标聊天: {self.dm_config.dm_target_chat_id}\n"
                response_text += f"💾 已处理: {dm_status.get('processed_count', 0)}条私信"
            
            await update.message.reply_text(response_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"处理/dm命令时出错: {e}")
            await update.message.reply_text(f"❌ 处理DM命令失败: {str(e)}")
    
    async def _initialize_dm_manager(self):
        """初始化DM管理器 - 支持优雅失败"""
        try:
            from src.dm.manager import DMManager
            
            if not self.dm_manager:
                self.dm_manager = DMManager(
                    twitter_client=self.twitter_client,
                    telegram_bot=self,
                    config=self.dm_config
                )
                
            # 如果未初始化，进行初始化（但不启动）
            if not self.dm_manager.is_initialized:
                await self.dm_manager.initialize()
                self.logger.info("✅ DM管理器初始化完成")
                
        except ImportError:
            self.logger.warning("⚠️ DM管理器模块不可用，跳过DM功能")
            self.dm_manager = None
        except Exception as e:
            self.logger.error(f"❌ 初始化DM管理器失败: {e}")
            self.dm_manager = None
    
    async def send_telegram_message(self, message: str):
        """发送消息到Telegram"""
        try:
            from telegram.ext import Application
            application = Application.builder().token(self.telegram_token).build()
            await application.bot.send_message(
                chat_id=self.authorized_user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            self.logger.error(f"发送Telegram消息失败: {e}")
    
    async def run(self):
        """运行兼容模式的机器人"""
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
        from aiohttp import web
        import aiohttp
        from datetime import datetime
        
        # 设置Telegram bot
        application = Application.builder().token(self.telegram_token).build()
        
        # 添加基本处理程序
        application.add_handler(CommandHandler("start", self._start_handler))
        application.add_handler(CommandHandler("help", self._help_handler))
        application.add_handler(CommandHandler("status", self._status_handler))
        application.add_handler(CommandHandler("dm", self.dm_command))
        application.add_handler(MessageHandler(filters.PHOTO, self._photo_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._text_handler))
        
        # 设置健康检查服务器
        async def health_check(request):
            return web.Response(text="OK", status=200)
        
        app = web.Application()
        app.router.add_get("/health", health_check)
        app.router.add_get("/", health_check)
        
        # 启动HTTP服务器
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8000)
        await site.start()
        
        self.logger.info("🌐 健康检查服务器启动在端口8000...")
        self.logger.info("🤖 Bot开始运行...")
        
        # 启动Telegram bot
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        # 初始化私信功能（优雅失败）
        try:
            await self._initialize_dm_manager()
            if self.dm_manager:
                self.logger.info("📩 私信功能初始化完成")
        except Exception as e:
            self.logger.warning(f"⚠️ 私信功能初始化失败，将在需要时重试: {e}")
        
        # 发送启动通知
        try:
            startup_message = f"""
🤖 <b>Twitter Bot 已启动</b> (兼容模式)

✅ <b>状态:</b> 在线运行
🔗 <b>Twitter API:</b> {'已连接' if self.twitter_client else '未连接'}
📩 <b>DM功能:</b> {'可用' if self.dm_manager else '不可用'}
⏰ <b>启动时间:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📝 发送任何消息给我，我会自动转发到你的Twitter账户。
使用 /dm 启用私信监听功能。
            """.strip()
            
            await self.send_telegram_message(startup_message)
            self.logger.info("📢 启动通知已发送")
        except Exception as e:
            self.logger.error(f"发送启动通知失败: {e}")
        
        # 保持运行
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            self.logger.info("👋 收到停止信号...")
        finally:
            # 优雅停止
            if self.dm_manager:
                try:
                    await self.dm_manager.stop()
                    self.logger.info("📩 私信功能已停止")
                except Exception as e:
                    self.logger.error(f"停止私信功能时出错: {e}")
            
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            await runner.cleanup()
    
    async def _start_handler(self, update, context):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
            
        await update.message.reply_text(
            "你好！发送任何消息给我，我会自动转发到你的Twitter账户。\n\n"
            "使用 /help 查看帮助信息。\n"
            "使用 /dm 启用私信监听功能。"
        )
    
    async def _help_handler(self, update, context):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
            
        help_text = """
使用方法：
1. 直接发送文本消息 - 将会发布到Twitter
2. 发送图片（可带文字描述） - 将会发布图片到Twitter
3. /start - 开始使用
4. /help - 显示帮助信息
5. /dm - 启用/查看私信监听功能
6. /status - 查看Bot运行状态

注意：消息长度不能超过280字符，图片将自动压缩优化
        """
        await update.message.reply_text(help_text)
    
    async def _status_handler(self, update, context):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        twitter_status = "✅ 正常" if self.twitter_client else "❌ 失败"
        dm_status = "✅ 可用" if self.dm_manager else "❌ 不可用"
        
        status_message = f"""
📊 <b>Bot 运行状态</b> (兼容模式)

🤖 <b>Telegram Bot:</b> ✅ 在线
🐦 <b>Twitter API:</b> {twitter_status}
📩 <b>DM功能:</b> {dm_status}
👤 <b>授权用户:</b> {update.effective_user.first_name}

💡 <b>使用提示:</b>
• 直接发送文本 → 发布推文
• 发送图片 → 发布图片推文
• /help → 查看帮助
        """.strip()
        
        await update.message.reply_text(status_message, parse_mode='HTML')
    
    async def _text_handler(self, update, context):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_client:
            await update.message.reply_text("❌ Twitter API未正确配置，请检查环境变量。")
            return
            
        try:
            message_text = update.message.text
            
            if len(message_text) > 280:
                await update.message.reply_text("📏 消息太长了！Twitter限制280字符以内。")
                return
            
            response = self.twitter_client.create_tweet(text=message_text)
            tweet_id = response.data['id']
            
            await update.message.reply_text(
                f"✅ 推文发送成功！\n\n"
                f"🆔 推文ID: {tweet_id}\n"
                f"📝 内容: {message_text}"
            )
            
        except Exception as e:
            self.logger.error(f"发送推文时出错: {e}")
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                await update.message.reply_text("❌ Twitter API认证失败，请检查API密钥和权限设置。")
            else:
                await update.message.reply_text(f"❌ 发送推文失败: {error_msg}")
    
    async def _photo_handler(self, update, context):
        if not self.is_authorized_user(update.effective_user.id):
            await update.message.reply_text("❌ 你没有权限使用此机器人。")
            return
        
        if not self.twitter_client:
            await update.message.reply_text("❌ Twitter API未正确配置，请检查环境变量。")
            return
            
        try:
            import tempfile
            import tweepy
            from PIL import Image
            
            # 获取图片和文字描述
            photo = update.message.photo[-1]  # 获取最大尺寸的图片
            caption = update.message.caption or ""
            
            if len(caption) > 280:
                await update.message.reply_text("📏 文字描述太长了！Twitter限制280字符以内。")
                return
            
            # 下载图片
            file = await context.bot.get_file(photo.file_id)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                # 下载图片到临时文件
                await file.download_to_drive(temp_file.name)
                
                try:
                    # 使用Pillow优化图片
                    with Image.open(temp_file.name) as img:
                        # 转换为RGB（Twitter需要）
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # 调整图片大小（Twitter限制5MB）
                        max_size = (2048, 2048)
                        img.thumbnail(max_size, Image.Resampling.LANCZOS)
                        
                        # 保存优化后的图片
                        optimized_path = temp_file.name.replace('.jpg', '_optimized.jpg')
                        img.save(optimized_path, 'JPEG', quality=85, optimize=True)
                    
                    # 初始化Twitter API v1.1客户端用于媒体上传
                    auth = tweepy.OAuth1UserHandler(
                        self.twitter_api_key,
                        self.twitter_api_secret,
                        self.twitter_access_token,
                        self.twitter_access_token_secret
                    )
                    api = tweepy.API(auth)
                    
                    # 上传媒体
                    media = api.media_upload(optimized_path)
                    
                    # 创建带媒体的推文
                    response = self.twitter_client.create_tweet(
                        text=caption,
                        media_ids=[media.media_id]
                    )
                    
                    tweet_id = response.data['id']
                    
                    await update.message.reply_text(
                        f"✅ 图片推文发送成功！\n\n"
                        f"🆔 推文ID: {tweet_id}\n"
                        f"📝 描述: {caption if caption else '无描述'}"
                    )
                    
                finally:
                    # 清理临时文件
                    try:
                        import os
                        os.unlink(temp_file.name)
                        if 'optimized_path' in locals():
                            os.unlink(optimized_path)
                    except:
                        pass
            
        except Exception as e:
            self.logger.error(f"发送图片推文时出错: {e}")
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                await update.message.reply_text("❌ Twitter API认证失败，请检查API密钥和权限设置。")
            elif "413" in error_msg or "too large" in error_msg.lower():
                await update.message.reply_text("❌ 图片太大，请发送较小的图片。")
            else:
                await update.message.reply_text(f"❌ 发送图片推文失败: {error_msg}")

if __name__ == "__main__":
    main()
