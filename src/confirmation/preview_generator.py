import re
import logging
from typing import List, Dict, Any
from .confirmation_manager import PendingTweet

logger = logging.getLogger(__name__)

class PreviewGenerator:
    """预览内容生成器"""
    
    def __init__(self, config):
        self.config = config
        self.max_length = getattr(config, 'tweet_max_length', 280)
    
    def generate_preview(self, pending_tweet: PendingTweet) -> str:
        """生成确认预览消息"""
        try:
            # 分析文本内容
            text_info = self._analyze_text(pending_tweet.text)
            
            # 生成预览消息
            preview_text = f"""📝 *推文发送确认*

*内容预览:*
{self._format_preview_text(pending_tweet.text)}

📊 *推文信息:*
• 字符数: {text_info['char_count']}/{self.max_length}
• 图片: {len(pending_tweet.media_files)}张
• 链接: {text_info['link_count']}个
• 话题标签: {text_info['hashtag_count']}个
• 提及用户: {text_info['mention_count']}个

{self._get_status_indicator(text_info['char_count'])}"""
            
            return preview_text
            
        except Exception as e:
            logger.error(f"生成预览时出错: {e}")
            return f"📝 *推文发送确认*\n\n*内容预览:*\n{pending_tweet.text}\n\n❌ 预览生成失败"
    
    def _analyze_text(self, text: str) -> Dict[str, Any]:
        """分析文本内容"""
        # 计算字符数
        char_count = len(text)
        
        # 计算链接数量
        url_pattern = r'https?://\S+'
        links = re.findall(url_pattern, text)
        link_count = len(links)
        
        # 计算话题标签数量
        hashtag_pattern = r'#\w+'
        hashtags = re.findall(hashtag_pattern, text)
        hashtag_count = len(hashtags)
        
        # 计算提及用户数量
        mention_pattern = r'@\w+'
        mentions = re.findall(mention_pattern, text)
        mention_count = len(mentions)
        
        return {
            'char_count': char_count,
            'link_count': link_count,
            'hashtag_count': hashtag_count,
            'mention_count': mention_count,
            'links': links,
            'hashtags': hashtags,
            'mentions': mentions
        }
    
    def _format_preview_text(self, text: str, max_lines: int = 10) -> str:
        """格式化预览文本"""
        # 如果文本太长，进行截断
        if len(text) > 500:
            text = text[:500] + "..."
        
        # 如果行数太多，进行截断
        lines = text.split('\n')
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("...")
        
        # 转义Markdown特殊字符
        formatted_text = '\n'.join(lines)
        # 转义可能导致Markdown解析问题的字符
        formatted_text = formatted_text.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
        
        return f"```\n{formatted_text}\n```"
    
    def _get_status_indicator(self, char_count: int) -> str:
        """获取状态指示器"""
        if char_count > self.max_length:
            return f"🚨 *警告:* 字符数超出限制 ({char_count - self.max_length} 字符)"
        elif char_count > self.max_length * 0.9:
            return f"⚠️ *提醒:* 接近字符限制 (剩余 {self.max_length - char_count} 字符)"
        else:
            return f"✅ *状态:* 字符数正常 (剩余 {self.max_length - char_count} 字符)"
    
    def generate_timeout_message(self, pending_tweet: PendingTweet) -> str:
        """生成超时消息"""
        return f"""⏰ *确认请求已超时* (5分钟)

*推文未发送:*
{self._format_preview_text(pending_tweet.text)}

💡 如需重新发送，请重新输入内容。"""
    
    def generate_error_message(self, error: str, pending_tweet: PendingTweet = None) -> str:
        """生成错误消息"""
        base_msg = f"""❌ *发送失败:* {error}
💡 *建议:* 请检查网络连接或稍后重试"""
        
        if pending_tweet:
            base_msg += f"\n\n*原始内容:*\n{self._format_preview_text(pending_tweet.text)}"
        
        return base_msg
    
    def generate_success_message(self, tweet_id: str, tweet_url: str, text: str) -> str:
        """生成成功消息"""
        return f"""✅ *推文发送成功！*

🆔 *推文ID:* `{tweet_id}`
🔗 *链接:* {tweet_url}

*内容:* {self._format_preview_text(text)}"""