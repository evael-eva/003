#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据获取器 - 封装requests请求和HTML解析
功能：
1. 请求亚盘详情页 (handicap.aspx) 获取初盘和实时水位数据
2. 请求大小球详情页 (overunder.aspx) 获取初盘和实时水位数据
3. 使用BeautifulSoup解析HTML表格，提取赔率、盘口、状态等字段
4. 复用需求中提供的 _parse_asian_table 和 _parse_overunder_table 解析逻辑
5. v8新增: 支持代理池（账密认证模式）
"""

import time
import random
import requests
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from multiprocessing import cpu_count
from bs4 import BeautifulSoup


# v7新增: User-Agent池（多个浏览器版本，避免被识别）
USER_AGENT_POOL = [
    # Chrome Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
    
    # Chrome macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
    
    # Edge Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0',
    
    # Firefox Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
]

# 默认请求头模板（不含User-Agent，每次请求时动态设置）
DEFAULT_HEADERS_TEMPLATE = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Priority': 'u=0, i',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

# 亚盘请求的Referer
ASIAN_REFERER = 'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
# 大小球请求的Referer  
OU_REFERER = 'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}'

# 完整Cookie（从请求头文件中完整提取）
DEFAULT_COOKIE = (
    'b-user-id=a7f93b80-e642-0d71-94d1-1cc4576514c6; '
    'letgoalSettingSolution=; detailCookie=null; ishidepcad=; '
    'Hm_lvt_a88664a99dbcb9c7c07dc420114041b3=1773720401,1775723609; '
    'HMACCOUNT=DC1D86079E63CA12; '
    'Hm_lvt_3c285e4976a3c4fb2124b4d51dd1801e=1774270674,1775730459; '
    'totalSettingSolution=; '
    'Hm_lpvt_3c285e4976a3c4fb2124b4d51dd1801e=1776258084; '
    'Hm_lpvt_a88664a99dbcb9c7c07dc420114041b3=1776258394; '
    'xallpubLinkMatch=4f450e0644019ed94385423f0ce7ea1c157b9f21df0fb08df4bb91d57a5cc808'
    '4b024934ca5b6156b431345d9f235f950e6ef711de1ad4ea1b2e8e66f16e73ccfffbd80f53b1f2ed73850715dd19a5d704dc7fd9d1992b62a0c5f605bd89a271bb31123c8dbc8c2e8ec000e05ab07806101390c2ebc9d9cbe378bf3b73b8ae80b0350d14adc3aed05be42dc4b432be945686cab789b2191862bbd0a4a05e9865153af293e1e8b3f0536b27de15217ab66fa5d8fb83d51428b7b3cc8f9e36ac4b'
)


class OddsFetcher:
    """盘口数据获取器 - 请求亚盘/大小球详情页并解析数据"""

    def __init__(self, proxy_config=None):
        """
        初始化数据获取器
        :param proxy_config: 代理配置字典 {
            'enabled': bool,           # 是否启用代理
            'api_url': str,            # 代理API接口地址
            'extract_num': int,        # 每次提取数量
        }
        """
        self.session = requests.Session()
        
        # v12优化: 配置HTTP连接池，提高并发性能
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(
            pool_connections=30,   # 连接池大小（匹配最大并发数）
            pool_maxsize=30,       # 最大连接数
            max_retries=3          # 自动重试次数
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # v7优化: 使用模板请求头，不含固定的User-Agent
        self.session.headers.update(DEFAULT_HEADERS_TEMPLATE)
        if DEFAULT_COOKIE:
            self.session.headers.update({'Cookie': DEFAULT_COOKIE})
        # 预设公司ID (3 = 必发)
        self.company_id = 3
        
        # v11新增: 单IP轮换策略
        self.proxy_config = proxy_config
        self.current_proxy = None  # 当前使用的单个代理（格式: IP:端口）
        self.proxies = None  # requests库使用的代理字典
        self.proxy_start_time = None  # 代理开始使用时间（用于5分钟轮换）
        self.PROXY_ROTATE_INTERVAL = 600  # 代理轮换间隔（秒），默认10分钟
        self._request_count = 0  # 请求计数器
        
        # v12新增: 代理获取锁和防抖机制
        import threading
        self._proxy_lock = threading.Lock()  # 保护代理更新的线程锁
        self._last_fetch_time = 0  # 上次获取代理的时间戳
        self._fetch_cooldown = 2  # 获取代理的冷却时间（秒），防止频繁调用
        
        if proxy_config and proxy_config.get('enabled'):
            self._setup_single_proxy(proxy_config)
    
    @staticmethod
    def _get_random_user_agent():
        """v7新增: 从User-Agent池中随机选择一个"""
        return random.choice(USER_AGENT_POOL)
    
    def _setup_single_proxy(self, proxy_config):
        """v11新增: 设置单个代理（从API提取1个IP）"""
        try:
            api_url = proxy_config.get('api_url', '')
            
            print(f"[代理初始化] 开始设置单IP代理...")
            print(f"[代理初始化] API地址: {api_url[:60]}..." if len(api_url) > 60 else f"[代理初始化] API地址: {api_url}")
            
            if not api_url:
                print("[代理初始化] ❌ API地址为空，跳过代理设置")
                return
            
            # 从 API 提取1个代理
            print("[代理初始化] 正在从API提取1个代理IP...")
            proxies_list = self._extract_proxies_from_api(api_url, num=1)
            
            if not proxies_list:
                print("[代理初始化] ❌ API提取失败，未获取到代理")
                return
            
            # 使用第一个代理
            self.current_proxy = proxies_list[0]
            self._apply_current_proxy()
            self.proxy_start_time = time.time()
            
            print(f"[代理初始化] ✅ 成功启用代理: {self.current_proxy}")
            print(f"[代理初始化] ⏱️ 将在 {self.PROXY_ROTATE_INTERVAL} 秒后自动轮换")
        except Exception as e:
            print(f"[代理初始化] ❌ 设置失败: {e}")
            import traceback
            traceback.print_exc()
            self.current_proxy = None
            self.proxies = None
    
    def _extract_proxies_from_api(self, api_url, num=10):
        """v8新增: 从API提取代理IP列表"""
        try:
            # v8.3修复: 清理URL中的转义字符
            # 将字面的 \r\n 替换为空（有些用户会直接复制带转义的URL）
            api_url = api_url.replace('\\r\\n', '').replace('\\n', '').replace('\\r', '')
            
            # 如果URL中没有num参数，添加
            if 'num=' not in api_url:
                if '?' in api_url:
                    api_url += f"&num={num}"
                else:
                    api_url += f"?num={num}"
            else:
                # v8.3优化: 如果已有num参数，更新为指定的数量
                import re
                api_url = re.sub(r'num=\d+', f'num={num}', api_url)
            
            print(f"[代理API] 请求URL: {api_url[:100]}..." if len(api_url) > 100 else f"[代理API] 请求URL: {api_url}")
            
            response = requests.get(api_url, timeout=10)
            if response.status_code != 200:
                print(f"[代理API] ❌ HTTP错误: {response.status_code}")
                print(f"[代理API] 响应内容: {response.text[:200]}")
                return []
            
            # 解析返回的txt内容
            text = response.text.strip()
            if not text:
                print("[代理API] ⚠️ API返回内容为空")
                return []
            
            # v8修复: 有些API返回的格式是连续IP，需要用正则提取
            import re
            # 匹配 IP:端口 格式（端口2-5位数字）
            pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})'
            matches = re.findall(pattern, text)
            proxies = [f'{ip}:{port}' for ip, port in matches]
            
            # 去重
            valid_proxies = list(set(proxies))
            
            if valid_proxies:
                print(f"[代理API] ✅ 成功提取 {len(valid_proxies)} 个代理")
            else:
                print(f"[代理API] ⚠️ 未找到有效的IP:端口格式")
                print(f"[代理API] 原始返回: {text[:200]}")
            
            return valid_proxies
            
        except Exception as e:
            print(f"[代理API] ❌ 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _apply_current_proxy(self):
        """v11新增: 应用当前代理到requests"""
        if not self.current_proxy:
            self.proxies = None
            return
        
        # v11支持: 代理认证
        auth_username = self.proxy_config.get('auth_username', '') if self.proxy_config else ''
        auth_password = self.proxy_config.get('auth_password', '') if self.proxy_config else ''
        
        if auth_username and auth_password:
            proxy_url = f"http://{auth_username}:{auth_password}@{self.current_proxy}"
        else:
            proxy_url = f"http://{self.current_proxy}"
        
        self.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        
        auth_info = "(已认证)" if auth_username else "(无需认证)"
        print(f"[代理应用] ✅ 当前代理: {self.current_proxy} {auth_info}")
    
    def _rotate_proxy_if_needed(self):
        """v11新增: 检查是否需要轮换代理（5分钟或失效）"""
        if not self.current_proxy or not self.proxy_start_time:
            return False
        
        elapsed = time.time() - self.proxy_start_time
        if elapsed >= self.PROXY_ROTATE_INTERVAL:
            print(f"[代理轮换] ⏱️ 当前代理已使用 {int(elapsed)} 秒，达到轮换阈值 ({self.PROXY_ROTATE_INTERVAL} 秒)")
            self._fetch_new_proxy()
            return True
        
        return False
    
    def _fetch_new_proxy(self):
        """v12优化: 获取新代理（失效或轮换时调用）
        使用线程锁和防抖机制，避免并发请求导致频繁调用API
        """
        if not self.proxy_config or not self.proxy_config.get('enabled'):
            return False
        
        # v12新增: 使用线程锁保护，确保同一时间只有一个线程能获取代理
        with self._proxy_lock:
            # v12新增: 防抖检查 - 如果距离上次获取不足冷却时间，跳过
            current_time = time.time()
            elapsed = current_time - self._last_fetch_time
            if elapsed < self._fetch_cooldown:
                print(f"[代理获取] ⏱️ 距离上次获取仅{elapsed:.1f}秒，跳过（冷却时间{self._fetch_cooldown}秒）")
                return False
            
            api_url = self.proxy_config.get('api_url', '')
            
            print(f"[代理获取] 正在从API提取1个新代理...")
            proxies_list = self._extract_proxies_from_api(api_url, num=1)
            
            if proxies_list:
                old_proxy = self.current_proxy
                self.current_proxy = proxies_list[0]
                self._apply_current_proxy()
                self.proxy_start_time = time.time()
                self._last_fetch_time = time.time()  # v12新增: 记录获取时间
                
                print(f"[代理获取] ✅ 成功更换代理: {old_proxy} → {self.current_proxy}")
                print(f"[代理获取] ⏱️ 将在 {self.PROXY_ROTATE_INTERVAL} 秒后再次轮换")
                return True
            else:
                print(f"[代理获取] ❌ 失败！未能获取新代理，继续使用当前代理")
                self._last_fetch_time = time.time()  # v12新增: 即使失败也记录时间，避免频繁重试
                return False
    
    def _mark_proxy_failed(self, proxy_addr):
        """v11新增: 标记代理失效并立即获取新代理"""
        # 提取纯 IP:端口 部分
        if proxy_addr.startswith('http://'):
            proxy_addr = proxy_addr[7:]  # 去掉 http://
        
        if '@' in proxy_addr:
            proxy_addr = proxy_addr.split('@')[1]  # 去掉认证信息
        
        print(f"[代理失效] {proxy_addr} 已标记为失效")
        
        # v11策略: 立即获取新代理
        print(f"[代理失效] 正在获取新代理替换...")
        success = self._fetch_new_proxy()
        
        if not success:
            print(f"[代理失效] ⚠️ 获取新代理失败，将继续重试")
    

    
    def set_proxy(self, proxy_config):
        """v11新增: 动态设置代理"""
        self.proxy_config = proxy_config
        if proxy_config and proxy_config.get('enabled'):
            self._setup_single_proxy(proxy_config)
        else:
            self.current_proxy = None
            self.proxies = None
            self.proxy_start_time = None
            print("[代理] 已禁用")
    
    def get_proxies(self):
        """v8新增: 获取当前代理配置"""
        return self.proxies

    def set_cookie(self, cookie_str):
        """设置自定义Cookie"""
        if cookie_str:
            self.session.headers.update({'Cookie': cookie_str})

    def fetch_asian_odds(self, match_id):
        """
        获取亚盘详情数据
        :param match_id: 比赛ID
        :return: dict 包含 header(表头), rows(数据行列表), error(错误信息)
                 每行数据格式: [时间, 比分, 主队赔率, 盘口, 客队赔率, 变化时间, 状态]
        """
        url = f"https://vip.titan007.com/changeDetail/handicap.aspx?id={match_id}&companyID={self.company_id}&l=0"
        # v7优化: 每次请求使用随机User-Agent
        headers = dict(self.session.headers)
        headers['User-Agent'] = self._get_random_user_agent()
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        
        # v11优化: 检查是否需要轮换代理（5分钟或失效）
        self._rotate_proxy_if_needed()
        
        # 记录当前使用的代理
        current_proxy = self.current_proxy if self.current_proxy else '无代理'
        display_proxy = current_proxy
        if '@' in current_proxy:
            display_proxy = current_proxy.split('@')[1]  # 只显示 IP:PORT
        print(f"[请求开始] 比赛{match_id} - 使用代理: {display_proxy}")
        
        try:
            # v8新增: 添加代理支持
            response = self.session.get(url, timeout=15, headers=headers, proxies=self.proxies)
            if response.status_code != 200:
                print(f"[请求失败] 比赛{match_id} - HTTP {response.status_code} - 代理: {current_proxy}")
                return {'header': [], 'rows': [], 'error': f'HTTP {response.status_code}'}

            print(f"[请求成功] 比赛{match_id} - 代理: {current_proxy}")
            # 尝试gb2312解码，失败则用utf-8
            html_content = self._decode_response(response)
            return self._parse_asian_table(html_content, f"比赛{match_id}")

        except requests.exceptions.ProxyError as e:
            # v8新增: 代理错误，标记当前代理为失效
            print(f"[代理失效] 比赛{match_id} - 代理 {current_proxy} 失效: {str(e)}")
            self._mark_proxy_failed(current_proxy)
            return {'header': [], 'rows': [], 'error': f'代理错误: {str(e)}'}
        except requests.exceptions.Timeout:
            print(f"[请求超时] 比赛{match_id} - 代理: {current_proxy}")
            return {'header': [], 'rows': [], 'error': '请求超时'}
        except Exception as e:
            print(f"[请求异常] 比赛{match_id} - 代理: {current_proxy} - 错误: {str(e)}")
            return {'header': [], 'rows': [], 'error': str(e)}

    def fetch_overunder_odds(self, match_id):
        """
        获取大小球详情数据
        :param match_id: 比赛ID
        :return: dict 包含 header(表头), rows(数据行列表), error(错误信息)
                 每行数据格式: [时间, 比分, 大球赔率, 进球数(盘口), 小球赔率, 变化时间, 状态]
        """
        url = f"https://vip.titan007.com/changeDetail/overunder.aspx?id={match_id}&companyID={self.company_id}&l=0"
        # v7优化: 每次请求使用随机User-Agent
        headers = dict(self.session.headers)
        headers['User-Agent'] = self._get_random_user_agent()
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        
        # v11优化: 检查是否需要轮换代理
        self._rotate_proxy_if_needed()
        
        current_proxy = self.current_proxy if self.current_proxy else '无代理'
        # v11优化: 显示时去掉认证信息
        display_proxy = current_proxy.split('@')[1] if '@' in current_proxy else current_proxy
        print(f"[请求开始] 比赛{match_id}(大小球) - 使用代理: {display_proxy}")
        
        try:
            # v8新增: 添加代理支持
            response = self.session.get(url, timeout=15, headers=headers, proxies=self.proxies)
            if response.status_code != 200:
                print(f"[请求失败] 比赛{match_id}(大小球) - HTTP {response.status_code} - 代理: {current_proxy}")
                return {'header': [], 'rows': [], 'error': f'HTTP {response.status_code}'}

            print(f"[请求成功] 比赛{match_id}(大小球) - 代理: {current_proxy}")
            html_content = self._decode_response(response)
            return self._parse_overunder_table(html_content, f"比赛{match_id}")

        except requests.exceptions.ProxyError as e:
            print(f"[代理失效] 比赛{match_id}(大小球) - 代理 {current_proxy} 失效: {str(e)}")
            self._mark_proxy_failed(current_proxy)
            return {'header': [], 'rows': [], 'error': f'代理错误: {str(e)}'}
        except requests.exceptions.Timeout:
            print(f"[请求超时] 比赛{match_id}(大小球) - 代理: {current_proxy}")
            return {'header': [], 'rows': [], 'error': '请求超时'}
        except Exception as e:
            print(f"[请求异常] 比赛{match_id}(大小球) - 代理: {current_proxy} - 错误: {str(e)}")
            return {'header': [], 'rows': [], 'error': str(e)}

    def fetch_initial_odds(self, match_id):
        """
        获取一场比赛的亚盘+大小球初盘数据（取最后一行即行作为初盘）
        :param match_id: 比赛ID
        :return: {
            'asian_initial': {'home_odds', 'handicap', 'away_odds', ...},
            'ou_initial': {'over_odds', 'goal_line', 'under_odds', ...},
            'error': str or None
        }
        """
        result = {
            'asian_initial': None,
            'ou_initial': None,
            'asian_rows': [],
            'ou_rows': [],
            'error': None,
        }

        # 获取亚盘
        asian_data = self.fetch_asian_odds(match_id)
        if asian_data.get('error'):
            result['error'] = f"亚盘: {asian_data['error']}"
        else:
            result['asian_rows'] = asian_data.get('rows', [])
            if asian_data['rows']:
                # 初盘 = 表格最后一行（最早的数据）
                initial_row = asian_data['rows'][-1]
                result['asian_initial'] = self._extract_asian_row(initial_row)

        # 获取大小球
        ou_data = self.fetch_overunder_odds(match_id)
        if ou_data.get('error'):
            err = result.get('error', '')
            result['error'] = f"{err}; 大小球: {ou_data['error']}" if err else f"大小球: {ou_data['error']}"
        else:
            result['ou_rows'] = ou_data.get('rows', [])
            if ou_data['rows']:
                initial_row = ou_data['rows'][-1]
                result['ou_initial'] = self._extract_ou_row(initial_row)

        # v2优化: 减少延迟，提高并发效率
        time.sleep(random.uniform(0.1, 0.2))

        return result

    def fetch_half_time_initial(self, match_id):
        """
        获取半场亚盘和大小球初盘数据（使用 changeDetail/handicapHalf.aspx 和 overunderHalf.aspx）
        :param match_id: 比赛ID
        :return: {
            'asian_half_initial': {'home_odds', 'handicap', 'away_odds', ...},
            'ou_half_initial': {'over_odds', 'goal_line', 'under_odds', ...},
            'error': str or None
        }
        """
        result = {
            'asian_half_initial': None,
            'ou_half_initial': None,
            'error': None,
        }

        # 获取半场亚盘
        asian_half_url = f"https://vip.titan007.com/changeDetail/handicapHalf.aspx?id={match_id}&companyID={self.company_id}&h=1&l=0"
        # v7优化: 每次请求使用随机User-Agent
        headers = dict(self.session.headers)
        headers['User-Agent'] = self._get_random_user_agent()
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        
        current_proxy = self.proxies.get('http', '无代理') if self.proxies else '无代理'
        # v8.4优化: 显示时去掉认证信息
        display_proxy = current_proxy.split('@')[1] if '@' in current_proxy else current_proxy
        print(f"[请求开始] 比赛{match_id}(半场亚盘) - 使用代理: {display_proxy}")
        
        try:
            # v8新增: 添加代理支持
            response = self.session.get(asian_half_url, timeout=15, headers=headers, proxies=self.proxies)
            if response.status_code == 200:
                print(f"[请求成功] 比赛{match_id}(半场亚盘) - 代理: {current_proxy}")
                html_content = self._decode_response(response)
                parsed = self._parse_asian_table(html_content, f"半场亚盘{match_id}")
                if not parsed.get('error') and parsed.get('rows'):
                    # 取最后一行作为初盘
                    initial_row = parsed['rows'][-1]
                    result['asian_half_initial'] = self._extract_asian_row(initial_row)
            else:
                print(f"[请求失败] 比赛{match_id}(半场亚盘) - HTTP {response.status_code} - 代理: {current_proxy}")
                result['error'] = f"半场亚盘 HTTP {response.status_code}"
        except requests.exceptions.ProxyError as e:
            print(f"[代理失效] 比赛{match_id}(半场亚盘) - 代理 {current_proxy} 失效: {str(e)}")
            self._mark_proxy_failed(current_proxy)
            result['error'] = f"半场亚盘代理错误: {str(e)}"
        except Exception as e:
            print(f"[请求异常] 比赛{match_id}(半场亚盘) - 代理: {current_proxy} - 错误: {str(e)}")
            result['error'] = f"半场亚盘: {str(e)}"

        # 短暂延迟
        time.sleep(random.uniform(0.1, 0.15))

        # 获取半场大小球
        ou_half_url = f"https://vip.titan007.com/changeDetail/overunderHalf.aspx?id={match_id}&companyID={self.company_id}&h=1&l=0"
        # v7优化: 复用已设置的headers（包含随机User-Agent）
        
        current_proxy = self.proxies.get('http', '无代理') if self.proxies else '无代理'
        # v8.4优化: 显示时去掉认证信息
        display_proxy = current_proxy.split('@')[1] if '@' in current_proxy else current_proxy
        print(f"[请求开始] 比赛{match_id}(半场大小球) - 使用代理: {display_proxy}")
        
        try:
            # v8新增: 添加代理支持
            response = self.session.get(ou_half_url, timeout=15, headers=headers, proxies=self.proxies)
            if response.status_code == 200:
                print(f"[请求成功] 比赛{match_id}(半场大小球) - 代理: {current_proxy}")
                html_content = self._decode_response(response)
                parsed = self._parse_overunder_table(html_content, f"半场大小球{match_id}")
                if not parsed.get('error') and parsed.get('rows'):
                    # 取最后一行作为初盘
                    initial_row = parsed['rows'][-1]
                    result['ou_half_initial'] = self._extract_ou_row(initial_row)
            else:
                print(f"[请求失败] 比赛{match_id}(半场大小球) - HTTP {response.status_code} - 代理: {current_proxy}")
                err = result.get('error', '')
                result['error'] = f"{err}; 半场大小球 HTTP {response.status_code}" if err else f"半场大小球 HTTP {response.status_code}"
        except requests.exceptions.ProxyError as e:
            print(f"[代理失效] 比赛{match_id}(半场大小球) - 代理 {current_proxy} 失效: {str(e)}")
            self._mark_proxy_failed(current_proxy)
            err = result.get('error', '')
            result['error'] = f"{err}; 半场大小球代理错误: {str(e)}" if err else f"半场大小球代理错误: {str(e)}"
        except Exception as e:
            print(f"[请求异常] 比赛{match_id}(半场大小球) - 代理: {current_proxy} - 错误: {str(e)}")
            err = result.get('error', '')
            result['error'] = f"{err}; 半场大小球: {str(e)}" if err else f"半场大小球: {str(e)}"

        # 短暂延迟
        time.sleep(random.uniform(0.1, 0.15))

        return result

    def fetch_latest_odds(self, match_id):
        """
        v12优化: 获取最新实时盘口数据（取第一行数据作为最新值）
        :return: 同 fetch_initial_odds 格式，新增 half_time_score 字段
        """
        result = {
            'asian_latest': None,
            'ou_latest': None,
            'asian_rows': [],
            'ou_rows': [],
            'half_time_score': None,  # v12新增: 半场比分
            'error': None,
        }

        asian_data = self.fetch_asian_odds(match_id)
        if not asian_data.get('error') and asian_data.get('rows'):
            result['asian_rows'] = asian_data['rows']
            latest = asian_data['rows'][0]  # 第一行是最新的
            result['asian_latest'] = self._extract_asian_row(latest)
            
            # v12新增: 提取半场比分
            half_time_score = self._extract_half_time_score(asian_data['rows'])
            if half_time_score:
                result['half_time_score'] = half_time_score

        ou_data = self.fetch_overunder_odds(match_id)
        if not ou_data.get('error') and ou_data.get('rows'):
            result['ou_rows'] = ou_data['rows']
            latest = ou_data['rows'][0]  # 第一行是最新的
            result['ou_latest'] = self._extract_ou_row(latest)

        time.sleep(random.uniform(0.1, 0.2))
        return result

    @staticmethod
    def _decode_response(response):
        """解码响应内容，处理gb2312/gbk/utf-8编码（ titan007 返回 gb2312 编码）"""
        raw_bytes = response.content

        # 1. 先尝试从content-type获取编码
        content_type = response.headers.get('content-type', '').lower()

        if 'gb2312' in content_type or 'gbk' in content_type:
            return raw_bytes.decode('gb2312', errors='ignore')
        if 'utf-8' in content_type or 'utf8' in content_type:
            return raw_bytes.decode('utf-8', errors='ignore')

        # 2. 尝试常见中文编码（按优先级）
        encodings_to_try = ['utf-8', 'gb2312', 'gbk', 'iso-8859-1', 'big5']
        for enc in encodings_to_try:
            try:
                text = raw_bytes.decode(enc, errors='strict')
                # 简单验证：如果能正常解码且包含合理字符则使用该编码
                if len(text) > 50 and ('<' in text or '\u4e00' <= ''.join(filter(str.isalpha, text[:100]))):
                    return text
                decoded = raw_bytes.decode(enc, errors='ignore')
                if decoded.strip():  # 有实际内容
                    return decoded
            except (UnicodeDecodeError, LookupError):
                continue

        # 3. 最终回退：用gb2312忽略错误解码（titan007最常用）
        return raw_bytes.decode('gb2312', errors='ignore')

    @staticmethod
    def _extract_asian_row(row_data):
        """从解析后的亚盘行中提取结构化数据"""
        if len(row_data) >= 5:
            return {
                'time': row_data[0] if len(row_data) > 0 else '',
                'score': row_data[1] if len(row_data) > 1 else '',
                'home_odds': row_data[2] if len(row_data) > 2 else '',
                'handicap': row_data[3] if len(row_data) > 3 else '',
                'away_odds': row_data[4] if len(row_data) > 4 else '',
                'change_time': row_data[5] if len(row_data) > 5 else '',
                'status': row_data[6] if len(row_data) > 6 else '',
            }
        return {}

    @staticmethod
    def _convert_handicap_to_number(handicap_str):
        """
        将带/的盘口格式转换为纯数字
        例如: '2/2.5' -> 2.25, '2.5/3' -> 2.75, '1.5/2' -> 1.75
        :param handicap_str: 原始盘口字符串
        :return: 转换后的浮点数
        """
        if not handicap_str or not isinstance(handicap_str, str):
            return None
        
        handicap_str = handicap_str.strip()
        
        # 如果已经是纯数字，直接返回
        try:
            return float(handicap_str)
        except ValueError:
            pass
        
        # 处理带/的格式
        if '/' in handicap_str:
            parts = handicap_str.split('/')
            if len(parts) == 2:
                try:
                    lower = float(parts[0])
                    upper = float(parts[1])
                    # 返回中间值
                    return (lower + upper) / 2
                except ValueError:
                    return None
        
        return None

    @staticmethod
    def _extract_ou_row(row_data):
        """从解析后的大小球行中提取结构化数据"""
        if len(row_data) >= 5:
            goal_line_raw = row_data[3] if len(row_data) > 3 else ''
            # v2优化: 将带/的盘口格式转换为纯数字
            handicap_value = OddsFetcher._convert_handicap_to_number(goal_line_raw)
            
            return {
                'time': row_data[0] if len(row_data) > 0 else '',
                'score': row_data[1] if len(row_data) > 1 else '',
                'over_odds': row_data[2] if len(row_data) > 2 else '',
                'goal_line': goal_line_raw,  # 原始文本
                'handicap': str(handicap_value) if handicap_value is not None else goal_line_raw,  # 转换后的数字
                'under_odds': row_data[4] if len(row_data) > 4 else '',
                'change_time': row_data[5] if len(row_data) > 5 else '',
                'status': row_data[6] if len(row_data) > 6 else '',
            }
        return {}

    @staticmethod
    def _parse_asian_table(html, company_name=''):
        """
        解析亚盘变化表格HTML（复用需求中的解析逻辑）
        表头: 时间 | 比分 | 主队 | 盘口 | 客队 | 变化时间 | 状态
        数据行: 分钟 | 比分 | 主赔 | 盘口文本 | 客赔 | 时间 | 状态(滚/即)
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = None

            odds_span = soup.find('span', id='odds2')
            if odds_span:
                table = odds_span.find('table')

            if not table:
                tables = soup.find_all('table')
                for t in tables:
                    if len(t.find_all('tr')) > 3:
                        table = t
                        break

            if not table:
                return {'header': [], 'rows': [], 'error': '未找到亚盘表格'}

            rows = table.find_all('tr')
            if len(rows) < 2:
                return {'header': [], 'rows': [], 'error': '表格行数不足'}

            header_row = rows[0]
            headers = []
            for td in header_row.find_all(['td', 'th']):
                text = td.get_text(strip=True)
                headers.append(text if text else '')

            if all(h == '' for h in headers):
                headers = ['时间', '比分', '主队', '盘口', '客队', '变化时间', '状态']

            data_rows = []
            for row in rows[1:]:
                tds = row.find_all('td')
                if len(tds) < 5:
                    continue

                row_data = []
                has_data = False
                status_value = ''

                for idx, td in enumerate(tds):
                    b_tag = td.find('b')
                    if b_tag:
                        text = b_tag.get_text(strip=True)
                    else:
                        text = td.get_text(strip=True)

                    td_class = td.get('class', [])
                    td_class_str = ' '.join(td_class) if isinstance(td_class, list) else str(td_class)

                    if 'hg_red' in td_class_str:
                        status_value = '即'
                    elif 'hg_blue' in td_class_str:
                        status_value = '滚'
                    elif 'hg_green' in td_class_str:
                        if text == '封':
                            status_value = '封'
                        elif not status_value:
                            status_value = '未知'

                    row_data.append(text)
                    if text and text != '封':
                        has_data = True

                if row_data and len(row_data) >= 7:
                    if not row_data[-1] or row_data[-1] in ['', ' ']:
                        row_data[-1] = status_value if status_value else ''
                elif row_data and status_value and len(row_data) >= 6:
                    while len(row_data) < 7:
                        row_data.append('')
                    if len(row_data) >= 7:
                        row_data[6] = status_value

                if has_data and row_data:
                    data_rows.append(row_data)

            return {'header': headers, 'rows': data_rows}

        except Exception as e:
            print(f"[亚盘解析] 异常: {e}")
            return {'header': [], 'rows': [], 'error': str(e)}
    
    @staticmethod
    def _extract_half_time_score(data_rows):
        """
        v12新增: 从数据行中提取半场比分
        查找时间列为“中场”的行，获取其比分
        :param data_rows: 解析后的数据行列表
        :return: 半场比分字符串（如 "0-1"），如果未找到则返回 None
        """
        if not data_rows:
            return None
        
        for row in data_rows:
            if len(row) >= 2:
                time_col = row[0]  # 第1列是时间
                score_col = row[1]  # 第2列是比分
                
                # 查找时间列为“中场”的行
                if time_col == '中场' or time_col == 'HT' or time_col == 'Half':
                    return score_col
        
        return None

    @staticmethod
    def _parse_overunder_table(html, company_name=''):
        """
        解析大小球变化表格HTML（复用需求中的解析逻辑）
        表头: 时间 | 比分 | 大球 | 进球数 | 小球 | 变化时间 | 状态
        数据行: 分钟 | 比分 | 大球赔率 | 进球数(盘口) | 小球赔率 | 时间 | 状态(滚/即)
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = None

            odds_span = soup.find('span', id='odds2')
            if odds_span:
                table = odds_span.find('table')

            if not table:
                tables = soup.find_all('table') if hasattr(soup, 'find_all') else []
                for t in tables:
                    if len(t.find_all('tr')) > 3:
                        table = t
                        break

            if not table:
                return {'header': [], 'rows': [], 'error': '未找到大小球表格'}

            rows = table.find_all('tr')
            if len(rows) < 2:
                return {'header': [], 'rows': [], 'error': '表格行数不足'}

            header_row = rows[0]
            headers = []
            for td in header_row.find_all(['td', 'th']):
                text = td.get_text(strip=True)
                headers.append(text if text else '')

            if all(h == '' for h in headers):
                headers = ['时间', '比分', '大球', '进球数', '小球', '变化时间', '状态']

            data_rows = []
            for row in rows[1:]:
                tds = row.find_all('td')
                if len(tds) < 5:
                    continue

                row_data = []
                has_data = False
                status_value = ''

                for idx, td in enumerate(tds):
                    b_tag = td.find('b')
                    if b_tag:
                        text = b_tag.get_text(strip=True)
                    else:
                        text = td.get_text(strip=True)

                    td_class = td.get('class', [])
                    td_class_str = ' '.join(td_class) if isinstance(td_class, list) else str(td_class)

                    if 'hg_red' in td_class_str:
                        status_value = '即'
                    elif 'hg_blue' in td_class_str:
                        status_value = '滚'
                    elif 'hg_green' in td_class_str:
                        if text == '封':
                            status_value = '封'
                        elif not status_value:
                            status_value = '未知'

                    row_data.append(text)
                    if text and text != '封':
                        has_data = True

                if row_data and len(row_data) >= 7:
                    if not row_data[-1] or row_data[-1] in ['', ' ']:
                        row_data[-1] = status_value if status_value else ''
                elif row_data and status_value and len(row_data) >= 6:
                    while len(row_data) < 7:
                        row_data.append('')
                    if len(row_data) >= 7:
                        row_data[6] = status_value

                if has_data and row_data:
                    data_rows.append(row_data)

            return {'header': headers, 'rows': data_rows}

        except Exception as e:
            print(f"[大小球解析] 异常: {e}")
            return {'header': [], 'rows': [], 'error': str(e)}

    def batch_fetch_initial(self, match_ids, max_retries=2):
        """
        v13优化: 批量获取多场比赛的初盘数据（带重试机制）
        :param match_ids: 比赛ID列表
        :param max_retries: 最大重试次数（默认2次）
        :return: {match_id: result_dict}
        """
        results = {}
        if not match_ids:
            return results

        # v2优化: 提高并发数至15，加快批量获取速度
        max_workers = min(len(match_ids), 15)  # 最多15个并发（原8个）
        
        def _fetch_one_with_retry(match_id):
            """v13新增: 带重试机制的单个比赛获取"""
            last_error = None
            for attempt in range(max_retries + 1):  # 首次 + 重试次数
                try:
                    result = self.fetch_initial_odds(match_id)
                    if not result.get('error'):
                        return match_id, result  # 成功则返回
                    
                    # 记录错误，准备重试
                    last_error = result.get('error', '未知错误')
                    if attempt < max_retries:
                        time.sleep(random.uniform(0.5, 1.0))  # 重试前等待
                        
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries:
                        time.sleep(random.uniform(0.5, 1.0))  # 重试前等待
            
            # 所有尝试都失败
            return match_id, {'error': f'重试{max_retries}次后仍失败: {last_error}'}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one_with_retry, mid): mid for mid in match_ids}
            for future in futures:
                try:
                    mid, result = future.result(timeout=60)  # v13优化: 增加超时时间至60秒
                    results[mid] = result
                except Exception as e:
                    mid = futures[future]
                    results[mid] = {'error': f'线程超时或异常: {str(e)}'}

        return results

    def batch_fetch_latest(self, match_ids):
        """
        批量获取多场比赛的最新实时盘口数据（多线程并发）
        :param match_ids: 比赛ID列表
        :return: {match_id: result_dict}
        """
        results = {}
        if not match_ids:
            return results

        # v2优化: 提高并发数至15
        max_workers = min(len(match_ids), 15)

        def _fetch_one(match_id):
            return match_id, self.fetch_latest_odds(match_id)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, mid): mid for mid in match_ids}
            for future in futures:
                try:
                    mid, result = future.result(timeout=30)
                    results[mid] = result
                except Exception as e:
                    mid = futures[future]
                    results[mid] = {'error': str(e)}

        return results

    def batch_fetch_half_time_initial(self, match_ids, max_retries=2):
        """
        v13新增: 批量获取多场比赛的半场初盘数据（带重试机制）
        :param match_ids: 比赛ID列表
        :param max_retries: 最大重试次数（默认2次）
        :return: {match_id: result_dict}
        """
        results = {}
        if not match_ids:
            return results

        # 使用较低的并发数，避免对服务器造成过大压力
        max_workers = min(len(match_ids), 10)
        
        def _fetch_half_with_retry(match_id):
            """v13新增: 带重试机制的半场初盘获取"""
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = self.fetch_half_time_initial(match_id)
                    if not result.get('error'):
                        return match_id, result
                    
                    last_error = result.get('error', '未知错误')
                    if attempt < max_retries:
                        time.sleep(random.uniform(0.5, 1.0))
                        
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries:
                        time.sleep(random.uniform(0.5, 1.0))
            
            return match_id, {'error': f'重试{max_retries}次后仍失败: {last_error}'}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_half_with_retry, mid): mid for mid in match_ids}
            for future in futures:
                try:
                    mid, result = future.result(timeout=60)
                    results[mid] = result
                except Exception as e:
                    mid = futures[future]
                    results[mid] = {'error': f'线程超时或异常: {str(e)}'}

        return results

    @staticmethod
    def parse_local_html_file(filepath, table_type='overunder'):
        """
        解析本地保存的HTML文件（用于调试和验证解析逻辑）
        :param filepath: HTML文件路径
        :param table_type: 'asian' 或 'overunder'
        :return: dict {header, rows, error}
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            if table_type == 'asian':
                return OddsFetcher._parse_asian_table(html_content, f"本地文件:{filepath}")
            else:
                return OddsFetcher._parse_overunder_table(html_content, f"本地文件:{filepath}")
        except FileNotFoundError:
            return {'header': [], 'rows': [], 'error': f'文件不存在: {filepath}'}
        except Exception as e:
            return {'header': [], 'rows': [], 'error': str(e)}
