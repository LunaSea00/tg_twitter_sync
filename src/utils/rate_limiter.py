import asyncio
import time
import logging
from functools import wraps
from typing import Dict, Any, Optional, Callable
import tweepy
from .exceptions import RateLimitError, TwitterAPIError

logger = logging.getLogger(__name__)

class RateLimiter:
    """速率限制管理器"""
    
    def __init__(self, config):
        self.config = config
        self.last_request_time = {}
        self.request_cache = {}
        self.cache_timestamps = {}
        
    def _get_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存键"""
        # 简单的缓存键生成，避免包含敏感信息
        key_parts = [func_name]
        
        # 只包含非敏感参数
        safe_args = []
        for arg in args:
            if isinstance(arg, (str, int, bool)) and len(str(arg)) < 100:
                safe_args.append(str(arg))
        
        safe_kwargs = {}
        for k, v in kwargs.items():
            if k not in ['password', 'token', 'secret', 'key'] and isinstance(v, (str, int, bool)) and len(str(v)) < 100:
                safe_kwargs[k] = str(v)
        
        if safe_args:
            key_parts.append('_'.join(safe_args))
        if safe_kwargs:
            key_parts.append('_'.join(f"{k}={v}" for k, v in sorted(safe_kwargs.items())))
        
        return '_'.join(key_parts)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if not self.config.rate_limit_enable_cache:
            return False
        
        if cache_key not in self.cache_timestamps:
            return False
        
        cache_time = self.cache_timestamps[cache_key]
        return (time.time() - cache_time) < self.config.rate_limit_cache_ttl
    
    def _get_cached_result(self, cache_key: str) -> Any:
        """获取缓存结果"""
        return self.request_cache.get(cache_key)
    
    def _cache_result(self, cache_key: str, result: Any):
        """缓存结果"""
        if self.config.rate_limit_enable_cache:
            self.request_cache[cache_key] = result
            self.cache_timestamps[cache_key] = time.time()
    
    async def _wait_for_rate_limit(self, func_name: str):
        """等待速率限制间隔"""
        if self.config.rate_limit_min_interval <= 0:
            return
        
        last_time = self.last_request_time.get(func_name, 0)
        current_time = time.time()
        time_passed = current_time - last_time
        
        if time_passed < self.config.rate_limit_min_interval:
            wait_time = self.config.rate_limit_min_interval - time_passed
            logger.debug(f"速率限制等待 {wait_time:.2f}s for {func_name}")
            await asyncio.sleep(wait_time)
        
        self.last_request_time[func_name] = time.time()
    
    def rate_limit_handler(self, func: Callable) -> Callable:
        """速率限制装饰器"""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__
            
            # 生成缓存键
            cache_key = self._get_cache_key(func_name, args, kwargs)
            
            # 检查缓存
            if self._is_cache_valid(cache_key):
                cached_result = self._get_cached_result(cache_key)
                if cached_result is not None:
                    logger.debug(f"使用缓存结果 for {func_name}")
                    return cached_result
            
            # 执行带重试的请求
            last_exception = None
            
            for attempt in range(self.config.rate_limit_max_retries + 1):
                try:
                    # 等待速率限制间隔
                    await self._wait_for_rate_limit(func_name)
                    
                    # 记录API调用开始
                    start_time = time.time()
                    logger.debug(f"🚀 开始API调用: {func_name}")
                    
                    # 执行原函数
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    
                    # 记录API调用完成
                    end_time = time.time()
                    duration = end_time - start_time
                    logger.info(f"✅ API调用成功: {func_name}, 耗时: {duration:.2f}s")
                    
                    # 缓存成功结果
                    self._cache_result(cache_key, result)
                    
                    if attempt > 0:
                        logger.info(f"重试成功: {func_name} (第{attempt + 1}次尝试)")
                    
                    return result
                
                except tweepy.TooManyRequests as e:
                    last_exception = e
                    if attempt < self.config.rate_limit_max_retries:
                        # 计算退避等待时间
                        backoff_time = self.config.rate_limit_min_interval * (self.config.rate_limit_backoff_factor ** attempt)
                        
                        # 尝试从响应头获取重置时间
                        reset_time = None
                        if hasattr(e, 'response') and e.response:
                            reset_header = e.response.headers.get('x-rate-limit-reset')
                            if reset_header:
                                try:
                                    reset_timestamp = int(reset_header)
                                    reset_time = max(0, reset_timestamp - int(time.time()))
                                except (ValueError, TypeError):
                                    pass
                        
                        # 使用API提供的重置时间或退避时间，取较小值
                        if reset_time is not None:
                            wait_time = min(backoff_time, reset_time)
                        else:
                            wait_time = backoff_time
                        
                        logger.warning(f"速率限制触发: {func_name}, 等待 {wait_time:.2f}s (第{attempt + 1}次尝试)")
                        logger.info(f"📊 API调用统计: {func_name} - 重试第{attempt + 1}次, 累计等待时间: {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"速率限制重试次数耗尽: {func_name}")
                        raise RateLimitError(f"API调用频率过高，请稍后重试: {str(e)}")
                
                except (tweepy.Forbidden, tweepy.Unauthorized, tweepy.BadRequest) as e:
                    # 这些错误不应该重试
                    logger.error(f"API请求错误 (不重试): {func_name} - {e}")
                    raise TwitterAPIError(f"API请求失败: {str(e)}")
                
                except Exception as e:
                    last_exception = e
                    if attempt < self.config.rate_limit_max_retries:
                        # 对于其他异常，也尝试重试
                        backoff_time = self.config.rate_limit_min_interval * (self.config.rate_limit_backoff_factor ** attempt)
                        logger.warning(f"请求失败，将重试: {func_name} - {e}, 等待 {backoff_time:.2f}s")
                        await asyncio.sleep(backoff_time)
                    else:
                        logger.error(f"请求重试次数耗尽: {func_name} - {e}")
                        raise TwitterAPIError(f"请求失败: {str(e)}")
            
            # 如果所有重试都失败了
            if last_exception:
                raise last_exception
        
        return wrapper

# 全局速率限制器实例
_rate_limiter = None

def get_rate_limiter(config=None):
    """获取速率限制器实例（单例模式）"""
    global _rate_limiter
    if _rate_limiter is None and config is not None:
        _rate_limiter = RateLimiter(config)
    return _rate_limiter

def rate_limit_handler(func: Callable) -> Callable:
    """速率限制装饰器（便捷函数）"""
    limiter = get_rate_limiter()
    if limiter is None:
        # 如果没有配置速率限制器，直接返回原函数
        logger.warning("速率限制器未初始化，跳过速率限制")
        return func
    
    return limiter.rate_limit_handler(func)