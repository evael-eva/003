#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据获取器 - 封装requests请求和HTML解析
功能：
1. 请求亚盘详情页 (handicap.aspx) 获取初盘和实时水位数据
2. 请求大小球详情页 (overunder.aspx) 获取初盘和实时水位数据
3. 使用BeautifulSoup解析HTML表格，提取赔率、盘口、状态等字段
4. 复用需求中提供的 _parse_asian_table 和 _parse_overunder_table 解析逻辑
"""

import time
import random
import requests
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from multiprocessing import cpu_count
from bs4 import BeautifulSoup


# 默认请求头（完整提取自亚盘/大小球请求头文件）
DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'zh,zh-TW;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Priority': 'u=0, i',
    'Sec-Ch-Ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
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

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if DEFAULT_COOKIE:
            self.session.headers.update({'Cookie': DEFAULT_COOKIE})
        # 预设公司ID (3 = 必发)
        self.company_id = 3

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
        headers = dict(self.session.headers)
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        try:
            response = self.session.get(url, timeout=15, headers=headers)
            if response.status_code != 200:
                return {'header': [], 'rows': [], 'error': f'HTTP {response.status_code}'}

            # 尝试gb2312解码，失败则用utf-8
            html_content = self._decode_response(response)
            return self._parse_asian_table(html_content, f"比赛{match_id}")

        except requests.exceptions.Timeout:
            return {'header': [], 'rows': [], 'error': '请求超时'}
        except Exception as e:
            return {'header': [], 'rows': [], 'error': str(e)}

    def fetch_overunder_odds(self, match_id):
        """
        获取大小球详情数据
        :param match_id: 比赛ID
        :return: dict 包含 header(表头), rows(数据行列表), error(错误信息)
                 每行数据格式: [时间, 比分, 大球赔率, 进球数(盘口), 小球赔率, 变化时间, 状态]
        """
        url = f"https://vip.titan007.com/changeDetail/overunder.aspx?id={match_id}&companyID={self.company_id}&l=0"
        headers = dict(self.session.headers)
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        try:
            response = self.session.get(url, timeout=15, headers=headers)
            if response.status_code != 200:
                return {'header': [], 'rows': [], 'error': f'HTTP {response.status_code}'}

            html_content = self._decode_response(response)
            return self._parse_overunder_table(html_content, f"比赛{match_id}")

        except requests.exceptions.Timeout:
            return {'header': [], 'rows': [], 'error': '请求超时'}
        except Exception as e:
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
        headers = dict(self.session.headers)
        headers['Referer'] = f'https://vip.titan007.com/AsianOdds_n.aspx?id={match_id}&l=0'
        
        try:
            response = self.session.get(asian_half_url, timeout=15, headers=headers)
            if response.status_code == 200:
                html_content = self._decode_response(response)
                parsed = self._parse_asian_table(html_content, f"半场亚盘{match_id}")
                if not parsed.get('error') and parsed.get('rows'):
                    # 取最后一行作为初盘
                    initial_row = parsed['rows'][-1]
                    result['asian_half_initial'] = self._extract_asian_row(initial_row)
            else:
                result['error'] = f"半场亚盘 HTTP {response.status_code}"
        except Exception as e:
            result['error'] = f"半场亚盘: {str(e)}"

        # 短暂延迟
        time.sleep(random.uniform(0.1, 0.15))

        # 获取半场大小球
        ou_half_url = f"https://vip.titan007.com/changeDetail/overunderHalf.aspx?id={match_id}&companyID={self.company_id}&h=1&l=0"
        
        try:
            response = self.session.get(ou_half_url, timeout=15, headers=headers)
            if response.status_code == 200:
                html_content = self._decode_response(response)
                parsed = self._parse_overunder_table(html_content, f"半场大小球{match_id}")
                if not parsed.get('error') and parsed.get('rows'):
                    # 取最后一行作为初盘
                    initial_row = parsed['rows'][-1]
                    result['ou_half_initial'] = self._extract_ou_row(initial_row)
            else:
                err = result.get('error', '')
                result['error'] = f"{err}; 半场大小球 HTTP {response.status_code}" if err else f"半场大小球 HTTP {response.status_code}"
        except Exception as e:
            err = result.get('error', '')
            result['error'] = f"{err}; 半场大小球: {str(e)}" if err else f"半场大小球: {str(e)}"

        # 短暂延迟
        time.sleep(random.uniform(0.1, 0.15))

        return result

    def fetch_latest_odds(self, match_id):
        """
        获取最新实时盘口数据（取第一行数据作为最新值）
        :return: 同 fetch_initial_odds 格式
        """
        result = {
            'asian_latest': None,
            'ou_latest': None,
            'asian_rows': [],
            'ou_rows': [],
            'error': None,
        }

        asian_data = self.fetch_asian_odds(match_id)
        if not asian_data.get('error') and asian_data.get('rows'):
            result['asian_rows'] = asian_data['rows']
            latest = asian_data['rows'][0]  # 第一行是最新的
            result['asian_latest'] = self._extract_asian_row(latest)

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

    def batch_fetch_initial(self, match_ids):
        """
        批量获取多场比赛的初盘数据（多进程+线程池并发，大幅提速）
        :param match_ids: 比赛ID列表
        :return: {match_id: result_dict}
        """
        results = {}
        if not match_ids:
            return results

        # v2优化: 提高并发数至15，加快批量获取速度
        max_workers = min(len(match_ids), 15)  # 最多15个并发（原8个）
        
        def _fetch_one(match_id):
            return match_id, self.fetch_initial_odds(match_id)

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
