#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
筛选控制器 - 封装DrissionPage浏览器操作，完成盘口筛选流程
功能：
1. 访问 live.titan007.com 页面
2. 点击"盘*"按钮打开指数筛选弹窗
3. 亚盘初盘筛选：取消全选 → 勾选用户选择的盘口 → 确定
4. 大小球初盘筛选：切换到"进球数"tab → 取消原有 → 勾选用户选择 → 确定
5. 解析比赛列表数据返回
"""

import os
import time
import random
import re
import threading
from bs4 import BeautifulSoup

from DrissionPage import WebPage, ChromiumOptions


class FilterController:
    """盘口筛选控制器"""

    # 亚盘盘口选项映射（value属性 -> 中文名）
    ASIAN_HANDICAP_OPTIONS = {
        '-0.25': '平/半', '-0.5': '半球', '-0.75': '半/一', '-1': '一球',
        '-1.25': '一/球半', '-1.5': '球半', '-1.75': '球半/两', '-2': '两球',
        '-2.25': '两/两球半', '-2.75': '两球半/三', '-3': '三球',
        '-3.5': '三球半', '-5.25': '五/五球半',
        '0': '平手', '0.25': '平/半', '0.5': '半球', '0.75': '半/一',
        '1': '一球', '1.25': '一/球半', '1.5': '球半', '1.75': '球半/两',
        '2': '两球', '2.5': '两球半', '2.75': '两球半/三', '3.25': '三/三球半',
        '3.5': '三球半', '4.5': '四球半',
    }

    # 大小球盘口选项映射
    OVERUNDER_OPTIONS = {
        '1.75': '1.5/2', '2': '2', '2.25': '2/2.5', '2.5': '2.5',
        '2.75': '2.5/3', '3': '3', '3.25': '3/3.5', '3.5': '3.5',
        '3.75': '3.5/4', '4': '4', '4.25': '4/4.5', '4.5': '4.5',
        '4.75': '4.5/5', '5.25': '5/5.5', '6': '6',
    }

    def __init__(self):
        self.web_page = None
        self._running = False

    @staticmethod
    def get_chrome_path():
        """获取Chrome浏览器路径"""
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"D:\Program Files\Google\Chrome\Application\chrome.exe",
            f"{os.getcwd()}\\images\\Chrome\\chrome.exe"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            path = winreg.QueryValue(key, None)
            winreg.CloseKey(key)
            if os.path.exists(path):
                return path
        except:
            pass
        return None

    @staticmethod
    def _random_delay(min_s=0.5, max_s=1.5):
        """随机延时，模拟人类操作"""
        time.sleep(random.uniform(min_s, max_s))

    def create_browser(self, headless=False):
        """创建浏览器实例"""
        co = ChromiumOptions()
        chrome_path = self.get_chrome_path()
        co.headless(headless)
        co.auto_port(True)
        co.no_js(False)
        co.mute(True)  # 静音，避免干扰用户
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        ]
        co.set_user_agent(random.choice(user_agents))
        if chrome_path:
            co.set_browser_path(chrome_path)
        self.web_page = WebPage('d', chromium_options=co)

    def close_browser(self):
        """关闭浏览器"""
        if self.web_page:
            try:
                self.web_page.quit()
            except:
                pass
            finally:
                self.web_page = None

    def open_live_page(self):
        """打开7M完整列表页面"""
        if not self.web_page:
            self.create_browser(headless=True)
        url = "https://live.titan007.com/indexall.aspx"
        self.web_page.get(url)
        self._random_delay(2, 3)
        try:
            erheyi_btn = self.web_page.ele('xpath://*[@id="tools"]/ul/li[1]', timeout=5)
            if erheyi_btn:
                erheyi_btn.click()
                self._random_delay(0.5, 1)
        except Exception as e:
            print(f"[FilterController] 点击二合一按钮失败: {e}")
        # 点击完整按钮显示所有比赛（与参考文件一致：button6）
        try:
            complete_btn = self.web_page.ele('xpath://*[@id="button6"]', timeout=5)
            if complete_btn:
                complete_btn.click()
                self._random_delay(0.5, 1)
        except Exception as e:
            print(f"[FilterController] 点击完整按钮失败: {e}")

    def _click_goal_div_button(self):
        """点击'盘*'按钮打开指数筛选弹窗"""
        try:
            btn = self.web_page.ele('xpath://*[@id="button8"]', timeout=5)
            if btn:
                btn.click()
                time.sleep(2)
                print(f"[FilterController] 打开弹窗: ok")
                return True
        except Exception as e:
            print(f"[FilterController] 点击盘*按钮失败: {e}")
        return False

    def _ensure_asian_tab(self):
        """确保在亚让(radioGoalType0)tab"""
        try:
            radio = self.web_page.ele('xpath://input[@id="radioGoalType0"]', timeout=5)
            if radio:
                radio.click()
                time.sleep(1)
                print(f"[FilterController] 切换到亚让tab: ok")
                return True
        except Exception as e:
            print(f"[FilterController] 切换到亚让tab失败: {e}")
        return False

    def _switch_to_overunder_tab(self):
        """切换到大小球（进球数）tab"""
        try:
            radio = self.web_page.ele('xpath://input[@id="radioGoalType1"]', timeout=5)
            if radio:
                radio.click()
                time.sleep(1)
                print(f"[FilterController] 切换到进球数tab: ok")
                return True
        except Exception as e:
            print(f"[FilterController] 切换到进球数tab失败: {e}")
        return False

    def _uncheck_all_checkboxes(self):
        """兜底检查：确保所有checkbox未选中（默认就是未选中状态）"""
        try:
            checkboxes = self.web_page.eles(
                'xpath://div[@id="goalDiv"]//input[@type="checkbox" and @name="checkbox"]',
                timeout=5
            )
            unchecked = 0
            for cb in checkboxes:
                try:
                    if cb.states.is_checked:
                        cb.click()
                        unchecked += 1
                        time.sleep(0.05)
                except:
                    continue
            print(f"[FilterController] 兜底检查: {len(checkboxes)}个checkbox, 其中{unchecked}个已选中需取消")
        except Exception as e:
            print(f"[FilterController] 取消全选失败: {e}")

    def _check_selected_handicaps(self, selected_values):
        """勾选指定value的盘口复选框（通过value属性匹配）"""
        count = 0
        if not selected_values:
            print(f"[FilterController] 勾选盘口: selected_values为空")
            return count
        selected_set = set(selected_values)
        try:
            # 搜索范围必须是 #goalDiv（不是 #goalTable！）
            checkboxes = self.web_page.eles(
                'xpath://div[@id="goalDiv"]//input[@type="checkbox" and @name="checkbox"]',
                timeout=5
            )
            print(f"[FilterController] 勾选盘口: 找到{len(checkboxes)}个checkbox, 目标值={list(selected_set)}")

            # 诊断：打印前10个值
            page_samples = []
            for cb in checkboxes[:10]:
                try:
                    page_samples.append(cb.attr('value'))
                except:
                    page_samples.append('?')
            print(f"[FilterController] 页面值样本={page_samples}")

            matched = set()
            for cb in checkboxes:
                try:
                    val = cb.attr('value')
                    if val and val in selected_set:
                        matched.add(val)
                        if not cb.states.is_checked:
                            cb.click()
                            count += 1
                            time.sleep(0.15)
                except Exception:
                    continue

            not_found = selected_set - matched
            if not_found:
                print(f"[FilterController] 未找到的值={not_found}")
            print(f"[FilterController] 实际勾选{count}个")
            time.sleep(0.3)
        except Exception as e:
            print(f"[FilterController] 勾选盘口失败: {e}")
        return count

    def _click_confirm(self):
        """点击确定按钮"""
        try:
            confirm_btn = self.web_page.ele(
                'xpath://div[@id="selectGoals_div"]//input[@type="button" and @value="确定"]',
                timeout=5
            )
            if confirm_btn:
                confirm_btn.click()
                time.sleep(1)
                print(f"[FilterController] 点击确定: ok")
                return True
        except Exception as e:
            print(f"[FilterController] 点击确定失败: {e}")
        return False

    def filter_by_asian(self, selected_values):
        """
        执行亚盘初盘筛选
        :param selected_values: 用户勾选的亚盘value列表, 如 ['0', '0.25', '0.5', '0.75', '1']
          对应HTML中的value属性：平手=0, 平/半=0.25, 半球=0.5, 半/一=0.75, 一球=1 ...
        :return: 筛选后的比赛列表
        """
        matches = []
        try:
            # 1. 打开弹窗
            self._click_goal_div_button()

            # 2. 确保在亚让tab（radioGoalType0）
            self._ensure_asian_tab()

            # 3. 取消全选 → 勾选目标盘口 → 确定
            self._uncheck_all_checkboxes()
            checked_count = self._check_selected_handicaps(selected_values)
            print(f"[FilterController] 亚盘筛选: 已勾选 {checked_count} 个盘口")
            self._click_confirm()

            # 解析页面上的比赛
            matches = self._parse_match_list(source='亚盘')

        except Exception as e:
            print(f"[FilterController] 亚盘筛选异常: {e}")
        return matches

    def filter_by_overunder(self, selected_values):
        """
        执行大小球初盘筛选
        :param selected_values: 用户勾选的大小球value列表, 如 ['2.5', '2.75', '3']
        :return: 筛选后的比赛列表
        """
        matches = []
        try:
            # 打开弹窗
            self._click_goal_div_button()

            # 切换到进球数tab
            self._switch_to_overunder_tab()

            # 用反选+逐个 → 勾选用户选择 → 确定
            self._uncheck_all_checkboxes()
            checked_count = self._check_selected_handicaps(selected_values)
            print(f"[FilterController] 大小球筛选: 已勾选 {checked_count} 个盘口")
            self._click_confirm()

            # 解析页面上的比赛
            matches = self._parse_match_list(source='大小球')

        except Exception as e:
            print(f"[FilterController] 大小球筛选异常: {e}")
        return matches
    
    def get_all_matches(self):
        """
        v2新增: 获取当前页面的所有比赛（不进行任何筛选）
        :return: 所有比赛列表
        """
        matches = []
        try:
            # 直接解析当前页面的比赛列表，不进行任何筛选操作
            matches = self._parse_match_list(source='全部')
            self.log_signal.emit(f"[FilterController] 获取到 {len(matches)} 场比赛")
        except Exception as e:
            self.log_signal.emit(f"[FilterController] 获取所有比赛失败: {e}")
        return matches

    def filter_combined(self, asian_enabled, asian_values, ou_enabled, ou_values,
                       half_ou_enabled=False, half_ou_min=0.75, half_ou_max=1.5):
        """
        组合筛选：支持同时启用亚盘、大小球和半场大球初盘范围筛选，合并去重结果
        优化：当同时启用多种筛选时，使用多个独立浏览器并行执行，速度提升约50%
        :param half_ou_enabled: 是否启用半场大球初盘范围筛选
        :param half_ou_min: 半场大球初盘最小值
        :param half_ou_max: 半场大球初盘最大值
        :return: 比赛列表，每条记录带source标注来源
        """
        all_matches = {}

        # v2优化: 判断是否需要多浏览器并行（只考虑浏览器端筛选）
        # 注意：half_ou_enabled 是本地API筛选，不需要浏览器，不计入并行判断
        browser_filters = []
        if asian_enabled and asian_values:
            browser_filters.append('asian')
        if ou_enabled and ou_values:
            browser_filters.append('ou')
        
        need_parallel = len(browser_filters) >= 2

        if need_parallel:
            # ========== 双浏览器并行模式 ==========
            print("[FilterController] 启动双浏览器并行筛选...")
            asian_results = []
            ou_results = []
            asian_error = None
            ou_error = None

            def _run_asian():
                nonlocal asian_results, asian_error
                try:
                    ctrl_a = FilterController()
                    ctrl_a.open_live_page()
                    asian_results = ctrl_a.filter_by_asian(asian_values)
                    ctrl_a.close_browser()
                except Exception as e:
                    asian_error = str(e)

            def _run_ou():
                nonlocal ou_results, ou_error
                try:
                    ctrl_o = FilterController()
                    ctrl_o.open_live_page()
                    ou_results = ctrl_o.filter_by_overunder(ou_values)
                    ctrl_o.close_browser()
                except Exception as e:
                    ou_error = str(e)

            t1 = threading.Thread(target=_run_asian)
            t2 = threading.Thread(target=_run_ou)
            t1.start()
            t2.start()
            t1.join(timeout=120)  # 最多等2分钟
            t2.join(timeout=120)

            if asian_error:
                print(f"[FilterController] 亚盘线程异常: {asian_error}")
            if ou_error:
                print(f"[FilterController] 大小球线程异常: {ou_error}")

            # 合并亚盘结果
            for m in asian_results:
                mid = m.get('match_id', '')
                if mid and mid not in all_matches:
                    m['source'] = '亚盘'
                    all_matches[mid] = m
                elif mid and mid in all_matches:
                    existing = all_matches[mid]
                    sources = existing.get('sources', [existing.get('source', '')])
                    if '亚盘' not in sources:
                        sources.append('亚盘')
                    existing['sources'] = sources

            # 合并大小球结果
            for m in ou_results:
                mid = m.get('match_id', '')
                if mid and mid not in all_matches:
                    m['source'] = '大小球'
                    all_matches[mid] = m
                elif mid and mid in all_matches:
                    existing = all_matches[mid]
                    sources = existing.get('sources', [existing.get('source', '')])
                    if '大小球' not in sources:
                        sources.append('大小球')
                    existing['sources'] = sources

        else:
            # ========== 单浏览器串行模式（只启用了一种或都没启用）==========
            self.open_live_page()

            if asian_enabled and asian_values:
                asian_matches = self.filter_by_asian(asian_values)
                for m in asian_matches:
                    mid = m.get('match_id', '')
                    if mid and mid not in all_matches:
                        m['source'] = '亚盘'
                        all_matches[mid] = m
                    elif mid and mid in all_matches:
                        existing = all_matches[mid]
                        sources = existing.get('sources', [existing.get('source', '')])
                        if '亚盘' not in sources:
                            sources.append('亚盘')
                        existing['sources'] = sources

            if ou_enabled and ou_values:
                ou_matches = self.filter_by_overunder(ou_values)
                for m in ou_matches:
                    mid = m.get('match_id', '')
                    if mid and mid not in all_matches:
                        m['source'] = '大小球'
                        all_matches[mid] = m
                    elif mid and mid in all_matches:
                        existing = all_matches[mid]
                        sources = existing.get('sources', [existing.get('source', '')])
                        if '大小球' not in sources:
                            sources.append('大小球')
                        existing['sources'] = sources
            
            # v2优化: 如果没有启用任何浏览器筛选，但启用了半场大球初盘筛选
            # 需要获取所有比赛列表，供后续本地过滤使用
            if not asian_enabled and not ou_enabled and half_ou_enabled:
                self.log_signal.emit("[FilterController] 仅启用半场大球初盘筛选，获取所有比赛...")
                # 获取当前页面的所有比赛
                all_matches_list = self.get_all_matches()
                for m in all_matches_list:
                    mid = m.get('match_id', '')
                    if mid and mid not in all_matches:
                        m['source'] = '全部'
                        all_matches[mid] = m

        return list(all_matches.values())

    def _extract_minutes(self, status):
        """从状态字符串中提取分钟数"""
        try:
            if not status:
                return 0
            if status.isdigit():
                return int(status)
            elif '中' in status:
                return 45
            else:
                match_minute = re.search(r'(\d+)', status)
                if match_minute:
                    return int(match_minute.group(1))
            return 0
        except:
            return 0

    def _is_match_live(self, status):
        """判断比赛是否正在进行中（仅保留纯数字分钟数 + 中场的比赛）"""
        if not status or not status.strip():
            return False

        s = status.strip()

        # 纯数字 = 正在进行中的分钟数（如 "56", "3"）
        if s.isdigit():
            return True

        # "中" = 中场休息
        if s == '中':
            return True

        # 其他所有情况都不是正在比赛（完场、未开、推迟等）
        return False

    def _parse_match_list(self, source='未指定'):
        """解析当前页面上可见的比赛列表（列结构对齐参考文件 半全场亚盘_当天.py）"""
        matches = []
        try:
            page_html = self.web_page.html
            soup = BeautifulSoup(page_html, 'html.parser')

            match_rows = soup.find_all('tr', id=lambda x: x and x.startswith('tr1_'))

            for row in match_rows:
                style = row.get('style', '')
                if 'display: none' in style:
                    continue

                tds = row.find_all('td')
                if len(tds) < 11:
                    continue

                match_id = ''
                row_id = row.get('id', '')
                if row_id and row_id.startswith('tr1_'):
                    match_id = row_id.replace('tr1_', '')

                # 列结构与参考文件一致：
                # td[1]: 联赛名  td[2]: 比赛时间  td[3]: 状态(分钟)  td[4]: 主队
                # td[5]: 比分  td[6]: 客队  td[7]: 角球/半场比分
                league = tds[1].get_text(strip=True) if len(tds) > 1 else ''
                match_time = tds[2].get_text(strip=True) if len(tds) > 2 else ''
                status = tds[3].get_text(strip=True) if len(tds) > 3 else ''
                home_team = tds[4].get_text(strip=True) if len(tds) > 4 else ''

                score = ''
                if len(tds) > 5:
                    score_fonts = tds[5].find_all('font')
                    if len(score_fonts) >= 2:
                        score = f"{score_fonts[0].get_text(strip=True)}-{score_fonts[1].get_text(strip=True)}"
                    elif '-' in tds[5].get_text(strip=True):
                        score = tds[5].get_text(strip=True)

                away_team = tds[6].get_text(strip=True) if len(tds) > 6 else ''

                half_score = ''
                corner_data = ''
                if len(tds) > 7:
                    corner_span = tds[7].find('span', class_='td_halfB')
                    if corner_span:
                        corner_data = corner_span.get_text(strip=True)
                    half_span = tds[7].find('span', class_='td_halfR')
                    if half_span:
                        half_score = half_span.get_text(strip=True)

                # 亚盘盘口
                handicap = ''
                if len(tds) > 10:
                    div_elem = tds[10].find('div')
                    if div_elem:
                        handicap = div_elem.get_text(strip=True)
                    else:
                        handicap = tds[10].get_text(strip=True)

                # 大小球
                overunder = ''
                if len(tds) > 11:
                    ou_div = tds[11].find('div')
                    if ou_div:
                        overunder = ou_div.get_text(strip=True)
                    else:
                        overunder = tds[11].get_text(strip=True)

                # if match_id:
                #     if not self._is_match_live(status):
                #         continue
                    matches.append({
                        'match_id': match_id,
                        'league': league,
                        'match_time': match_time,
                        'status': status,
                        'home_team': home_team,
                        'score': score,
                        'away_team': away_team,
                        'half_score': half_score,
                        'corner_data': corner_data,
                        'handicap': handicap,
                        'overunder': overunder,
                        'source': source,
                    })

        except Exception as e:
            print(f"[FilterController] 解析比赛列表失败: {e}")

        return matches
