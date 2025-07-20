#!/usr/bin/env python3
"""
Twitter OAuth 2.0 PKCE 授权设置工具

使用方法：
1. 在 .env 文件中设置 TWITTER_OAUTH2_CLIENT_ID 和 TWITTER_OAUTH2_CLIENT_SECRET
2. 运行此脚本: python tools/oauth_setup.py
3. 按照提示完成授权流程
4. 脚本会自动更新 .env 文件中的用户访问令牌
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.twitter.oauth import TwitterOAuth2
from src.config.settings import get_config
from dotenv import load_dotenv, set_key

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """主要的授权流程"""
    try:
        # 加载配置
        load_dotenv()
        config = get_config()
        
        if not config.twitter_oauth2_client_id:
            logger.error("请在 .env 文件中设置 TWITTER_OAUTH2_CLIENT_ID")
            return
        
        # 初始化 OAuth 处理器
        oauth = TwitterOAuth2(
            client_id=config.twitter_oauth2_client_id,
            client_secret=config.twitter_oauth2_client_secret or '',
            redirect_uri=config.twitter_redirect_uri
        )
        
        print("🔐 Twitter OAuth 2.0 PKCE 授权设置")
        print("=" * 50)
        
        # 询问用户是否使用自动授权流程
        use_auto_flow = input("🤖 是否使用自动授权流程？(y/n，默认y): ").strip().lower()
        use_auto_flow = use_auto_flow != 'n'
        
        if use_auto_flow:
            print("🚀 启动自动授权流程...")
            try:
                # 使用完整的自动授权流程
                token_data = oauth.complete_authorization_flow(
                    scopes=['dm.read', 'dm.write', 'tweet.read', 'users.read', 'offline.access'],
                    auto_open_browser=True,
                    port=8080
                )
            except Exception as e:
                print(f"❌ 自动授权流程失败: {e}")
                print("🔄 回退到手动授权流程...")
                use_auto_flow = False
        
        if not use_auto_flow:
            # 手动授权流程
            print("📋 使用手动授权流程...")
            
            # 生成授权 URL
            auth_url, state, code_verifier = oauth.get_authorization_url()
            
            print(f"📱 请在浏览器中打开以下链接进行授权：")
            print(f"\n{auth_url}\n")
            
            print("📋 授权完成后，你会被重定向到一个包含 'code' 参数的 URL")
            print("📋 请复制该 URL 中的 code 参数值")
            print("📋 例如: http://localhost:8080/callback?code=ABC123&state=XYZ")
            print("📋 你需要复制的是: ABC123")
            
            # 等待用户输入授权码
            authorization_code = input("\n🔑 请输入授权码 (code): ").strip()
            
            if not authorization_code:
                logger.error("授权码不能为空")
                return
            
            print("\n🔄 正在交换访问令牌...")
            
            # 交换访问令牌
            token_data = oauth.exchange_code_for_token(authorization_code, code_verifier)
        
        # 保存令牌到 .env 文件
        env_file = project_root / '.env'
        
        set_key(str(env_file), 'TWITTER_USER_ACCESS_TOKEN', token_data['access_token'])
        
        if 'refresh_token' in token_data:
            set_key(str(env_file), 'TWITTER_USER_REFRESH_TOKEN', token_data['refresh_token'])
        
        print("✅ 访问令牌已保存到 .env 文件")
        print(f"🔧 访问令牌类型: {token_data.get('token_type', 'bearer')}")
        print(f"🔧 权限范围: {token_data.get('scope', 'N/A')}")
        
        if 'expires_in' in token_data:
            print(f"⏰ 令牌过期时间: {token_data['expires_in']} 秒")
        
        if 'refresh_token' in token_data:
            print("🔄 刷新令牌已保存，可用于自动刷新访问令牌")
        
        print("\n🎉 OAuth 2.0 设置完成！现在可以使用 DM API 了")
        
    except KeyboardInterrupt:
        print("\n👋 用户取消操作")
    except Exception as e:
        logger.error(f"设置失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())