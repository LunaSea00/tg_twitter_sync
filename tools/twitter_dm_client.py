#!/usr/bin/env python3
"""
完整的 Twitter 私信客户端脚本，使用 OAuth2 PKCE 获取 Token，获取对话列表并发送私信
基于提供的脚本，与现有项目架构集成
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
from src.twitter.client import TwitterClient
from src.config.settings import get_config
from dotenv import load_dotenv

# ======= 配置区 =======
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

ACCESS_TOKEN = None
twitter_client = None

# ======= 主程序逻辑 =======
async def main():
    global ACCESS_TOKEN, twitter_client
    
    try:
        # 加载配置
        load_dotenv()
        config = get_config()
        
        CLIENT_ID = os.getenv("TWITTER_CLIENT_ID") or config.twitter_oauth2_client_id
        if not CLIENT_ID:
            print("❌ 请先设置 TWITTER_CLIENT_ID 或 TWITTER_OAUTH2_CLIENT_ID 环境变量")
            return

        # 检查是否已有访问令牌
        if config.twitter_user_access_token:
            print("✅ 发现已有访问令牌，直接使用")
            ACCESS_TOKEN = config.twitter_user_access_token
        else:
            # 初始化OAuth处理器
            oauth = TwitterOAuth2(
                client_id=CLIENT_ID,
                client_secret=config.twitter_oauth2_client_secret or '',
                redirect_uri=config.twitter_redirect_uri or "http://localhost:8080/callback"
            )
            
            print("🔐 开始Twitter OAuth 2.0授权流程...")
            try:
                # 使用自动授权流程
                token_data = oauth.complete_authorization_flow(
                    scopes=['dm.read', 'dm.write', 'tweet.read', 'users.read', 'offline.access'],
                    auto_open_browser=True,
                    port=8080
                )
                ACCESS_TOKEN = token_data['access_token']
                
                # 保存令牌到配置
                from dotenv import set_key
                env_file = project_root / '.env'
                set_key(str(env_file), 'TWITTER_USER_ACCESS_TOKEN', ACCESS_TOKEN)
                if 'refresh_token' in token_data:
                    set_key(str(env_file), 'TWITTER_USER_REFRESH_TOKEN', token_data['refresh_token'])
                
                print("✅ 访问令牌已保存到 .env 文件")
                
            except Exception as e:
                print(f"❌ 授权失败: {e}")
                return

        # 初始化Twitter客户端
        credentials = {
            'bearer_token': config.twitter_credentials['bearer_token'],
            'consumer_key': config.twitter_credentials['consumer_key'],
            'consumer_secret': config.twitter_credentials['consumer_secret'],
            'access_token': config.twitter_credentials['access_token'],
            'access_token_secret': config.twitter_credentials['access_token_secret'],
            'oauth2_client_id': config.twitter_oauth2_client_id,
            'oauth2_client_secret': config.twitter_oauth2_client_secret,
            'redirect_uri': config.twitter_redirect_uri,
            'user_access_token': ACCESS_TOKEN
        }
        
        twitter_client = TwitterClient(credentials)

        print("✅ Twitter客户端初始化成功！")

        # 测试DM API访问权限
        print("🔍 测试DM API访问权限...")
        if await twitter_client.test_dm_access():
            print("✅ DM API权限测试成功")
        else:
            print("❌ DM API权限测试失败")
            return

        # 获取历史 DM 对话
        print("📩 获取历史 DM 对话...")
        try:
            conversations_result = await twitter_client.get_dm_conversations()
            conversations = conversations_result.get('data', [])
            
            if conversations:
                print(f"📋 找到 {len(conversations)} 个对话:")
                for idx, conv in enumerate(conversations):
                    conv_id = conv['dm_conversation_id']
                    participants = conv.get('participants', [])
                    participant_names = [p.get('username', p.get('name', 'Unknown')) for p in participants]
                    print(f"  {idx+1}. {conv_id} - 参与者: {', '.join(participant_names)}")
                
                # 演示：向第一个对话发送测试消息
                if len(conversations) > 0:
                    conv_id = conversations[0]['dm_conversation_id']
                    test_message = "Hello from Python bot! 🤖"
                    
                    print(f"\n📝 发送测试消息到对话 {conv_id}...")
                    try:
                        result = await twitter_client.send_dm_by_conversation_id(conv_id, test_message)
                        if result.get('success'):
                            print(f"✅ 消息发送成功: {result.get('dm_event_id')}")
                        else:
                            print(f"❌ 消息发送失败: {result}")
                    except Exception as e:
                        print(f"❌ 发送消息时出错: {e}")
                
                # 演示：获取最近的DM事件
                print("\n📬 获取最近的DM事件...")
                try:
                    dm_events = await twitter_client.get_all_dm_events(max_results=10)
                    events = dm_events.get('data', [])
                    print(f"📋 找到 {len(events)} 条最近的DM事件")
                    
                    for event in events[:3]:  # 只显示前3条
                        sender_id = event.get('sender_id')
                        text = event.get('text', '(无文本内容)')
                        created_at = event.get('created_at')
                        print(f"  - 发送者ID: {sender_id}")
                        print(f"    内容: {text[:50]}{'...' if len(text) > 50 else ''}")
                        print(f"    时间: {created_at}")
                        print()
                        
                except Exception as e:
                    print(f"❌ 获取DM事件时出错: {e}")
                    
            else:
                print("❌ 没有任何私信对话。请先手动和某人开始私信。")
                
        except Exception as e:
            print(f"❌ 获取对话时出错: {e}")

        print("\n🎉 DM客户端演示完成！")

    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 用户取消操作")
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        sys.exit(1)