import base64
import hashlib
import secrets
import urllib.parse
import logging
import requests
import webbrowser
import http.server
import socketserver
import threading
import time
from typing import Dict, Optional, Tuple
from ..utils.exceptions import TwitterAPIError

logger = logging.getLogger(__name__)

class TwitterOAuth2:
    """Twitter OAuth 2.0 PKCE 授权处理"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = "https://twitter.com/i/oauth2/authorize"
        self.token_url = "https://api.twitter.com/2/oauth2/token"
        
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """生成 PKCE code_verifier 和 code_challenge"""
        # 生成 code_verifier (43-128 字符，URL安全的base64)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # 生成 code_challenge (SHA256 hash 的 base64url 编码)
        digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def get_authorization_url(self, scopes: list = None) -> Tuple[str, str, str]:
        """
        获取授权URL
        返回: (authorization_url, state, code_verifier)
        """
        if scopes is None:
            scopes = ['dm.read', 'dm.write', 'tweet.read', 'users.read', 'offline.access']
        
        # 生成 state 和 PKCE 参数
        state = secrets.token_urlsafe(32)
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        # 构建授权URL参数
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        authorization_url = f"{self.auth_url}?{urllib.parse.urlencode(params)}"
        
        logger.info("生成授权URL成功")
        return authorization_url, state, code_verifier
    
    def exchange_code_for_token(self, code: str, code_verifier: str) -> Dict[str, str]:
        """
        用授权码交换访问令牌
        """
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            data = {
                'code': code,
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'code_verifier': code_verifier
            }
            
            # 如果有 client_secret，使用 Basic 认证
            if self.client_secret:
                auth = (self.client_id, self.client_secret)
                response = requests.post(self.token_url, headers=headers, data=data, auth=auth)
            else:
                response = requests.post(self.token_url, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("成功获取访问令牌")
                return token_data
            else:
                error_data = response.json()
                logger.error(f"获取访问令牌失败: {response.status_code} - {error_data}")
                raise TwitterAPIError(f"获取访问令牌失败: {error_data.get('error_description', '未知错误')}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"交换令牌时发生错误: {e}")
            raise TwitterAPIError(f"交换令牌失败: {e}")
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """
        刷新访问令牌
        """
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            data = {
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
                'client_id': self.client_id
            }
            
            # 如果有 client_secret，使用 Basic 认证
            if self.client_secret:
                auth = (self.client_id, self.client_secret)
                response = requests.post(self.token_url, headers=headers, data=data, auth=auth)
            else:
                response = requests.post(self.token_url, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("成功刷新访问令牌")
                return token_data
            else:
                error_data = response.json()
                logger.error(f"刷新访问令牌失败: {response.status_code} - {error_data}")
                raise TwitterAPIError(f"刷新访问令牌失败: {error_data.get('error_description', '未知错误')}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {e}")
            raise TwitterAPIError(f"网络错误: {e}")
        except Exception as e:
            logger.error(f"刷新令牌时发生错误: {e}")
            raise TwitterAPIError(f"刷新令牌失败: {e}")
    
    def wait_for_authorization_code(self, port: int = 8080, timeout: int = 300) -> Optional[str]:
        """
        启动本地服务器等待授权回调，自动获取授权码
        """
        code_holder = {}
        server_ready = threading.Event()
        
        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                
                if "code" in params:
                    code_holder["code"] = params["code"][0]
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(b'''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Twitter Authorization</title>
                    </head>
                    <body>
                        <h1>Twitter 授权成功！</h1>
                        <p>您可以关闭此窗口，返回应用程序。</p>
                    </body>
                    </html>
                    ''')
                    logger.info("成功接收到授权码")
                else:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(b'''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Twitter Authorization Error</title>
                    </head>
                    <body>
                        <h1>授权失败</h1>
                        <p>未收到有效的授权码，请重试。</p>
                    </body>
                    </html>
                    ''')
                    logger.error("未收到有效的授权码")
            
            def log_message(self, format, *args):
                pass  # 静默日志输出
        
        def start_server():
            try:
                with socketserver.TCPServer(("", port), CallbackHandler) as httpd:
                    server_ready.set()
                    logger.info(f"授权回调服务器启动在端口 {port}")
                    
                    start_time = time.time()
                    while time.time() - start_time < timeout:
                        httpd.handle_request()
                        if code_holder.get("code"):
                            break
                    
                    if not code_holder.get("code"):
                        logger.warning(f"等待授权超时 ({timeout}秒)")
                        
            except Exception as e:
                logger.error(f"启动回调服务器失败: {e}")
        
        # 在后台线程启动服务器
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()
        
        # 等待服务器启动
        server_ready.wait(timeout=10)
        
        return code_holder.get("code")
    
    def complete_authorization_flow(self, scopes: list = None, auto_open_browser: bool = True, port: int = 8080) -> Dict[str, str]:
        """
        完整的授权流程：生成URL -> 打开浏览器 -> 等待回调 -> 交换令牌
        """
        try:
            # 生成授权URL
            auth_url, state, code_verifier = self.get_authorization_url(scopes)
            
            logger.info("开始Twitter OAuth 2.0授权流程")
            print("🔗 授权链接:")
            print(auth_url)
            
            if auto_open_browser:
                print("🌐 正在打开浏览器...")
                webbrowser.open(auth_url)
            else:
                print("📋 请手动复制上述链接到浏览器中打开")
            
            print(f"🔄 等待授权回调 (在端口 {port})...")
            
            # 等待授权码
            code = self.wait_for_authorization_code(port=port)
            
            if not code:
                raise TwitterAPIError("未能获取授权码，授权失败")
            
            print("🔐 正在换取访问令牌...")
            
            # 交换访问令牌
            token_data = self.exchange_code_for_token(code, code_verifier)
            
            logger.info("授权流程完成")
            return token_data
            
        except Exception as e:
            logger.error(f"授权流程失败: {e}")
            raise TwitterAPIError(f"授权流程失败: {e}")