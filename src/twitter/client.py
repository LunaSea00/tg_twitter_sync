import logging
import time
import os
import tweepy
import requests
import json
from typing import Dict, Any, List, Optional
from ..utils.exceptions import TwitterAPIError, RateLimitError
from ..utils.error_handler import handle_errors, ErrorHandler
from ..utils.rate_limiter import get_rate_limiter
from ..media.uploader import MediaUploader
from .oauth import TwitterOAuth2

logger = logging.getLogger(__name__)

class TwitterClient:
    def __init__(self, credentials: Dict[str, str], max_length: int = 280, config=None):
        self.max_length = max_length
        self.credentials = credentials
        self.config = config
        self._client = None
        self._connection_verified = None
        self._dm_access_verified = None
        
        # 初始化速率限制器
        if config:
            from ..utils.rate_limiter import get_rate_limiter
            self.rate_limiter = get_rate_limiter(config)
        else:
            self.rate_limiter = None
        
        try:
            # 完全延迟初始化 - 只存储凭据，不进行任何API相关操作
            logger.info("📝 Twitter客户端凭据已加载（未验证）")
            
            # OAuth 2.0 处理器延迟初始化
            self.oauth2_handler = None
            self._oauth2_initialized = False
            
            # 用户上下文访问令牌（用于DM API）
            self.user_access_token = credentials.get('user_access_token')
            
            # 媒体上传器将在需要时初始化
            self._media_uploader = None
            
            # 检查是否跳过验证
            skip_verification = config and getattr(config, 'skip_twitter_verification', False)
            if skip_verification or os.getenv('SKIP_TWITTER_VERIFICATION', '').lower() == 'true':
                logger.info("⚡ 快速启动模式：跳过API验证")
            
            logger.info("✅ Twitter客户端初始化成功（延迟模式）")
        except Exception as e:
            logger.error(f"Twitter客户端初始化失败: {e}")
            raise TwitterAPIError(f"初始化Twitter客户端失败: {e}")
    
    @property
    def client(self):
        """获取Twitter客户端（延迟初始化）"""
        if self._client is None:
            try:
                self._client = tweepy.Client(
                    bearer_token=self.credentials['bearer_token'],
                    consumer_key=self.credentials['consumer_key'],
                    consumer_secret=self.credentials['consumer_secret'],
                    access_token=self.credentials['access_token'],
                    access_token_secret=self.credentials['access_token_secret'],
                    wait_on_rate_limit=True
                )
                logger.info("Twitter客户端延迟初始化完成")
            except Exception as e:
                logger.error(f"Twitter客户端延迟初始化失败: {e}")
                raise TwitterAPIError(f"Twitter客户端初始化失败: {e}")
        return self._client
    
    @property
    def media_uploader(self):
        """获取媒体上传器（延迟初始化）"""
        if self._media_uploader is None:
            from ..media.uploader import MediaUploader
            self._media_uploader = MediaUploader(self)
        return self._media_uploader
    
    def _initialize_oauth2_if_needed(self):
        """按需初始化OAuth 2.0处理器"""
        if not self._oauth2_initialized and self.credentials.get('oauth2_client_id'):
            try:
                self.oauth2_handler = TwitterOAuth2(
                    client_id=self.credentials['oauth2_client_id'],
                    client_secret=self.credentials.get('oauth2_client_secret', ''),
                    redirect_uri=self.credentials.get('redirect_uri', 'http://localhost:8080/callback')
                )
                logger.info("OAuth 2.0处理器延迟初始化成功")
            except Exception as e:
                logger.error(f"OAuth 2.0处理器延迟初始化失败: {e}")
            finally:
                self._oauth2_initialized = True
    
    @handle_errors("推文发送失败")
    async def create_tweet(self, text: str) -> Dict[str, Any]:
        """创建推文"""
        try:
            if not self.validate_tweet_length(text):
                raise TwitterAPIError(f"推文长度超过{self.max_length}字符限制")
            
            if not text.strip():
                raise TwitterAPIError("推文内容不能为空")
            
            # 检查dry-run模式
            if self.config and self.config.dry_run_mode:
                logger.info(f"🧪 DRY-RUN模式: 模拟发送推文")
                logger.info(f"📝 推文内容: {text}")
                fake_tweet_id = f"dry_run_{int(time.time())}"
                return {
                    'success': True,
                    'tweet_id': fake_tweet_id,
                    'text': text,
                    'url': f"https://twitter.com/user/status/{fake_tweet_id}",
                    'dry_run': True
                }
            
            # 按需验证连接
            connection_ok = await self.test_connection()
            if not connection_ok:
                raise TwitterAPIError("⏳ Twitter API已达到每日限制，请24小时后再试")
            
            response = self.client.create_tweet(text=text)
            tweet_id = response.data['id']
            
            logger.info(f"推文创建成功: {tweet_id}")
            return {
                'success': True,
                'tweet_id': tweet_id,
                'text': text,
                'url': f"https://twitter.com/user/status/{tweet_id}"
            }
            
        except tweepy.TooManyRequests as e:
            logger.warning(f"Twitter API频率限制: {e}")
            raise RateLimitError("⏳ Twitter API已达到每日限制，请24小时后再试")
        
        except tweepy.Forbidden as e:
            logger.error(f"Twitter API禁止访问: {e}")
            raise TwitterAPIError("🔑 Twitter API凭据需要重新配置")
        
        except tweepy.Unauthorized as e:
            logger.error(f"Twitter API未授权: {e}")
            raise TwitterAPIError("🔑 Twitter API凭据需要重新配置")
        
        except tweepy.BadRequest as e:
            logger.error(f"Twitter API请求错误: {e}")
            raise TwitterAPIError(f"❌ 推文格式错误: {e}")
        
        except Exception as e:
            logger.error(f"Twitter API未知错误: {e}")
            raise TwitterAPIError(f"❌ Twitter服务暂时不可用，请稍后再试")
    
    @handle_errors("带媒体推文发送失败")
    async def create_tweet_with_media(self, text: str, image_paths: List[str]) -> Dict[str, Any]:
        """创建带有图片的推文"""
        try:
            if not self.validate_tweet_length(text):
                raise TwitterAPIError(f"推文长度超过{self.max_length}字符限制")
            
            if len(image_paths) > 4:
                raise TwitterAPIError("最多支持4张图片")
            
            if not image_paths:
                # 如果没有图片，回退到普通推文
                return await self.create_tweet(text)
            
            # 按需验证连接
            connection_ok = await self.test_connection()
            if not connection_ok:
                raise TwitterAPIError("⏳ Twitter API已达到每日限制，请24小时后再试")
            
            # 上传媒体文件
            media_ids = self.media_uploader.upload_multiple_media(image_paths)
            
            if not media_ids:
                raise TwitterAPIError("没有成功上传任何图片")
            
            # 创建带媒体的推文
            result = self.media_uploader.create_tweet_with_media(text, media_ids)
            
            logger.info(f"带媒体的推文创建成功: {result['tweet_id']}")
            return result
            
        except tweepy.TooManyRequests as e:
            logger.warning(f"Twitter API频率限制: {e}")
            raise RateLimitError("⏳ Twitter API已达到每日限制，请24小时后再试")
        
        except tweepy.Forbidden as e:
            logger.error(f"Twitter API禁止访问: {e}")
            raise TwitterAPIError("🔑 Twitter API凭据需要重新配置")
        
        except tweepy.Unauthorized as e:
            logger.error(f"Twitter API未授权: {e}")
            raise TwitterAPIError("🔑 Twitter API凭据需要重新配置")
        
        except tweepy.BadRequest as e:
            logger.error(f"Twitter API请求错误: {e}")
            raise TwitterAPIError(f"❌ 媒体推文格式错误: {e}")
        
        except Exception as e:
            logger.error(f"Twitter API未知错误: {e}")
            raise TwitterAPIError(f"❌ Twitter服务暂时不可用，请稍后再试")
    
    def validate_tweet_length(self, text: str) -> bool:
        """验证推文长度"""
        return len(text.strip()) <= self.max_length
    
    def get_tweet_stats(self, text: str) -> Dict[str, int]:
        """获取推文统计信息"""
        return {
            'length': len(text),
            'remaining': self.max_length - len(text),
            'max_length': self.max_length
        }
    
    async def test_connection(self) -> bool:
        """测试Twitter连接（带缓存）- 按需验证"""
        # 检查是否跳过验证
        if self.config and getattr(self.config, 'skip_twitter_verification', False):
            logger.info("⏭️ 跳过Twitter连接验证（配置禁用）")
            return True
            
        if os.getenv('SKIP_TWITTER_VERIFICATION', '').lower() == 'true':
            logger.info("⏭️ 跳过Twitter连接验证（环境变量禁用）")
            return True
            
        if self._connection_verified is not None:
            return self._connection_verified
        
        try:
            logger.info("🔍 首次使用Twitter功能，正在验证连接...")
            # 使用速率限制装饰器
            if self.rate_limiter:
                test_func = self.rate_limiter.rate_limit_handler(self._test_connection_impl)
                result = await test_func()
            else:
                result = await self._test_connection_impl()
            
            self._connection_verified = result
            if result:
                logger.info("✅ Twitter连接验证成功")
            else:
                logger.warning("❌ Twitter连接验证失败")
            return result
        except Exception as e:
            logger.error(f"Twitter连接测试失败: {e}")
            self._connection_verified = False
            return False
    
    async def _test_connection_impl(self) -> bool:
        """内部连接测试实现"""
        try:
            self.client.get_me()
            logger.info("Twitter连接测试成功")
            return True
        except Exception as e:
            logger.error(f"Twitter连接测试失败: {e}")
            return False
    
    def _get_dm_headers(self) -> Dict[str, str]:
        """获取DM API请求头"""
        if not self.user_access_token:
            raise TwitterAPIError("需要用户访问令牌才能使用DM API")
        
        return {
            'Authorization': f'Bearer {self.user_access_token}',
            'Content-Type': 'application/json'
        }
    
    def _process_dm_response(self, response: requests.Response) -> List[Dict[str, Any]]:
        """处理DM API响应"""
        if response.status_code == 200:
            data = response.json()
            
            if not data.get('data'):
                return []
            
            # 处理响应数据
            messages = []
            for dm_event in data['data']:
                message_dict = {
                    'id': dm_event['id'],
                    'text': dm_event.get('text', ''),
                    'created_at': dm_event.get('created_at'),
                    'sender_id': dm_event.get('sender_id'),
                    'dm_conversation_id': dm_event.get('dm_conversation_id'),
                }
                
                # 添加附件信息
                if dm_event.get('attachments'):
                    message_dict['attachments'] = dm_event['attachments']
                
                # 添加引用推文信息
                if dm_event.get('referenced_tweet'):
                    message_dict['referenced_tweet'] = dm_event['referenced_tweet']
                
                # 添加includes信息
                if data.get('includes'):
                    message_dict['includes'] = {}
                    if data['includes'].get('users'):
                        message_dict['includes']['users'] = data['includes']['users']
                    if data['includes'].get('media'):
                        message_dict['includes']['media'] = data['includes']['media']
                    if data['includes'].get('tweets'):
                        message_dict['includes']['tweets'] = data['includes']['tweets']
                
                messages.append(message_dict)
            
            return messages
            
        elif response.status_code == 429:
            logger.warning("私信API频率限制")
            raise RateLimitError("私信API调用过于频繁，请稍后重试")
            
        elif response.status_code == 403:
            error_data = response.json()
            logger.error(f"私信API禁止访问: {error_data}")
            raise TwitterAPIError("没有权限访问私信API，请检查API权限和用户授权")
            
        elif response.status_code == 401:
            logger.error("私信API未授权")
            raise TwitterAPIError("私信API授权失败，请检查用户访问令牌")
            
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get('title', '未知错误')
            except:
                error_msg = f"HTTP {response.status_code}"
            logger.error(f"获取私信失败: {response.status_code} - {error_msg}")
            raise TwitterAPIError(f"获取私信失败: {error_msg}")
    
    async def get_all_dm_events(self, max_results: int = 100, next_token: str = None) -> Dict[str, Any]:
        """
        获取最近全部 DM 事件（过去 30 天内）
        API: GET /2/dm_events
        """
        try:
            url = "https://api.twitter.com/2/dm_events"
            headers = self._get_dm_headers()
            
            params = {
                'max_results': min(max_results, 100),  # API限制最多100
                'dm_event.fields': 'id,text,created_at,sender_id,dm_conversation_id,attachments,referenced_tweet',
                'expansions': 'sender_id,attachments.media_keys,referenced_tweet.id',
                'user.fields': 'id,username,name,profile_image_url',
                'media.fields': 'media_key,type,url,preview_image_url',
                'tweet.fields': 'id,text,author_id,created_at'
            }
            
            if next_token:
                params['pagination_token'] = next_token
            
            response = requests.get(url, headers=headers, params=params)
            messages = self._process_dm_response(response)
            
            # 处理分页信息
            result = {
                'data': messages,
                'meta': response.json().get('meta', {})
            }
            
            logger.info(f"获取到 {len(messages)} 条DM事件")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"私信API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取DM事件时发生错误: {e}")
            raise TwitterAPIError(f"获取DM事件失败: {e}")
    
    async def get_dm_with_user(self, participant_id: str, max_results: int = 100, next_token: str = None) -> Dict[str, Any]:
        """
        获取与某用户的对话消息
        API: GET /2/dm_conversations/with/:participant_id/dm_events
        """
        try:
            url = f"https://api.twitter.com/2/dm_conversations/with/{participant_id}/dm_events"
            headers = self._get_dm_headers()
            
            params = {
                'max_results': min(max_results, 100),
                'dm_event.fields': 'id,text,created_at,sender_id,dm_conversation_id,attachments,referenced_tweet',
                'expansions': 'sender_id,attachments.media_keys,referenced_tweet.id',
                'user.fields': 'id,username,name,profile_image_url',
                'media.fields': 'media_key,type,url,preview_image_url',
                'tweet.fields': 'id,text,author_id,created_at'
            }
            
            if next_token:
                params['pagination_token'] = next_token
            
            response = requests.get(url, headers=headers, params=params)
            messages = self._process_dm_response(response)
            
            result = {
                'data': messages,
                'meta': response.json().get('meta', {})
            }
            
            logger.info(f"获取到与用户 {participant_id} 的 {len(messages)} 条对话")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"私信API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取用户对话时发生错误: {e}")
            raise TwitterAPIError(f"获取用户对话失败: {e}")
    
    async def get_dm_conversation_events(self, conversation_id: str, max_results: int = 100, next_token: str = None) -> Dict[str, Any]:
        """
        获取某条对话中的消息（支持群组）
        API: GET /2/dm_conversations/:dm_conversation_id/dm_events
        """
        try:
            url = f"https://api.twitter.com/2/dm_conversations/{conversation_id}/dm_events"
            headers = self._get_dm_headers()
            
            params = {
                'max_results': min(max_results, 100),
                'dm_event.fields': 'id,text,created_at,sender_id,dm_conversation_id,attachments,referenced_tweet',
                'expansions': 'sender_id,attachments.media_keys,referenced_tweet.id',
                'user.fields': 'id,username,name,profile_image_url',
                'media.fields': 'media_key,type,url,preview_image_url',
                'tweet.fields': 'id,text,author_id,created_at'
            }
            
            if next_token:
                params['pagination_token'] = next_token
            
            response = requests.get(url, headers=headers, params=params)
            messages = self._process_dm_response(response)
            
            result = {
                'data': messages,
                'meta': response.json().get('meta', {})
            }
            
            logger.info(f"获取到对话 {conversation_id} 的 {len(messages)} 条消息")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"私信API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取对话消息时发生错误: {e}")
            raise TwitterAPIError(f"获取对话消息失败: {e}")
    
    # 主要的私信获取方法，支持多种实现方式
    async def get_direct_messages(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        获取私信（优先使用高级DM API，回退到tweepy实现）
        """
        try:
            # 按需验证DM访问权限
            dm_access_ok = await self.test_dm_access()
            if not dm_access_ok:
                raise TwitterAPIError("🔑 Twitter DM API凭据需要重新配置")
            
            # 优先尝试使用高级DM API
            if self.user_access_token:
                result = await self.get_all_dm_events(max_results)
                return result['data']
            else:
                # 回退到tweepy的实现
                logger.info("使用tweepy回退实现获取私信")
                response = self.client.get_direct_message_events(
                    max_results=max_results,
                    dm_event_fields=['id', 'text', 'created_at', 'sender_id', 'attachments'],
                    expansions=['sender_id', 'attachments.media_keys'],
                    user_fields=['id', 'username', 'name', 'profile_image_url'],
                    media_fields=['media_key', 'type', 'url', 'preview_image_url']
                )
                
                if not response.data:
                    return []
                
                # 处理响应数据
                messages = []
                for dm_event in response.data:
                    message_dict = {
                        'id': dm_event.id,
                        'text': dm_event.text,
                        'created_at': dm_event.created_at.isoformat() if dm_event.created_at else None,
                        'sender_id': dm_event.sender_id,
                    }
                    
                    # 添加附件信息
                    if hasattr(dm_event, 'attachments') and dm_event.attachments:
                        message_dict['attachments'] = dm_event.attachments
                    
                    # 添加includes信息
                    if hasattr(response, 'includes'):
                        message_dict['includes'] = {}
                        if response.includes.get('users'):
                            message_dict['includes']['users'] = [
                                {
                                    'id': user.id,
                                    'username': user.username,
                                    'name': user.name,
                                    'profile_image_url': getattr(user, 'profile_image_url', None)
                                }
                                for user in response.includes['users']
                            ]
                        if response.includes.get('media'):
                            message_dict['includes']['media'] = [
                                {
                                    'media_key': media.media_key,
                                    'type': media.type,
                                    'url': getattr(media, 'url', None),
                                    'preview_image_url': getattr(media, 'preview_image_url', None)
                                }
                                for media in response.includes['media']
                            ]
                    
                    messages.append(message_dict)
                
                logger.info(f"使用tweepy获取到 {len(messages)} 条私信")
                return messages
                
        except tweepy.TooManyRequests as e:
            logger.warning(f"私信API频率限制: {e}")
            raise RateLimitError("⏳ Twitter API已达到每日限制，请24小时后再试")
        
        except tweepy.Forbidden as e:
            logger.error(f"私信API禁止访问: {e}")
            raise TwitterAPIError("🔑 Twitter DM API凭据需要重新配置")
        
        except tweepy.Unauthorized as e:
            logger.error(f"私信API未授权: {e}")
            raise TwitterAPIError("🔑 Twitter DM API凭据需要重新配置")
        
        except Exception as e:
            logger.error(f"获取私信时发生错误: {e}")
            raise TwitterAPIError(f"❌ Twitter服务暂时不可用，请稍后再试")
    
    async def test_dm_access(self) -> bool:
        """测试私信API访问权限（带缓存）- 按需验证"""
        # 检查是否跳过验证
        if self.config and getattr(self.config, 'skip_twitter_verification', False):
            logger.info("⏭️ 跳过DM API验证（配置禁用）")
            return True
            
        if os.getenv('SKIP_TWITTER_VERIFICATION', '').lower() == 'true':
            logger.info("⏭️ 跳过DM API验证（环境变量禁用）")
            return True
            
        if self._dm_access_verified is not None:
            return self._dm_access_verified
        
        try:
            logger.info("🔍 首次使用DM功能，正在验证访问权限...")
            # 初始化OAuth2处理器（如果需要）
            self._initialize_oauth2_if_needed()
            
            # 使用速率限制装饰器
            if self.rate_limiter:
                test_func = self.rate_limiter.rate_limit_handler(self._test_dm_access_impl)
                result = await test_func()
            else:
                result = await self._test_dm_access_impl()
            
            self._dm_access_verified = result
            if result:
                logger.info("✅ DM API访问验证成功")
            else:
                logger.warning("❌ DM API访问验证失败")
            return result
        except Exception as e:
            logger.error(f"私信API测试时发生未知错误: {e}")
            self._dm_access_verified = False
            return False
    
    async def _test_dm_access_impl(self) -> bool:
        """内部DM访问测试实现"""
        try:
            # 尝试获取少量私信来测试权限
            await self.get_direct_messages(max_results=1)
            logger.info("私信API访问测试成功")
            return True
        except TwitterAPIError as e:
            logger.error(f"私信API访问测试失败: {e}")
            return False
        except Exception as e:
            logger.error(f"私信API测试时发生未知错误: {e}")
            return False
    
    @handle_errors("发送私信失败")
    async def send_direct_message(self, conversation_id: str, text: str, media_id: Optional[str] = None) -> Dict[str, Any]:
        """发送私信到指定对话"""
        try:
            url = f"https://api.twitter.com/2/dm_conversations/{conversation_id}/messages"
            headers = self._get_dm_headers()
            
            # 构建请求数据
            data = {
                'text': text
            }
            
            # 如果有媒体附件
            if media_id:
                data['attachments'] = [
                    {
                        'media_id': media_id
                    }
                ]
            
            # 发送请求
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 201:
                result = response.json()
                logger.info(f"私信发送成功: {result['data']['dm_event_id']}")
                return {
                    'success': True,
                    'dm_conversation_id': result['data']['dm_conversation_id'],
                    'dm_event_id': result['data']['dm_event_id'],
                    'text': text
                }
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('title', '未知错误')
                except:
                    error_msg = f"HTTP {response.status_code}"
                logger.error(f"私信发送失败: {response.status_code} - {error_msg}")
                raise TwitterAPIError(f"发送私信失败: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"私信API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        
        except Exception as e:
            logger.error(f"发送私信时发生错误: {e}")
            raise TwitterAPIError(f"发送私信失败: {e}")
    
    @handle_errors("创建私信对话失败")
    async def create_dm_conversation(self, participant_id: str, text: str, media_id: Optional[str] = None) -> Dict[str, Any]:
        """创建新的私信对话并发送消息"""
        try:
            url = "https://api.twitter.com/2/dm_conversations"
            
            headers = {
                'Authorization': f'Bearer {self.credentials["bearer_token"]}',
                'Content-Type': 'application/json'
            }
            
            # 构建请求数据
            data = {
                'conversation_type': 'OneToOne',
                'participant_ids': [participant_id],
                'text': text
            }
            
            # 如果有媒体附件
            if media_id:
                data['attachments'] = [
                    {
                        'media_id': media_id
                    }
                ]
            
            # 发送请求
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 201:
                result = response.json()
                logger.info(f"私信对话创建成功: {result['data']['dm_conversation_id']}")
                return {
                    'success': True,
                    'dm_conversation_id': result['data']['dm_conversation_id'],
                    'dm_event_id': result['data']['dm_event_id'],
                    'text': text
                }
            else:
                error_data = response.json()
                logger.error(f"创建私信对话失败: {response.status_code} - {error_data}")
                raise TwitterAPIError(f"创建私信对话失败: {error_data.get('title', '未知错误')}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"私信API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        
        except Exception as e:
            logger.error(f"创建私信对话时发生错误: {e}")
            raise TwitterAPIError(f"创建私信对话失败: {e}")
    
    async def send_dm_to_user(self, username_or_id: str, text: str, media_id: Optional[str] = None) -> Dict[str, Any]:
        """向用户发送私信（自动创建对话或使用现有对话）"""
        try:
            # 如果是用户名，先获取用户ID
            if not username_or_id.isdigit():
                user = self.client.get_user(username=username_or_id)
                if not user.data:
                    raise TwitterAPIError(f"用户 {username_or_id} 不存在")
                user_id = user.data.id
            else:
                user_id = username_or_id
            
            # 尝试创建新对话（如果对话已存在，API会返回现有对话）
            return await self.create_dm_conversation(user_id, text, media_id)
            
        except Exception as e:
            logger.error(f"发送私信给用户 {username_or_id} 失败: {e}")
            raise TwitterAPIError(f"发送私信失败: {e}")
    
    async def get_dm_conversations(self, max_results: int = 100, next_token: str = None) -> Dict[str, Any]:
        """
        获取DM对话列表
        API: GET /2/dm_conversations
        """
        try:
            url = "https://api.twitter.com/2/dm_conversations"
            headers = self._get_dm_headers()
            
            params = {
                'max_results': min(max_results, 100),
                'dm_conversation.fields': 'id,type',
                'expansions': 'participant_ids',
                'user.fields': 'id,username,name,profile_image_url'
            }
            
            if next_token:
                params['pagination_token'] = next_token
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                conversations = []
                
                if data.get('data'):
                    for conv in data['data']:
                        conversation_dict = {
                            'dm_conversation_id': conv['id'],
                            'type': conv.get('type', 'OneToOne'),
                            'participants': []
                        }
                        
                        # 添加参与者信息
                        if data.get('includes', {}).get('users'):
                            for user in data['includes']['users']:
                                conversation_dict['participants'].append({
                                    'id': user['id'],
                                    'username': user.get('username'),
                                    'name': user.get('name'),
                                    'profile_image_url': user.get('profile_image_url')
                                })
                        
                        conversations.append(conversation_dict)
                
                result = {
                    'data': conversations,
                    'meta': data.get('meta', {})
                }
                
                logger.info(f"获取到 {len(conversations)} 个DM对话")
                return result
                
            elif response.status_code == 429:
                logger.warning("DM对话API频率限制")
                raise RateLimitError("DM对话API调用过于频繁，请稍后重试")
                
            elif response.status_code == 403:
                error_data = response.json()
                logger.error(f"DM对话API禁止访问: {error_data}")
                raise TwitterAPIError("没有权限访问DM对话API，请检查API权限和用户授权")
                
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('title', '未知错误')
                except:
                    error_msg = f"HTTP {response.status_code}"
                logger.error(f"获取DM对话失败: {response.status_code} - {error_msg}")
                raise TwitterAPIError(f"获取DM对话失败: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"DM对话API网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取DM对话时发生错误: {e}")
            raise TwitterAPIError(f"获取DM对话失败: {e}")
    
    async def send_dm_by_conversation_id(self, conversation_id: str, text: str) -> Dict[str, Any]:
        """
        向指定对话ID发送私信 (简化版本，与提供的脚本兼容)
        """
        return await self.send_direct_message(conversation_id, text)
