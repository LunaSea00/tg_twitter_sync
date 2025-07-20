import asyncio
import logging
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ConfirmationStatus(Enum):
    """确认状态枚举"""
    PENDING = "pending"       # 等待确认
    CONFIRMED = "confirmed"   # 已确认
    CANCELLED = "cancelled"   # 已取消
    EXPIRED = "expired"       # 已超时
    EDITING = "editing"       # 编辑中

@dataclass
class PendingTweet:
    """待发送推文数据"""
    user_id: int
    chat_id: int
    message_id: int
    text: str
    media_files: List[str] = None
    created_at: float = None
    expires_at: float = None
    status: ConfirmationStatus = ConfirmationStatus.PENDING
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.media_files is None:
            self.media_files = []

class ConfirmationManager:
    """确认状态管理器"""
    
    def __init__(self, config):
        self.config = config
        self._pending_tweets: Dict[str, PendingTweet] = {}
        self._cleanup_task = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_tweets())
    
    async def _cleanup_expired_tweets(self):
        """定期清理过期的确认请求"""
        while True:
            try:
                current_time = time.time()
                expired_keys = []
                
                for key, tweet in self._pending_tweets.items():
                    if current_time > tweet.expires_at and tweet.status == ConfirmationStatus.PENDING:
                        tweet.status = ConfirmationStatus.EXPIRED
                        expired_keys.append(key)
                        logger.info(f"确认请求已过期: {key}")
                
                # 移除过期的确认请求
                for key in expired_keys:
                    del self._pending_tweets[key]
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"清理过期确认请求时出错: {e}")
                await asyncio.sleep(60)
    
    def _generate_key(self, user_id: int, chat_id: int, message_id: int) -> str:
        """生成唯一键"""
        return f"{user_id}_{chat_id}_{message_id}"
    
    def create_confirmation(self, user_id: int, chat_id: int, message_id: int, 
                          text: str, media_files: List[str] = None) -> str:
        """创建确认请求"""
        key = self._generate_key(user_id, chat_id, message_id)
        
        current_time = time.time()
        pending_tweet = PendingTweet(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            media_files=media_files or [],
            created_at=current_time,
            expires_at=current_time + self.config.confirmation_timeout
        )
        
        self._pending_tweets[key] = pending_tweet
        logger.info(f"创建确认请求: {key}")
        return key
    
    def get_confirmation(self, key: str) -> Optional[PendingTweet]:
        """获取确认请求"""
        return self._pending_tweets.get(key)
    
    def update_status(self, key: str, status: ConfirmationStatus) -> bool:
        """更新确认状态"""
        if key in self._pending_tweets:
            self._pending_tweets[key].status = status
            logger.info(f"更新确认状态: {key} -> {status.value}")
            return True
        return False
    
    def confirm_tweet(self, key: str) -> Optional[PendingTweet]:
        """确认发送推文"""
        tweet = self._pending_tweets.get(key)
        if tweet and tweet.status == ConfirmationStatus.PENDING:
            tweet.status = ConfirmationStatus.CONFIRMED
            logger.info(f"确认发送推文: {key}")
            return tweet
        return None
    
    def cancel_tweet(self, key: str) -> bool:
        """取消发送推文"""
        if key in self._pending_tweets:
            self._pending_tweets[key].status = ConfirmationStatus.CANCELLED
            del self._pending_tweets[key]
            logger.info(f"取消发送推文: {key}")
            return True
        return False
    
    def set_editing_mode(self, key: str) -> bool:
        """设置编辑模式"""
        if key in self._pending_tweets:
            self._pending_tweets[key].status = ConfirmationStatus.EDITING
            logger.info(f"设置编辑模式: {key}")
            return True
        return False
    
    def is_expired(self, key: str) -> bool:
        """检查是否已过期"""
        tweet = self._pending_tweets.get(key)
        if tweet:
            return time.time() > tweet.expires_at
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._pending_tweets)
        pending = sum(1 for t in self._pending_tweets.values() 
                     if t.status == ConfirmationStatus.PENDING)
        editing = sum(1 for t in self._pending_tweets.values() 
                     if t.status == ConfirmationStatus.EDITING)
        
        return {
            'total_confirmations': total,
            'pending_confirmations': pending,
            'editing_confirmations': editing,
            'cleanup_task_running': self._cleanup_task is not None and not self._cleanup_task.done()
        }
    
    def cleanup(self):
        """清理资源"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        self._pending_tweets.clear()
        logger.info("确认管理器已清理")