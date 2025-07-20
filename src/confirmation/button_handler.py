import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any

from .confirmation_manager import ConfirmationManager, ConfirmationStatus
from .preview_generator import PreviewGenerator
from ..utils.error_handler import ErrorHandler

logger = logging.getLogger(__name__)

class ButtonHandler:
    """按钮回调处理器"""
    
    def __init__(self, twitter_client, confirmation_manager: ConfirmationManager, 
                 preview_generator: PreviewGenerator, config):
        self.twitter_client = twitter_client
        self.confirmation_manager = confirmation_manager
        self.preview_generator = preview_generator
        self.config = config
    
    def create_confirmation_keyboard(self, confirmation_key: str) -> InlineKeyboardMarkup:
        """创建确认按钮键盘"""
        keyboard = [
            [
                InlineKeyboardButton("✅ 确认发送", callback_data=f"confirm_{confirmation_key}"),
                InlineKeyboardButton("✏️ 编辑内容", callback_data=f"edit_{confirmation_key}")
            ],
            [
                InlineKeyboardButton("❌ 取消发送", callback_data=f"cancel_{confirmation_key}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def create_retry_keyboard(self, confirmation_key: str) -> InlineKeyboardMarkup:
        """创建重试按钮键盘"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 重试发送", callback_data=f"retry_{confirmation_key}"),
                InlineKeyboardButton("❌ 放弃", callback_data=f"abandon_{confirmation_key}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理按钮回调"""
        query = update.callback_query
        await query.answer()
        
        try:
            callback_data = query.data
            action, confirmation_key = callback_data.split('_', 1)
            
            # 获取确认请求
            pending_tweet = self.confirmation_manager.get_confirmation(confirmation_key)
            if not pending_tweet:
                await query.edit_message_text("❌ 确认请求不存在或已过期")
                return
            
            # 检查是否过期
            if self.confirmation_manager.is_expired(confirmation_key):
                timeout_msg = self.preview_generator.generate_timeout_message(pending_tweet)
                await query.edit_message_text(timeout_msg, parse_mode='Markdown')
                self.confirmation_manager.cancel_tweet(confirmation_key)
                return
            
            # 处理不同的按钮动作
            if action == "confirm":
                await self._handle_confirm(query, confirmation_key, pending_tweet)
            elif action == "edit":
                await self._handle_edit(query, confirmation_key, pending_tweet)
            elif action == "cancel":
                await self._handle_cancel(query, confirmation_key, pending_tweet)
            elif action == "retry":
                await self._handle_retry(query, confirmation_key, pending_tweet)
            elif action == "abandon":
                await self._handle_abandon(query, confirmation_key, pending_tweet)
            else:
                await query.edit_message_text("❌ 未知操作")
                
        except Exception as e:
            ErrorHandler.log_error(e, "按钮回调处理")
            await query.edit_message_text("❌ 处理请求时发生错误")
    
    async def _handle_confirm(self, query, confirmation_key: str, pending_tweet):
        """处理确认发送"""
        try:
            # 更新状态为已确认
            tweet = self.confirmation_manager.confirm_tweet(confirmation_key)
            if not tweet:
                await query.edit_message_text("❌ 确认请求状态异常")
                return
            
            # 显示发送中状态
            await query.edit_message_text("⏳ 正在发送推文...")
            
            # 发送推文
            if tweet.media_files:
                result = await self.twitter_client.create_tweet_with_media(
                    tweet.text, tweet.media_files
                )
            else:
                result = await self.twitter_client.create_tweet(tweet.text)
            
            if result.get('success'):
                # 发送成功
                success_msg = self.preview_generator.generate_success_message(
                    result['tweet_id'], result['url'], tweet.text
                )
                await query.edit_message_text(success_msg, parse_mode='Markdown')
                
                # 清理确认请求
                self.confirmation_manager.cancel_tweet(confirmation_key)
                
            else:
                # 发送失败，提供重试选项
                error_msg = self.preview_generator.generate_error_message(
                    result.get('error', '未知错误'), tweet
                )
                retry_keyboard = self.create_retry_keyboard(confirmation_key)
                await query.edit_message_text(
                    error_msg, 
                    parse_mode='Markdown',
                    reply_markup=retry_keyboard
                )
                
        except Exception as e:
            ErrorHandler.log_error(e, "确认发送推文")
            error_msg = self.preview_generator.generate_error_message(str(e), pending_tweet)
            retry_keyboard = self.create_retry_keyboard(confirmation_key)
            await query.edit_message_text(
                error_msg, 
                parse_mode='Markdown',
                reply_markup=retry_keyboard
            )
    
    async def _handle_edit(self, query, confirmation_key: str, pending_tweet):
        """处理编辑内容"""
        # 设置编辑模式
        self.confirmation_manager.set_editing_mode(confirmation_key)
        
        edit_msg = f"""✏️ *编辑模式*

*当前内容:*
{self.preview_generator._format_preview_text(pending_tweet.text)}

💡 *提示:* 请发送新的内容来替换当前推文"""
        
        await query.edit_message_text(edit_msg, parse_mode='Markdown')
    
    async def _handle_cancel(self, query, confirmation_key: str, pending_tweet):
        """处理取消发送"""
        self.confirmation_manager.cancel_tweet(confirmation_key)
        
        cancel_msg = f"""❌ *已取消发送*

*取消的内容:*
{self.preview_generator._format_preview_text(pending_tweet.text)}

💡 如需重新发送，请重新输入内容。"""
        
        await query.edit_message_text(cancel_msg, parse_mode='Markdown')
    
    async def _handle_retry(self, query, confirmation_key: str, pending_tweet):
        """处理重试发送"""
        await self._handle_confirm(query, confirmation_key, pending_tweet)
    
    async def _handle_abandon(self, query, confirmation_key: str, pending_tweet):
        """处理放弃发送"""
        await self._handle_cancel(query, confirmation_key, pending_tweet)
    
    def is_confirmation_enabled(self) -> bool:
        """检查确认功能是否启用"""
        return getattr(self.config, 'enable_confirmation', True)
    
    def should_require_confirmation(self, text: str, media_files: list = None) -> bool:
        """判断是否需要确认"""
        if not self.is_confirmation_enabled():
            return False
        
        # 检查是否所有推文都需要确认
        if getattr(self.config, 'require_confirmation_for_all', True):
            return True
        
        # 其他条件可以在这里添加，比如：
        # - 文本长度超过阈值
        # - 包含敏感词汇
        # - 包含媒体文件
        # - 包含链接等
        
        return False