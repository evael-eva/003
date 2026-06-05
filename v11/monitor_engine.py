#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
监控引擎(QThread) - 定时检测盘口数据并比对阈值，触发告警
功能：
1. 定时轮询已监控比赛的亚盘/大小球实时数据
2. 比对用户设定的阈值（进球数、水位）
3. 触发三种提醒规则：上下半场进球、进球数达标、水位达标
4. 通过信号通知UI层更新和触发告警服务
"""

import time
import random
import re
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
from concurrent.futures import ThreadPoolExecutor

from odds_fetcher import OddsFetcher


class MonitorEngine(QThread):
    """监控引擎线程"""

    # ===== 信号定义 =====
    # 数据更新信号：传递比赛ID和最新数据
    data_updated = pyqtSignal(str, dict)
    # 告警触发信号：(match_id, alert_type, detail_msg)
    alert_triggered = pyqtSignal(str, str, str)
    # 日志信号
    log_signal = pyqtSignal(str)
    # 监控状态变化信号：(running:bool, match_count:int)
    status_changed = pyqtSignal(bool, int)
    # 轮询完成一轮信号（用于UI刷新计时器等）
    cycle_completed = pyqtSignal()
    # v11新增: 比赛结束信号 (match_id, home_team, away_team)
    match_ended_signal = pyqtSignal(str, str, str)

    def __init__(self, fetcher=None):
        """
        初始化监控引擎
        :param fetcher: OddsFetcher实例（可选），如果不提供则创建新的
        """
        super().__init__()
        self._running = False
        self._refresh_interval = 10  # 默认刷新间隔(秒)

        # v8.3修复: 使用传入的fetcher或创建新的
        if fetcher:
            self.fetcher = fetcher
            print("[监控引擎] ✅ 使用外部传入的OddsFetcher实例")
        else:
            self.fetcher = OddsFetcher()
            print("[监控引擎] ⚠️ 创建新的OddsFetcher实例（无代理配置）")
        # 已监控的比赛列表: {match_id: config_dict}
        # config_dict 包含:
        #   home_team, away_team,
        #   target_goals(int): 目标全场进球数
        #   first_half_alert(bool): 上半场进球提醒开关
        #   second_half_alert(bool): 下半场进球提醒开关
        #   asian_home_threshold(float): 亚盘主队水位阈值
        #   asian_away_threshold(float): 亚盘客队水位阈值
        #   ou_over_threshold(float): 大球水位阈值
        #   ou_under_threshold(float): 小球水位阈值
        self.monitored_matches = {}

        # 防重复告警记录: {(match_id, alert_type): last_trigger_time}
        self.alert_cooldown = {}  # 冷却期默认60秒
        self.cooldown_seconds = 60

        # 单次告警模式（默认开启）：每条规则触发后永久标记，不再重复
        self.one_shot_alert = True
        self._one_shot_triggered = set()  # {(match_id, alert_type)} 已触发的集合

        # 首轮跳过标记：第一轮只缓存基线数据，不触发告警（防止启动时误报）
        self._first_cycle_completed = False

        # 最新数据缓存: {match_id: latest_data}
        self.latest_data_cache = {}
        
        # 70分钟进球提醒状态跟踪: {match_id: {'goals_before_threshold': int, 'alerted': bool}}
        # 记录在到达设定时间前的进球数，用于判断是否有进球
        self.minute_goal_states = {}
        
        # v2新增: 进球阈值提醒状态: {match_id: {'first_half_last_goals': 0, 'second_half_last_goals': 0, ...}}
        self.goal_threshold_states = {}
        
        # v2新增: 无进球提醒状态: {match_id: {'first_half_no_goal_alerted': False, ...}}
        self.no_goal_states = {}
        
        # v5新增: 崩溃恢复机制
        self.crash_count = 0  # 连续崩溃次数
        self.max_crash_restart = 5  # 最大自动重启次数
        self.last_crash_time = None  # 上次崩溃时间
        self.crash_cooldown = 30  # 崩溃后冷却时间（秒）
        
        # v7新增: 看门狗机制（心跳检测和超时监控）
        self.watchdog_timeout = 120  # 看门狗超时阈值（秒），默认2分钟
        self.last_cycle_complete_time = None  # 上次轮询完成时间
        self.last_heartbeat_time = None  # 最后心跳时间
        self.watchdog_enabled = True  # 看门狗开关
        
        # v7新增: 进程健康检查
        self.health_check_interval = 60  # 健康检查间隔（秒）
        self.last_health_check_time = None  # 上次健康检查时间
        self.memory_threshold_mb = 500  # 内存使用阈值（MB）
        
        # v11修复: 复用线程池，避免频繁创建销毁导致线程泄漏
        self._thread_pool = None
        self._thread_pool_max_workers = 0
        
        # v5新增: 比赛结束检测机制
        self.match_end_states = {}  # {match_id: {'end_detected_time': datetime, 'is_ending': bool}}
        
        # v5新增: 未开赛比赛管理（延迟监控）
        self.pending_matches = {}  # {match_id: {'config': dict, 'match_time': str, 'added_time': datetime}}

    def add_match(self, match_id, config):
        """
        添加要监控的比赛
        :param match_id: 比赛ID
        :param config: 监控配置字典，可包含 'match_time' 和 'status' 字段
        """
        # v5新增: 检查是否为未开赛比赛
        match_status = config.get('status', '')
        match_time = config.get('match_time', '')
        
        # v7优化: 添加调试日志
        self.log_signal.emit(
            f"[延迟监控] add_match: ID={match_id}, status='{match_status}', match_time='{match_time}'"
        )
        
        # 如果状态为空或为"未开始"，加入待开赛队列
        if not match_status or match_status in ['未开始', '', ' ']:
            self.pending_matches[match_id] = {
                'config': config,
                'match_time': match_time,
                'added_time': datetime.now()
            }
            self.log_signal.emit(
                f"[延迟监控] 比赛 {config.get('home_team', '')} vs {config.get('away_team', '')} "
                f"(ID:{match_id}) 尚未开赛，已加入等待队列"
            )
            if match_time:
                self.log_signal.emit(f"[延迟监控] 预计开赛时间: {match_time}")
        else:
            # 已开始比赛，直接监控
            self.monitored_matches[match_id] = config
            self.log_signal.emit(f"[监控引擎] 添加监控比赛: {config.get('home_team', '')} vs {config.get('away_team', '')} (ID:{match_id})")
        
        self.status_changed.emit(self.is_running(), len(self.monitored_matches))

    def remove_match(self, match_id):
        """移除某场比赛的监控（v7增强版：清理所有相关状态）"""
        if match_id in self.monitored_matches:
            del self.monitored_matches[match_id]
            self.log_signal.emit(f"[监控引擎] 移除监控比赛: ID {match_id}")
        
        # v5新增: 也从待开赛队列中移除
        if match_id in self.pending_matches:
            del self.pending_matches[match_id]
            self.log_signal.emit(f"[延迟监控] 从等待队列移除: ID {match_id}")
        
        if match_id in self.latest_data_cache:
            del self.latest_data_cache[match_id]
        
        if match_id in self.minute_goal_states:
            del self.minute_goal_states[match_id]
        
        # v2新增: 清理新状态
        if match_id in self.goal_threshold_states:
            del self.goal_threshold_states[match_id]
        
        if match_id in self.no_goal_states:
            del self.no_goal_states[match_id]
        
        # v5新增: 清理比赛结束检测状态
        if match_id in self.match_end_states:
            del self.match_end_states[match_id]
        
        # v7修复: 清理告警冷却记录
        keys_to_remove = [key for key in self.alert_cooldown if key[0] == match_id]
        for key in keys_to_remove:
            del self.alert_cooldown[key]
        
        # v7修复: 清理单次触发记录
        keys_to_remove = [key for key in self._one_shot_triggered if key[0] == match_id]
        for key in keys_to_remove:
            self._one_shot_triggered.discard(key)
        
        self.log_signal.emit(f"[状态清理] 比赛{match_id}的所有状态已清理")
        self.status_changed.emit(self.is_running(), len(self.monitored_matches))

    def clear_matches(self):
        """清空所有监控比赛"""
        self.monitored_matches.clear()
        self.latest_data_cache.clear()
        self.alert_cooldown.clear()
        self._one_shot_triggered.clear()  # 同时清空单次告警记录
        self.minute_goal_states.clear()  # 清空70分钟进球提醒状态
        # v2新增: 清空新状态
        self.goal_threshold_states.clear()
        self.no_goal_states.clear()
        # v5新增: 清空比赛结束检测状态
        self.match_end_states.clear()
        # v5新增: 清空待开赛队列
        self.pending_matches.clear()
        self.status_changed.emit(False, 0)

    def set_refresh_interval(self, seconds):
        """设置刷新间隔（秒）"""
        if seconds > 0:
            self._refresh_interval = seconds

    def set_cooldown(self, seconds):
        """设置告警冷却时间（秒）"""
        if seconds > 0:
            self.cooldown_seconds = seconds
    
    def set_watchdog_timeout(self, seconds):
        """v7新增: 设置看门狗超时时间（秒）"""
        if seconds > 0:
            self.watchdog_timeout = seconds
            self.log_signal.emit(f"[看门狗] 超时阈值已更新为: {seconds}秒")
    
    def set_watchdog_enabled(self, enabled):
        """v7新增: 启用/禁用看门狗"""
        self.watchdog_enabled = enabled
        status = "启用" if enabled else "禁用"
        self.log_signal.emit(f"[看门狗] 已{status}")
    
    def set_health_check_interval(self, seconds):
        """v7新增: 设置健康检查间隔（秒）"""
        if seconds > 0:
            self.health_check_interval = seconds
            self.log_signal.emit(f"[健康检查] 检查间隔已更新为: {seconds}秒")
    
    def set_memory_threshold(self, mb):
        """v7新增: 设置内存使用阈值（MB）"""
        if mb > 0:
            self.memory_threshold_mb = mb
            self.log_signal.emit(f"[健康检查] 内存阈值已更新为: {mb} MB")
    
    def _check_pending_matches(self):
        """
        v5新增: 检查待开赛比赛是否已开赛
        通过获取比赛数据来判断状态，如果已开始则移入监控队列
        """
        self.log_signal.emit(f"[延迟监控] _check_pending_matches 被调用")
        
        if not self.pending_matches:
            self.log_signal.emit(f"[延迟监控] 待开赛队列为空，跳过检查")
            return
        
        # v7优化: 输出待开赛队列信息
        self.log_signal.emit(f"[延迟监控] 当前待开赛队列: {len(self.pending_matches)}场比赛")
        for mid, info in self.pending_matches.items():
            config = info['config']
            self.log_signal.emit(
                f"  - {config.get('home_team', '')} vs {config.get('away_team', '')} "
                f"(ID:{mid}, 预计时间:{info.get('match_time', '未知')})"
            )
        
        match_ids_to_activate = []
        
        for match_id, pending_info in list(self.pending_matches.items()):
            try:
                config = pending_info['config']
                match_time_str = pending_info.get('match_time', '')
                
                # 尝试获取比赛数据
                latest_data = self.fetcher.fetch_latest_odds(match_id)
                
                # 检查是否有错误
                if latest_data.get('error'):
                    # 可能是网络问题，继续等待
                    continue
                
                # 检查是否有数据行
                asian_rows = latest_data.get('asian_rows', [])
                if not asian_rows or len(asian_rows) == 0:
                    # 没有数据，可能还未开赛或数据未更新
                    continue
                
                # 获取第一行数据（最新）
                latest_row = asian_rows[0]
                if len(latest_row) < 7:
                    continue
                
                # 解析时间和状态
                time_str = latest_row[0]  # 第1列：时间（分钟）
                status = latest_row[6] if len(latest_row) > 6 else ''  # 第7列：状态
                
                # v7优化: 添加调试日志
                self.log_signal.emit(
                    f"[延迟监控] 检查比赛{match_id}: time_str='{time_str}', status='{status}'"
                )
                
                # 判断是否已开赛：
                # 1. 时间是数字（表示分钟数）
                # 2. 状态为'滚'（滚球）
                # 3. 或者时间为"中场"、"完场"等
                # 4. v7新增: 如果状态不为空且不是"未开始"，也认为已开赛
                is_started = False
                
                # 尝试将时间转换为数字
                try:
                    minute = int(time_str)
                    # 如果有分钟数，说明已开赛
                    is_started = True
                except (ValueError, TypeError):
                    # 如果不是数字，检查是否为特殊状态
                    if time_str in ['中', '完', '加时', '点球','推迟']:
                        is_started = True
                        self.log_signal.emit(f"[延迟监控] 比赛{match_id}: 检测到特殊状态'{time_str}'，判定为已开赛")
                    elif status == '滚':
                        # 状态为滚球，说明已开赛
                        is_started = True
                        self.log_signal.emit(f"[延迟监控] 比赛{match_id}: 检测到滚球状态，判定为已开赛")
                    elif status and status not in ['未开始', '', ' ']:
                        # v7新增: 如果状态不为空且不是"未开始"，也认为已开赛
                        is_started = True
                        self.log_signal.emit(f"[延迟监控] 比赛{match_id}: 检测到状态'{status}'，判定为已开赛")
                    else:
                        self.log_signal.emit(f"[延迟监控] 比赛{match_id}: 未满足开赛条件，继续等待")
                
                if is_started:
                    match_ids_to_activate.append(match_id)
                    self.log_signal.emit(
                        f"[延迟监控] ✅ 比赛 {config.get('home_team', '')} vs {config.get('away_team', '')} "
                        f"(ID:{match_id}) 已开赛！开始监控..."
                    )
                    if match_time_str:
                        self.log_signal.emit(f"[延迟监控] 预计开赛时间: {match_time_str}")
                    if time_str.isdigit():
                        self.log_signal.emit(f"[延迟监控] 当前比赛时间: {time_str}分钟")
            
            except Exception as e:
                # 单个比赛检查失败不影响其他比赛
                self.log_signal.emit(f"[延迟监控] 检查比赛{match_id}状态失败: {e}")
        
        # 将已开赛的比赛移入监控队列
        for match_id in match_ids_to_activate:
            if match_id in self.pending_matches:
                pending_info = self.pending_matches.pop(match_id)
                config = pending_info['config']
                
                # 添加到监控队列
                self.monitored_matches[match_id] = config
                
                # 初始化监控状态
                try:
                    latest_data = self.fetcher.fetch_latest_odds(match_id)
                    if latest_data and not latest_data.get('error'):
                        self._initialize_match_state(match_id, config, latest_data)
                        self.latest_data_cache[match_id] = latest_data
                except Exception as e:
                    self.log_signal.emit(f"[延迟监控] 初始化比赛{match_id}状态失败: {e}")
                
                self.log_signal.emit(
                    f"[监控引擎] 开始监控: {config.get('home_team', '')} vs {config.get('away_team', '')} "
                    f"(ID:{match_id})"
                )
        
        # 更新状态
        if match_ids_to_activate:
            self.status_changed.emit(self.is_running(), len(self.monitored_matches))

    def _watchdog_check(self):
        """
        v7新增: 看门狗检查机制
        检测程序是否卡死或长时间无响应
        """
        if not self.watchdog_enabled:
            return
        
        if not self.last_cycle_complete_time:
            # 还没有完成过任何轮询，不进行检查
            return
        
        # 计算距离上次轮询完成的时间
        elapsed = (datetime.now() - self.last_cycle_complete_time).total_seconds()
        
        # 如果超过超时阈值，触发看门狗
        if elapsed > self.watchdog_timeout:
            self.log_signal.emit(
                f"⚠️ [看门狗] 检测到程序可能卡死！\n"
                f"距离上次完成轮询已过 {elapsed:.1f} 秒\n"
                f"超时阈值: {self.watchdog_timeout} 秒\n"
                f"将尝试强制重启..."
            )
            
            # 发送看门狗告警
            if self.alert_service:
                try:
                    alert_msg = (
                        f"⚠️ 看门狗超时告警!\n\n"
                        f"监控引擎已 {elapsed:.1f} 秒无响应\n"
                        f"超时阈值: {self.watchdog_timeout} 秒\n\n"
                        f"系统将尝试自动重启..."
                    )
                    self.alert_service.trigger_alert(
                        'SYSTEM',
                        'watchdog_timeout',
                        alert_msg
                    )
                except Exception as alert_err:
                    self.log_signal.emit(f"[看门狗] 发送告警失败: {alert_err}")
            
            # 抛出异常，触发外层的崩溃恢复机制
            raise TimeoutError(f"看门狗超时: {elapsed:.1f}秒无响应")
    
    def _health_check(self):
        """
        v7新增: 进程健康检查
        监控内存使用、线程状态等关键指标
        """
        now = datetime.now()
        
        # 按间隔执行健康检查
        if self.last_health_check_time:
            elapsed = (now - self.last_health_check_time).total_seconds()
            if elapsed < self.health_check_interval:
                return
        
        self.last_health_check_time = now
        
        try:
            import psutil
            import os
            
            # 获取当前进程
            process = psutil.Process(os.getpid())
            
            # 检查内存使用
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # 转换为MB
            
            if memory_mb > self.memory_threshold_mb:
                self.log_signal.emit(
                    f"⚠️ [健康检查] 内存使用过高: {memory_mb:.1f} MB (阈值: {self.memory_threshold_mb} MB)"
                )
                
                # 发送告警
                if self.alert_service:
                    try:
                        alert_msg = (
                            f"⚠️ 内存使用告警!\n\n"
                            f"当前内存: {memory_mb:.1f} MB\n"
                            f"阈值: {self.memory_threshold_mb} MB\n\n"
                            f"建议重启程序以释放内存。"
                        )
                        self.alert_service.trigger_alert(
                            'SYSTEM',
                            'memory_warning',
                            alert_msg
                        )
                    except Exception as alert_err:
                        self.log_signal.emit(f"[健康检查] 发送告警失败: {alert_err}")
            else:
                self.log_signal.emit(f"[健康检查] 内存使用正常: {memory_mb:.1f} MB")
            
            # 检查线程状态
            thread_count = process.num_threads()
            self.log_signal.emit(f"[健康检查] 线程数: {thread_count}")
            
        except ImportError:
            # 如果没有安装psutil，跳过健康检查
            self.log_signal.emit("[健康检查] psutil未安装，跳过健康检查")
        except Exception as e:
            self.log_signal.emit(f"[健康检查] 检查失败: {e}")

    def set_one_shot_alert(self, enabled):
        """设置单次告警模式（True=每条规则只告警一次，False=冷却期后可重复）"""
        self.one_shot_alert = enabled
        if not enabled:
            self._one_shot_triggered.clear()

    def is_running(self):
        return self._running and self.isRunning()

    def stop(self):
        """停止监控"""
        self._running = False
        self._first_cycle_completed = False  # 重置，下次启动重新建立基线
        
        # v11修复: 关闭线程池，释放资源
        if self._thread_pool:
            try:
                self._thread_pool.shutdown(wait=True)
                self.log_signal.emit("[监控引擎] 线程池已关闭")
            except Exception as e:
                self.log_signal.emit(f"[监控引擎] 关闭线程池失败: {e}")
            finally:
                self._thread_pool = None
                self._thread_pool_max_workers = 0
        
        self.log_signal.emit("[监控引擎] 正在停止...")

    def run(self):
        """主循环 - 并发检测（使用线程池批量请求，大幅提速）"""
        self._running = True
        # v5优化: 启动时重置崩溃计数器
        self.crash_count = 0
        self.last_crash_time = None
        # v7新增: 初始化看门狗和健康检查时间
        self.last_cycle_complete_time = datetime.now()
        self.last_heartbeat_time = datetime.now()
        self.last_health_check_time = None
        
        self.log_signal.emit(f"[监控引擎] 启动成功, 刷新间隔: {self._refresh_interval}秒, 监控比赛数: {len(self.monitored_matches)}")
        self.log_signal.emit(f"[看门狗] 已启用，超时阈值: {self.watchdog_timeout}秒")

        while self._running:
            try:
                # v7新增: 更新心跳时间
                self.last_heartbeat_time = datetime.now()
                
                # v7新增: 执行健康检查
                self._health_check()
                
                # v7修复: 即使没有监控比赛，也要检查待开赛队列
                # 先检查待开赛比赛是否已开赛
                if self.pending_matches:
                    self.log_signal.emit(f"[延迟监控] === 开始检查待开赛队列 ===")
                    self._check_pending_matches()
                    self.log_signal.emit(f"[延迟监控] === 检查完成 ===")
                
                # 如果仍然没有监控比赛，等待后继续下一轮
                if not self.monitored_matches:
                    # 没有监控比赛时，等待
                    for _ in range(self._refresh_interval):
                        if not self._running:
                            break
                        time.sleep(1)
                    continue

                # ========== 并发获取所有比赛数据（线程池）==========
                match_ids = list(self.monitored_matches.keys())
                
                # v7优化: 根据比赛数量动态调整并发数，提高并发性能
                num_matches = len(match_ids)
                if num_matches <= 5:
                    max_workers = num_matches
                elif num_matches <= 15:
                    max_workers = min(num_matches, 20)  # 中等数量比赛，最多15个并发
                elif num_matches <= 30:
                    max_workers = min(num_matches, 25)  # 较大量比赛，最多20个并发
                else:
                    max_workers = min(num_matches, 30)  # 大量比赛时限制为25
                
                # v11修复: 复用线程池，避免频繁创建销毁
                if (self._thread_pool is None or 
                    max_workers != self._thread_pool_max_workers):
                    # 关闭旧线程池
                    if self._thread_pool:
                        try:
                            self._thread_pool.shutdown(wait=True)
                        except Exception:
                            pass
                    
                    # 创建新线程池
                    self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
                    self._thread_pool_max_workers = max_workers
                    self.log_signal.emit(f"[线程池] 已创建/更新，最大工作线程: {max_workers}")
                
                def _fetch_one(match_id):
                    return match_id, self.fetcher.fetch_latest_odds(match_id)

                batch_results = {}
                futures = {self._thread_pool.submit(_fetch_one, mid): mid for mid in match_ids}
                for future in futures:
                    if not self._running:
                        # v7修复: 取消未完成的任务，避免资源泄漏
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
                    try:
                        # v7修复: 缩短超时时间至15秒，避免长时间等待
                        mid, result = future.result(timeout=15)
                        batch_results[mid] = result
                    except Exception as e:
                        mid = futures[future]
                        batch_results[mid] = {'error': str(e)}

                # ========== 处理每场比赛的检测结果 ==========
                check_count = 0
                for match_id, latest in batch_results.items():
                    if not self._running:
                        break

                    config = self.monitored_matches.get(match_id)
                    if not config:
                        continue

                    if latest.get('error'):
                        if match_id not in self.latest_data_cache:
                            self.log_signal.emit(f"[监控引擎] {match_id} 获取数据失败: {latest['error']}")
                        # 尝试从旧缓存继续检测盘口变化等不需要新数据的规则
                        latest = self.latest_data_cache.get(match_id, latest)

                    # 缓存最新数据（首轮也必须缓存，作为后续对比的基线）
                    if not latest.get('error'):
                        self.latest_data_cache[match_id] = latest
                        check_count += 1  # 计数必须放在continue之前，否则首轮永远是0
                        
                        # v5优化: 首轮获取数据时，初始化监控状态
                        if not self._first_cycle_completed:
                            self._initialize_match_state(match_id, config, latest)

                    # 发送数据更新信号（UI始终显示最新数据）
                    self.data_updated.emit(match_id, latest)

                    # v5新增: 检查比赛是否结束
                    if latest and not latest.get('error'):
                        self._check_match_end_status(match_id, config, latest)

                    # 首轮只做数据缓存和状态初始化，不触发告警（防止启动时误报）
                    if not self._first_cycle_completed:
                        continue

                    # 执行所有检测规则（单场异常不影响其他比赛）
                    try:
                        if latest and not latest.get('error'):
                            self._check_all_rules(match_id, config, latest)
                        elif latest is None:
                            import traceback
                            self.log_signal.emit(f"[监控引擎] {match_id} 数据为空(None)! raw_result类型={type(batch_results.get(match_id))}, "
                                                f"cache有此比赛={match_id in self.latest_data_cache}")
                        elif latest.get('error'):
                            pass  # 有error的情况已在上面处理过，静默
                    except Exception as rule_err:
                        self.log_signal.emit(f"[监控引擎] 比赛规则检测异常({match_id}): {rule_err}")

                    check_count += 1

                # 首轮数据采集完成，标记基线已建立
                if not self._first_cycle_completed:
                    self._first_cycle_completed = True
                    self.log_signal.emit(f"[监控引擎] 基线数据已缓存({check_count}场)，从下一轮开始检测告警")
                
                # v5新增: 更新看门狗时间（本轮完成）
                self.last_cycle_complete_time = datetime.now()
                
                # 本轮检查完成
                self.cycle_completed.emit()
                
                # 等待到下一个周期
                remaining = self._refresh_interval
                while self._running and remaining > 0:
                    time.sleep(min(1, remaining))
                    remaining -= 1
                    
                    # v7新增: 看门狗检查（防止程序卡死）
                    self._watchdog_check()

            except KeyboardInterrupt:
                # v7修复: 特殊处理键盘中断，优雅退出
                self.log_signal.emit("[监控引擎] 收到中断信号，正在停止...")
                self._running = False
                break
            except SystemExit:
                # v7修复: 特殊处理系统退出
                self.log_signal.emit("[监控引擎] 收到退出信号")
                self._running = False
                break
            except TimeoutError as te:
                # v7新增: 特殊处理看门狗超时
                import traceback
                error_detail = traceback.format_exc()
                self.crash_count += 1
                self.last_crash_time = datetime.now()
                
                self.log_signal.emit(f"[看门狗] 超时异常 (第{self.crash_count}次): {te}")
                self.log_signal.emit(f"[看门狗] 详细堆栈:\n{error_detail}")
                
                # 发送错误告警
                if self.alert_service:
                    try:
                        alert_msg = f"⚠️ 看门狗超时!\n\n错误信息: {te}\n\n崩溃次数: {self.crash_count}/{self.max_crash_restart}"
                        self.alert_service.trigger_alert(
                            'SYSTEM', 
                            'watchdog_timeout', 
                            alert_msg
                        )
                    except Exception as alert_err:
                        self.log_signal.emit(f"[监控引擎] 发送错误告警失败: {alert_err}")
                
                # 检查是否超过最大重启次数
                if self.crash_count >= self.max_crash_restart:
                    self.log_signal.emit(f"[监控引擎] 已达到最大重启次数({self.max_crash_restart})，停止自动重启")
                    self._running = False
                    break
                
                # 非阻塞式冷却等待
                self.log_signal.emit(f"[监控引擎] 等待{self.crash_cooldown}秒后重启...")
                cooldown_start = time.time()
                while self._running and (time.time() - cooldown_start) < self.crash_cooldown:
                    time.sleep(1)
                    elapsed = int(time.time() - cooldown_start)
                    if elapsed % 10 == 0 and elapsed > 0:
                        remaining = self.crash_cooldown - elapsed
                        self.log_signal.emit(f"[监控引擎] 重启倒计时: {remaining}秒")
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                self.crash_count += 1
                self.last_crash_time = datetime.now()
                
                # v7修复: 分类记录异常
                error_type = type(e).__name__
                error_msg = f"[监控引擎] 循环异常 (第{self.crash_count}次) [{error_type}]: {e}"
                self.log_signal.emit(error_msg)
                self.log_signal.emit(f"[监控引擎] 详细堆栈:\n{error_detail}")
                
                # v7修复: 检查是否为致命异常
                if error_type in ['MemoryError', 'RecursionError']:
                    self.log_signal.emit("[监控引擎] 检测到致命异常，无法自动恢复")
                    self._running = False
                    break
                
                # v7新增: 分类处理不同类型的异常
                transient_errors = [
                    'ConnectionError', 'TimeoutError', 'RequestException', 
                    'URLError', 'SocketError', 'ReadTimeout'
                ]
                
                if error_type in transient_errors:
                    # 临时性错误（网络问题等），使用较短的冷却时间
                    self.log_signal.emit(f"[监控引擎] 检测到临时性错误({error_type})，使用快速重启策略")
                    quick_cooldown = min(self.crash_cooldown, 10)  # 最多10秒
                    self.log_signal.emit(f"[监控引擎] 等待{quick_cooldown}秒后快速重启...")
                    cooldown_start = time.time()
                    while self._running and (time.time() - cooldown_start) < quick_cooldown:
                        time.sleep(1)
                else:
                    # 其他错误，使用标准冷却时间
                    # 发送错误告警（带超时保护）
                    if self.alert_service:
                        try:
                            alert_msg = f"⚠️ 监控引擎崩溃!\n\n错误类型: {error_type}\n错误信息: {e}\n\n崩溃次数: {self.crash_count}/{self.max_crash_restart}"
                            self.alert_service.trigger_alert(
                                'SYSTEM', 
                                'engine_crash', 
                                alert_msg
                            )
                        except Exception as alert_err:
                            self.log_signal.emit(f"[监控引擎] 发送错误告警失败: {alert_err}")
                    
                    # 检查是否超过最大重启次数
                    if self.crash_count >= self.max_crash_restart:
                        self.log_signal.emit(f"[监控引擎] 已达到最大重启次数({self.max_crash_restart})，停止自动重启")
                        self._running = False
                        break
                    
                    # v7修复: 非阻塞式冷却等待
                    self.log_signal.emit(f"[监控引擎] 等待{self.crash_cooldown}秒后重启...")
                    cooldown_start = time.time()
                    while self._running and (time.time() - cooldown_start) < self.crash_cooldown:
                        time.sleep(1)
                        elapsed = int(time.time() - cooldown_start)
                        if elapsed % 10 == 0 and elapsed > 0:
                            remaining = self.crash_cooldown - elapsed
                            self.log_signal.emit(f"[监控引擎] 重启倒计时: {remaining}秒")

        self.status_changed.emit(False, len(self.monitored_matches))
        self.log_signal.emit("[监控引擎] 已停止")

    def _initialize_match_state(self, match_id, config, latest):
        """
        v5优化: 首轮获取数据时，初始化监控状态
        利用历史数据准确设置基准值，避免误判
        :param match_id: 比赛ID
        :param config: 监控配置
        :param latest: 最新数据
        """
        try:
            # 提取关键数据
            ou_latest = latest.get('ou_latest')
            if not ou_latest:
                return
            
            score_str = ou_latest.get('score', '')
            minute_str = ou_latest.get('time', '')
            current_minute = self._parse_minute(minute_str)
            total_goals = self._parse_total_goals(score_str)
            first_half_goals = self._parse_first_half_goals(score_str, current_minute)
            second_half_goals = total_goals - first_half_goals
            
            # === 1. 初始化下半场进球阈值状态 ===
            if config.get('second_half_goal_enabled', False):
                if match_id not in self.goal_threshold_states:
                    self.goal_threshold_states[match_id] = {
                        'first_half_last_goals': 0,
                        'second_half_last_goals': 0,
                        'second_half_baseline_goals': None,
                        'first_half_reached': False,
                        'second_half_reached': False
                    }
                
                state = self.goal_threshold_states[match_id]
                threshold = config.get('second_half_goal_threshold', 1)
                
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                if current_minute > 45 and state.get('second_half_baseline_goals') is None:
                    state['second_half_baseline_goals'] = first_half_goals  # 使用上半场最终进球数
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}初始化: 进入下半场，基准进球数={first_half_goals} "
                        f"(第{current_minute}分钟，全场{total_goals}球)"
                    )
                
                # 计算当前下半场实际进球数
                baseline = state.get('second_half_baseline_goals') or 0
                actual_second_half_goals = max(0, total_goals - baseline)
                
                # v5修复: 记录当前状态
                state['second_half_last_goals'] = actual_second_half_goals
                
                # v5修复: 如果初始状态已满足阈值，立即触发提醒
                # 因为这是"状态监控"规则，只要状态满足就应该提醒
                if actual_second_half_goals >= threshold and not state.get('second_half_reached', False):
                    self._try_trigger(
                        match_id, 'second_half_goal_threshold',
                        f"⚽ 下半场进球达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"下半场{actual_second_half_goals}球(阈值{threshold}), 全场{total_goals}球, "
                        f"比分 {score_str}, 第{current_minute}分钟"
                    )
                    state['second_half_reached'] = True
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}初始化: 下半场已进{actual_second_half_goals}球，"
                        f"已达到阈值{threshold}，立即触发提醒"
                    )
            
            # === 2. 初始化下半场仅N球状态 ===
            if config.get('second_half_no_goal_enabled', False):
                if match_id not in self.no_goal_states:
                    self.no_goal_states[match_id] = {
                        'second_half_one_goal_time': None,
                        'second_half_no_goal_alerted': False,
                        'second_half_baseline_goals': None
                    }
                
                state = self.no_goal_states[match_id]
                threshold_goals = config.get('second_half_no_goal_threshold', 1)
                
                # 如果已经进入下半场，记录基准值
                if current_minute > 45 and state.get('second_half_baseline_goals') is None:
                    state['second_half_baseline_goals'] = first_half_goals
                
                # 计算当前下半场实际进球数
                baseline = state.get('second_half_baseline_goals') or 0
                actual_second_half_goals = max(0, total_goals - baseline)
                
                # 如果已经达到阈值，记录时间但不触发提醒
                if actual_second_half_goals == threshold_goals:
                    state['second_half_one_goal_time'] = current_minute
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}初始化: 下半场已进{actual_second_half_goals}球，"
                        f"将在{config.get('second_half_no_goal_minute', 70)}分钟检查是否进第{threshold_goals+1}球"
                    )
                elif actual_second_half_goals > threshold_goals:
                    state['second_half_no_goal_alerted'] = True
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}初始化: 下半场已进{actual_second_half_goals}球，"
                        f"超过阈值{threshold_goals}，不再触发此规则"
                    )
            
            # === 3. 初始化70分钟进球提醒状态 ===
            if config.get('has_goal_time_enabled', False):
                threshold_minute = config.get('has_goal_time_minute', 70)
                
                if match_id not in self.minute_goal_states:
                    self.minute_goal_states[match_id] = {
                        'has_goal_time_alerted': False
                    }
                
                state = self.minute_goal_states[match_id]
                
                # 如果已经超过设定时间，标记为已提醒（不重复提醒）
                if current_minute >= threshold_minute:
                    state['has_goal_time_alerted'] = True
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}初始化: 已超过{threshold_minute}分钟，"
                        f"不再触发时间点提醒"
                    )
            
            self.log_signal.emit(
                f"[监控引擎] 比赛{match_id}状态初始化完成: "
                f"第{current_minute}分钟，全场{total_goals}球，上半场{first_half_goals}球，下半场{second_half_goals}球"
            )
            
        except Exception as e:
            self.log_signal.emit(f"[监控引擎] 比赛{match_id}状态初始化失败: {e}")
    
    def _ensure_match_state_initialized(self, match_id, config, latest):
        """
        v7修复: 统一的状态初始化方法
        确保所有必需的监控状态都被正确初始化
        :param match_id: 比赛ID
        :param config: 监控配置
        :param latest: 最新数据
        """
        try:
            # 提取关键数据
            ou_latest = latest.get('ou_latest') if latest else None
            if not ou_latest:
                return
            
            score_str = ou_latest.get('score', '')
            minute_str = ou_latest.get('time', '')
            current_minute = self._parse_minute(minute_str)
            total_goals = self._parse_total_goals(score_str)
            first_half_goals = self._parse_first_half_goals(score_str, current_minute)
            
            # 1. 初始化进球阈值状态
            if match_id not in self.goal_threshold_states:
                self.goal_threshold_states[match_id] = {
                    'first_half_last_goals': first_half_goals,
                    'second_half_last_goals': 0,
                    'second_half_baseline_goals': first_half_goals if current_minute > 45 else None,
                    'first_half_reached': False,
                    'second_half_reached': False
                }
                self.log_signal.emit(f"[状态初始化] 比赛{match_id}进球阈值状态已初始化")
            
            # 2. 初始化无进球提醒状态
            if match_id not in self.no_goal_states:
                self.no_goal_states[match_id] = {
                    'first_half_no_goal_alerted': False,
                    'second_half_one_goal_time': None,
                    'second_half_no_goal_alerted': False,
                    'second_half_baseline_goals': first_half_goals if current_minute > 45 else None
                }
                self.log_signal.emit(f"[状态初始化] 比赛{match_id}无进球提醒状态已初始化")
            
            # 3. 初始化70分钟提醒状态
            if match_id not in self.minute_goal_states:
                self.minute_goal_states[match_id] = {
                    'goals_before_threshold': total_goals,
                    'alerted': False,
                    'last_checked_minute': current_minute
                }
                self.log_signal.emit(f"[状态初始化] 比赛{match_id}70分钟提醒状态已初始化")
                
        except Exception as e:
            self.log_signal.emit(f"[状态初始化] 比赛{match_id}初始化失败: {e}")
    
    def _check_all_rules(self, match_id, config, latest):
        """执行所有检测规则（增强版：支持启用开关+比较符+盘口变化监控）"""
        try:
            # === 提取关键数据 ===
            asian_latest = latest.get('asian_latest')
            ou_latest = latest.get('ou_latest')

            # === 规则1 & 2: 进球数检测 ===
            current_score_str = ''
            total_goals = 0
            first_half_goals = 0
            second_half_goals = 0
            current_minute = 0

            if ou_latest:
                score_str = ou_latest.get('score', '')
                minute_str = ou_latest.get('time', '')
                current_score_str = score_str
                current_minute = self._parse_minute(minute_str)
                total_goals = self._parse_total_goals(score_str)
                first_half_goals = self._parse_first_half_goals(score_str, current_minute)
                second_half_goals = total_goals - first_half_goals

            # --- 目标进球（带启用开关）---
            target_enabled = config.get('target_goals_enabled', True)
            target_goals = config.get('target_goals', 0)
            if target_enabled and target_goals > 0 and total_goals >= target_goals:
                self._try_trigger(match_id, 'goal_reached',
                                  f"全场进球达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                  f"当前{total_goals}球(目标{target_goals}球), "
                                  f"比分 {current_score_str}, 第{current_minute}分钟")

            # === v2规则1: 上半场进球（带阈值）===
            if config.get('first_half_goal_enabled', False):
                threshold = config.get('first_half_goal_threshold', 1)
                
                # 初始化状态
                if match_id not in self.goal_threshold_states:
                    self.goal_threshold_states[match_id] = {
                        'first_half_last_goals': 0,
                        'second_half_last_goals': 0,
                        'first_half_reached': False,
                        'second_half_reached': False
                    }
                
                state = self.goal_threshold_states[match_id]
                
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                # 检查是否达到阈值且是新增的进球
                if (first_half_goals >= threshold and 
                    first_half_goals > state.get('first_half_last_goals', 0) and
                    not state.get('first_half_reached', False)):
                    self._try_trigger(
                        match_id, 'first_half_goal_threshold',
                        f"⚽ 上半场进球达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"上半场{first_half_goals}球(阈值{threshold}), 全场{total_goals}球, "
                        f"比分 {current_score_str}"
                    )
                    state['first_half_reached'] = True
                
                state['first_half_last_goals'] = first_half_goals

            # === v2规则2: 下半场进球（带阈值）===
            if config.get('second_half_goal_enabled', False):
                threshold = config.get('second_half_goal_threshold', 1)
                
                if match_id not in self.goal_threshold_states:
                    self.goal_threshold_states[match_id] = {
                        'first_half_last_goals': 0,
                        'second_half_last_goals': 0,
                        'second_half_baseline_goals': None,  # v2优化: 下半场开始时的全场进球数
                        'first_half_reached': False,
                        'second_half_reached': False
                    }
                
                state = self.goal_threshold_states[match_id]
                
                # v2优化: 记录下半场开始时的基准进球数
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                # 修复: 使用 current_minute > 45 而不是 == 46，避免错过记录时机
                if current_minute > 45 and state.get('second_half_baseline_goals') is None:
                    state['second_half_baseline_goals'] = total_goals
                    self.log_signal.emit(
                        f"[监控引擎] 比赛{match_id}进入下半场，记录基准进球数: {total_goals} (第{current_minute}分钟)"
                    )
                
                # v2优化: 计算下半场实际进球数 = 当前全场进球 - 下半场开始时的基准进球
                second_half_baseline = state.get('second_half_baseline_goals') or 0  # v2修复: 处理None值
                actual_second_half_goals = max(0, total_goals - second_half_baseline)
                
                # 使用实际的下半场进球数进行判断
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                if (actual_second_half_goals >= threshold and 
                    actual_second_half_goals > state.get('second_half_last_goals', 0) and
                    not state.get('second_half_reached', False)):
                    self._try_trigger(
                        match_id, 'second_half_goal_threshold',
                        f"⚽ 下半场进球达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"下半场{actual_second_half_goals}球(阈值{threshold}), 全场{total_goals}球, "
                        f"比分 {current_score_str}, 第{current_minute}分钟"
                    )
                    state['second_half_reached'] = True
                
                state['second_half_last_goals'] = actual_second_half_goals

            # === 规则3: 水位达标（带启用开关 + 自定义比较符）===
            if asian_latest:
                home_odds = self._safe_float(asian_latest.get('home_odds', ''))
                away_odds = self._safe_float(asian_latest.get('away_odds', ''))

                # 亚盘主队水位
                if config.get('asian_home_enabled', False) and home_odds is not None:
                    th = config.get('asian_home_threshold')
                    op = config.get('asian_home_operator', '<')
                    if self._check_threshold(home_odds, th, op):
                        op_txt = {'<': '低于', '>': '高于', '=': '等于'}.get(op, '<')
                        self._try_trigger(match_id, 'asian_home_odds',
                                          f"亚盘主队水位达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"主队赔率={asian_latest.get('home_odds','')}(阈值{op_txt}{th}), "
                                          f"盘口={asian_latest.get('handicap', '')}")

                # 亚盘客队水位
                if config.get('asian_away_enabled', False) and away_odds is not None:
                    th = config.get('asian_away_threshold')
                    op = config.get('asian_away_operator', '<')
                    if self._check_threshold(away_odds, th, op):
                        op_txt = {'<': '低于', '>': '高于', '=': '等于'}.get(op, '<')
                        self._try_trigger(match_id, 'asian_away_odds',
                                          f"亚盘客队水位达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"客队赔率={asian_latest.get('away_odds','')}(阈值{op_txt}{th}), "
                                          f"盘口={asian_latest.get('handicap', '')}")

            if ou_latest:
                over_odds = self._safe_float(ou_latest.get('over_odds', ''))
                under_odds = self._safe_float(ou_latest.get('under_odds', ''))

                # 大球水位
                if config.get('ou_over_enabled', False) and over_odds is not None:
                    th = config.get('ou_over_threshold')
                    op = config.get('ou_over_operator', '<')
                    if self._check_threshold(over_odds, th, op):
                        op_txt = {'<': '低于', '>': '高于', '=': '等于'}.get(op, '<')
                        self._try_trigger(match_id, 'ou_over_odds',
                                          f"大球水位达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"大球赔率={ou_latest.get('over_odds','')}(阈值{op_txt}{th}), "
                                          f"盘口={ou_latest.get('goal_line', '')}")

                # 小球水位
                if config.get('ou_under_enabled', False) and under_odds is not None:
                    th = config.get('ou_under_threshold')
                    op = config.get('ou_under_operator', '<')
                    if self._check_threshold(under_odds, th, op):
                        op_txt = {'<': '低于', '>': '高于', '=': '等于'}.get(op, '<')
                        self._try_trigger(match_id, 'ou_under_odds',
                                          f"小球水位达标! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"小球赔率={ou_latest.get('under_odds','')}(阈值{op_txt}{th}), "
                                          f"盘口={ou_latest.get('goal_line', '')}")

            # === 规则4: 亚盘盘口变化检测 ===
            if config.get('handicap_change_asian_enabled', False) and asian_latest:
                h_str = asian_latest.get('handicap', '')
                h_val = self._parse_handicap_value(h_str)
                if h_val is not None:
                    hc_th = config.get('handicap_change_asian_threshold', 0.25)
                    hc_op = config.get('handicap_change_asian_operator', '>')
                    # 与初盘比较
                    init_asian = (self.latest_data_cache.get(match_id, {}) or {}).get('asian_initial')
                    init_h = self._parse_handicap_value(init_asian.get('handicap', '')) if init_asian else None
                    if init_h is None:
                        init_h = h_val  # 首次无初盘数据时跳过

                    change = round(h_val - init_h, 2)
                    if abs(change) > 0 and self._check_threshold(abs(change), hc_th, hc_op):
                        direction = "升盘" if change > 0 else "降盘"
                        op_txt = {'<': '', '>': '超过', '=': '等于'}.get(hc_op, '>')
                        self._try_trigger(match_id, 'asian_handicap_change',
                                          f"亚盘盘口变化! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"{direction} 变化{abs(change)}(阈值{op_txt}{hc_th}), "
                                          f"当前={h_str}(数值{h_val})")

            # === 规则5: 大小球盘口变化检测 ===
            if config.get('handicap_change_ou_enabled', False) and ou_latest:
                gl_str = ou_latest.get('goal_line', '')
                gl_val = self._parse_goal_line_value(gl_str)
                if gl_val is not None:
                    ouc_th = config.get('handicap_change_ou_threshold', 0.25)
                    ouc_op = config.get('handicap_change_ou_operator', '>')
                    init_ou = (self.latest_data_cache.get(match_id, {}) or {}).get('ou_initial')
                    init_gl = self._parse_goal_line_value(init_ou.get('goal_line', '')) if init_ou else None
                    if init_gl is None:
                        init_gl = gl_val

                    change = round(gl_val - init_gl, 2)
                    if abs(change) > 0 and self._check_threshold(abs(change), ouc_th, ouc_op):
                        direction = "升盘(变大)" if change > 0 else "降盘(变小)"
                        op_txt = {'<': '', '>': '超过', '=': '等于'}.get(ouc_op, '>')
                        self._try_trigger(match_id, 'ou_handicap_change',
                                          f"大小球盘口变化! {config.get('home_team','')} vs {config.get('away_team','')}: "
                                          f"{direction} 变化{abs(change)}(阈值{op_txt}{ouc_th}), "
                                          f"当前={gl_str}(数值{gl_val})")

            # === 规则6: 70分钟进球提醒 ===
            if config.get('minute_70_goal_enabled', False) and current_minute > 0:
                threshold_minute = config.get('minute_70_threshold', 70)
                
                # 初始化状态跟踪
                if match_id not in self.minute_goal_states:
                    self.minute_goal_states[match_id] = {
                        'goals_before_threshold': 0,
                        'alerted': False,
                        'last_checked_minute': 0
                    }
                
                state = self.minute_goal_states[match_id]
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                last_minute = state.get('last_checked_minute', 0)
                
                # 如果已经提醒过，跳过
                if state.get('alerted', False):
                    pass
                # 如果还没到达设定时间，更新进球数记录
                elif current_minute < threshold_minute:
                    state['goals_before_threshold'] = total_goals
                    state['last_checked_minute'] = current_minute
                # 刚到达或超过设定时间，检查是否有进球
                # v7修复: 使用 .get() 安全访问，避免 KeyError
                elif last_minute < threshold_minute <= current_minute and not state.get('alerted', False):
                    goals_before = state.get('goals_before_threshold', 0)
                    if goals_before > 0:
                        # 有进球，触发提醒
                        self._try_trigger(
                            match_id, 'minute_70_goal',
                            f"⏰ {threshold_minute}分钟进球提醒! {config.get('home_team','')} vs {config.get('away_team','')}: "
                            f"比赛进行到第{current_minute}分钟，{threshold_minute}分钟前已有{goals_before}个进球，"
                            f"当前比分 {current_score_str}"
                        )
                        state['alerted'] = True
                    else:
                        # 没有进球，标记为已检查
                        state['alerted'] = True
                    state['last_checked_minute'] = current_minute

            # === v2规则7: 有进球后到达时间提醒（原70分钟功能优化版）===
            if config.get('has_goal_time_enabled', False) and total_goals > 0:
                threshold_minute = config.get('has_goal_time_minute', 70)
                
                if match_id not in self.no_goal_states:
                    self.no_goal_states[match_id] = {
                        'has_goal_time_alerted': False
                    }
                
                state = self.no_goal_states[match_id]
                
                if current_minute >= threshold_minute and not state.get('has_goal_time_alerted', False):
                    self._try_trigger(
                        match_id, 'has_goal_time_reached',
                        f"⏰ {threshold_minute}分钟提醒! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"比赛进行到第{current_minute}分钟，已有{total_goals}个进球，"
                        f"当前比分 {current_score_str}"
                    )
                    state['has_goal_time_alerted'] = True

            # === v2规则8: 上半场进N球后无第(N+1)球提醒 ===
            if config.get('first_half_no_goal_enabled', False) and current_minute <= 45:
                threshold_goals = config.get('first_half_no_goal_threshold', 1)  # v2新增: 可配置进球数阈值
                threshold_minute = config.get('first_half_no_goal_minute', 30)
                
                if match_id not in self.no_goal_states:
                    self.no_goal_states[match_id] = {
                        'first_half_one_goal_time': None,  # 记录上半场进第threshold_goals球的时间
                        'first_half_no_goal_alerted': False
                    }
                
                state = self.no_goal_states[match_id]
                
                # 记录上半场第threshold_goals个进球的时间
                if first_half_goals == threshold_goals and state.get('first_half_one_goal_time') is None:
                    state['first_half_one_goal_time'] = current_minute
                
                # 如果上半场有threshold_goals个进球，且到达设定时间还没有第(threshold_goals+1)个进球
                if (first_half_goals == threshold_goals and 
                    current_minute >= threshold_minute and 
                    not state.get('first_half_no_goal_alerted', False)):
                    goal_time = state.get('first_half_one_goal_time', 0)
                    self._try_trigger(
                        match_id, 'first_half_no_goal',
                        f"⚠️ 上半场仅{threshold_goals}球! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"比赛进行到第{current_minute}分钟，上半场第{goal_time}分钟进{threshold_goals}球后，"
                        f"至今未进第{threshold_goals+1}球"
                    )
                    state['first_half_no_goal_alerted'] = True

            # === v2规则9: 下半场进N球后无第(N+1)球提醒 ===
            if config.get('second_half_no_goal_enabled', False) and current_minute > 45:
                threshold_goals = config.get('second_half_no_goal_threshold', 1)  # v2新增: 可配置进球数阈值
                threshold_minute = config.get('second_half_no_goal_minute', 70)
                
                if match_id not in self.no_goal_states:
                    self.no_goal_states[match_id] = {
                        'second_half_one_goal_time': None,  # 记录下半场进第threshold_goals球的时间
                        'second_half_no_goal_alerted': False,
                        'second_half_baseline_goals': None  # v2优化: 下半场开始时的基准进球数
                    }
                
                state = self.no_goal_states[match_id]
                
                # v2优化: 记录下半场开始时的基准进球数
                # 修复: 使用 current_minute > 45 而不是 == 46，避免错过记录时机
                if current_minute > 45 and state.get('second_half_baseline_goals') is None:
                    state['second_half_baseline_goals'] = total_goals
                
                # v2优化: 计算下半场实际进球数
                second_half_baseline = state.get('second_half_baseline_goals') or 0  # v2修复: 处理None值
                actual_second_half_goals = max(0, total_goals - second_half_baseline)
                
                # 记录下半场第threshold_goals个进球的时间（使用实际的下半场进球数）
                if actual_second_half_goals == threshold_goals and state.get('second_half_one_goal_time') is None:
                    state['second_half_one_goal_time'] = current_minute
                
                # 如果下半场有threshold_goals个进球，且到达设定时间还没有第(threshold_goals+1)个进球
                if (actual_second_half_goals == threshold_goals and 
                    current_minute >= threshold_minute and 
                    not state.get('second_half_no_goal_alerted', False)):
                    goal_time = state.get('second_half_one_goal_time', 0)
                    self._try_trigger(
                        match_id, 'second_half_no_goal',
                        f"⚠️ 下半场仅{threshold_goals}球! {config.get('home_team','')} vs {config.get('away_team','')}: "
                        f"比赛进行到第{current_minute}分钟，下半场第{goal_time}分钟进{threshold_goals}球后，"
                        f"至今未进第{threshold_goals+1}球，全场{total_goals}球"
                    )
                    state['second_half_no_goal_alerted'] = True

        except Exception as e:
            self.log_signal.emit(f"[监控引擎] 检测比赛{match_id}异常: {e}")

    @staticmethod
    def _check_threshold(current, threshold, operator='<'):
        """根据比较符判断是否触发"""
        if current is None or threshold is None:
            return False
        try:
            c, t = float(current), float(threshold)
            if operator == '<':
                return c <= t
            elif operator == '>':
                return c >= t
            elif operator == '=':
                return abs(c - t) < 0.01
        except (ValueError, TypeError):
            pass
        return False

    @staticmethod
    def _parse_handicap_value(handicap_text):
        """
        将亚盘盘口字符串转为数值
        支持格式：'平手'→0, '半球'→0.5, '一球/球半'→1.25,
                 '受让一球'→-1, '受让半球/一球'→-0.75 等
        """
        if not handicap_text:
            return None

        # 定义中文到数字的基础映射（正值）
        base_mapping = {
            '平盘': 0, '平手': 0,
            '半球': 0.5,
            '一球': 1, '球半': 1.5,
            '两球': 2, '两球半': 2.5,
            '三球': 3, '三球半': 3.5,
            '四球': 4, '四球半': 4.5,
            '五球': 5, '五球半': 5.5,
            '六球': 6, '六球半': 6.5,
            '七球': 7, '七球半': 7.5,
            '八球': 8, '八球半': 8.5,
            '九球': 9, '九球半': 9.5,
            '十球': 10, '十球半': 10.5,
        }

        s = str(handicap_text).strip()

        # 直接是数字
        try:
            return float(s)
        except ValueError:
            pass

        # 处理类似 "一球/球半" 的组合情况
        if '/' in s:
            # 检查是否包含"受让"前缀，受让代表负数
            is_shourang = False
            handicap_str = s
            if handicap_str.startswith('受让'):
                is_shourang = True
                handicap_str = handicap_str[2:]

            parts = handicap_str.split('/')
            if len(parts) == 2:
                part1 = parts[0].strip()
                part2 = parts[1].strip()
                val1 = base_mapping.get(part1)
                val2 = base_mapping.get(part2)
                # 尝试将两个值转换为数字并计算平均值
                if val1 is not None and val2 is not None:
                    avg = (val1 + val2) / 2
                    # 如果是受让盘口，结果取负
                    if is_shourang:
                        avg = -avg
                    return avg
                else:
                    # 尝试直接转float
                    try:
                        v1 = float(part1) if val1 is None else val1
                        v2 = float(part2) if val2 is None else val2
                        avg = (v1 + v2) / 2
                        return -avg if is_shourang else avg
                    except ValueError:
                        return None
            else:
                # 不止两个部分，尝试逐个映射
                vals = []
                for part in parts:
                    part = part.strip()
                    v = base_mapping.get(part)
                    if v is not None:
                        vals.append(v)
                    else:
                        try:
                            vals.append(float(part))
                        except ValueError:
                            pass
                if len(vals) >= 2:
                    avg = sum(vals[:2]) / 2
                    return -avg if is_shourang else avg
                return None

        # 单值映射：检查受让前缀
        if s.startswith('受让'):
            remainder = s[2:]
            # 受让平手/受让平盘
            if remainder in ('平手', '平盘'):
                return 0  # 受让平手=0
            val = base_mapping.get(remainder)
            if val is not None:
                return -val
            # 尝试直接转数字
            try:
                return -float(remainder)
            except ValueError:
                return None

        # 正常单值映射
        val = base_mapping.get(s)
        if val is not None:
            return val

        return None

    @staticmethod
    def _parse_goal_line_value(goal_line_str):
        """
        将大小球盘口字符串转为纯数值
        例如：'2/2.5' → 2.25, '2.5' → 2.5, '3/3.5' → 3.25
        """
        if not goal_line_str:
            return None
        s = str(goal_line_str).strip()
        try:
            return float(s)
        except ValueError:
            pass

        if '/' in s:
            parts = s.split('/')
            vals = []
            for p in parts:
                p = p.strip()
                try:
                    vals.append(float(p))
                except ValueError:
                    continue
            if len(vals) >= 2:
                return round((vals[0] + vals[1]) / 2, 2)

        return None

    def _try_trigger(self, match_id, alert_type, message):
        """尝试触发告警（带冷却机制 + 可选单次模式）"""
        key = (match_id, alert_type)
        now = datetime.now()

        # 单次告警模式：已触发过的规则永久跳过
        if self.one_shot_alert and key in self._one_shot_triggered:
            return

        last_time = self.alert_cooldown.get(key)
        if last_time:
            elapsed = (now - last_time).total_seconds()
            if elapsed < self.cooldown_seconds:
                return  # 还在冷却期内，不重复告警

        # 触发告警
        self.alert_cooldown[key] = now

        # 单次模式：标记为已触发，后续不再重复
        if self.one_shot_alert:
            self._one_shot_triggered.add(key)

        # v5优化: 从config中提取联赛信息，添加到消息中
        config = self.monitored_matches.get(match_id, {})
        league = config.get('league', '')
        if league:
            # 在消息开头添加联赛信息
            enhanced_message = f"【{league}】{message}"
        else:
            enhanced_message = message
        
        self.alert_triggered.emit(match_id, alert_type, enhanced_message)
        timestamp = now.strftime('%H:%M:%S')
        self.log_signal.emit(f"[⚠️告警] [{timestamp}] {message}")

    @staticmethod
    def _safe_float(value_str):
        """安全转换为float，转换失败返回None"""
        try:
            if value_str is None or value_str == '' or value_str == '-' or value_str == '封':
                return None
            return float(value_str)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _check_odds_threshold(current_value, threshold):
        """兼容旧接口：判断水位是否达到阈值（默认<=）"""
        return MonitorEngine._check_threshold(current_value, threshold, '<')

    @staticmethod
    def _parse_minute(time_str):
        """从时间字符串中提取分钟数"""
        if not time_str:
            return 0
        time_str = str(time_str).strip()
        if '中' in time_str:
            return 45
        if time_str.isdigit():
            return int(time_str)
        m = re.search(r'(\d+)', time_str)
        if m:
            return int(m.group(1))
        return 0

    @staticmethod
    def _parse_total_goals(score_str):
        """从比分字符串解析总进球数"""
        if not score_str:
            return 0
        parts = score_str.split('-')
        if len(parts) >= 2:
            try:
                return int(parts[0].strip()) + int(parts[1].strip())
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _parse_first_half_goals(score_str, current_minute):
        """
        估算上半场进球数
        策略：
        - 如果当前<=45分钟（含中场），全部进球算上半场
        - 如果当前>45分钟，无法精确区分上下半场，保守估算为min(total, 上半场合理范围)
        注意：这个方法只能给出近似值，精确的上/下半场区分需要更详细的数据源
        """
        total = MonitorEngine._parse_total_goals(score_str)
        if current_minute <= 45:
            return total
        else:
            # 已经进入下半场，粗略估计上半场进球不超过合理范围
            # 这里简单返回一个保守估计，实际应用可能需要额外的半场比分数据
            return min(total, max(0, total - 3))  # 假设下半场最多进3球作为保守估计

    def _check_match_end_status(self, match_id, config, latest_data):
        """
        v5新增: 检查比赛是否结束，如果是则停止监控
        
        判断逻辑：
        1. 检查最新一行数据是否为89分钟且状态为'封'
        2. 如果是，启动计时器，记录时间
        3. 每次轮询时检查是否有新的数据行出现
        4. 如果2分钟内没有新数据，停止监控该场比赛
        
        :param match_id: 比赛ID
        :param config: 配置字典
        :param latest_data: 最新数据
        """
        try:
            # 获取亚盘数据行
            asian_rows = latest_data.get('asian_rows', [])
            if not asian_rows or len(asian_rows) == 0:
                return
            
            # 获取第一行（最新数据）
            latest_row = asian_rows[0]
            if len(latest_row) < 7:
                return
            
            # 解析时间和状态
            time_str = latest_row[0]  # 第1列：时间（分钟）
            status = latest_row[6] if len(latest_row) > 6 else ''  # 第7列：状态
            
            # 尝试将时间转换为数字
            try:
                minute = int(time_str)
            except (ValueError, TypeError):
                # 如果不是数字（如"中场"、"完场"等），不处理
                return
            
            # 检查是否是89分钟且状态为'封'
            is_ending_candidate = (minute >= 89 and status == '封')
            
            # 初始化或更新状态
            if match_id not in self.match_end_states:
                self.match_end_states[match_id] = {
                    'end_detected_time': None,
                    'is_ending': False,
                    'last_row_count': len(asian_rows),
                    'latest_minute': minute
                }
            
            state = self.match_end_states[match_id]
            
            # 情况1: 检测到比赛可能结束（89分钟+封盘）
            if is_ending_candidate and not state['is_ending']:
                state['end_detected_time'] = datetime.now()
                state['is_ending'] = True
                state['last_row_count'] = len(asian_rows)
                state['latest_minute'] = minute
                
                self.log_signal.emit(
                    f"[比赛结束检测] {config.get('home_team', '')} vs {config.get('away_team', '')} "
                    f"(ID:{match_id}) 检测到比赛可能结束: {minute}分钟, 状态={status}"
                )
            
            # 情况2: 已经在等待结束确认中
            elif state['is_ending']:
                current_time = datetime.now()
                elapsed_seconds = (current_time - state['end_detected_time']).total_seconds()
                
                # 检查是否有新数据行出现
                current_row_count = len(asian_rows)
                has_new_data = current_row_count != state['last_row_count'] or minute != state['latest_minute']
                
                if has_new_data:
                    # 有新数据，重置结束检测
                    state['end_detected_time'] = None
                    state['is_ending'] = False
                    state['last_row_count'] = current_row_count
                    state['latest_minute'] = minute
                    
                    self.log_signal.emit(
                        f"[比赛结束检测] {config.get('home_team', '')} vs {config.get('away_team', '')} "
                        f"(ID:{match_id}) 检测到新数据，取消结束判定"
                    )
                elif elapsed_seconds >= 120:  # 2分钟 = 120秒
                    # 2分钟内无新数据，确认比赛结束，停止监控
                    self.log_signal.emit(
                        f"[比赛结束检测] ⚠️ {config.get('home_team', '')} vs {config.get('away_team', '')} "
                        f"(ID:{match_id}) 比赛已结束！2分钟内无新数据，自动停止监控"
                    )
                    
                    # v11新增: 发送比赛结束信号给UI
                    self.match_ended_signal.emit(
                        match_id,
                        config.get('home_team', ''),
                        config.get('away_team', '')
                    )
                    
                    # 发送告警通知（可选）
                    if self.alert_service:
                        try:
                            # 构造包含联赛名的消息
                            league = config.get('league', '')
                            if league:
                                enhanced_msg = f"【{league}】比赛结束自动停止监控\n\n{config.get('home_team', '')} vs {config.get('away_team', '')}\n比赛ID: {match_id}\n最后时间: {minute}分钟\n停止原因: 2分钟内无新数据更新"
                            else:
                                enhanced_msg = f"比赛结束自动停止监控\n\n{config.get('home_team', '')} vs {config.get('away_team', '')}\n比赛ID: {match_id}\n最后时间: {minute}分钟\n停止原因: 2分钟内无新数据更新"
                            self.alert_service.trigger_alert(
                                match_id,
                                'match_ended',
                                enhanced_msg
                            )
                        except Exception as e:
                            self.log_signal.emit(f"[比赛结束检测] 发送告警失败: {e}")
                    
                    # 从监控列表中移除该比赛
                    self.remove_match(match_id)
                    
                    # 清理状态
                    del self.match_end_states[match_id]
                else:
                    # 还在等待中，输出倒计时提示（每30秒一次）
                    remaining = 120 - elapsed_seconds
                    if remaining % 30 < 1:  # 每30秒输出一次
                        self.log_signal.emit(
                            f"[比赛结束检测] {config.get('home_team', '')} vs {config.get('away_team', '')} "
                            f"(ID:{match_id}) 等待确认中... 剩余{int(remaining)}秒"
                        )
        
        except Exception as e:
            # 异常不影响主流程，只记录日志
            self.log_signal.emit(f"[比赛结束检测] 异常: {e}")
