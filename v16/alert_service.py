#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
告警服务 - 统一管理弹窗/声音/邮件三种通知方式
功能：
1. 弹窗提醒：通过信号投递到主线程，使用PyQt5的QMessageBox弹出警告窗口（禁止在子线程直接创建Qt窗口）
2. 声音报警：使用winsound播放Windows系统提示音
3. 邮件通知：调用EmailService发送SMTP邮件
4. 日志记录：将所有告警数据保存到日志文件

提供统一的trigger_alert()接口，根据配置决定启用哪些通知渠道。
"""

import os
import json
import threading
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class AlertService(QObject):
    """告警服务管理器（继承QObject以便使用信号槽）"""

    # 弹窗请求信号：(message, alert_type, timestamp)
    _popup_requested = pyqtSignal(str, str, str)

    def __init__(self, log_dir='alert_logs'):
        super().__init__()
        # 通知开关
        self.popup_enabled = True
        self.sound_enabled = True
        self.email_enabled = False
        
        # v2新增: 日志记录开关和配置
        self.log_enabled = True
        self.log_dir = log_dir
        self._ensure_log_dir()

        # 父窗口引用（用于弹窗）
        self.parent_widget = None

        # 邮件配置（从EmailConfig加载）
        self.email_config = {
            'smtp_server': '',
            'smtp_port': 465,
            'sender_email': '',
            'sender_password': '',
            'receiver_email': '',
        }

        # 告警计数器
        self.total_alerts = 0

        # 将信号连接到实际的弹窗显示方法（在主线程中执行）
        self._popup_requested.connect(self._show_popup_on_main_thread)

    def set_parent(self, widget):
        """设置父窗口（用于弹窗）"""
        self.parent_widget = widget
    
    def _ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def _save_alert_log(self, match_id, alert_type, message, timestamp):
        """
        保存告警数据到日志文件
        :param match_id: 比赛ID
        :param alert_type: 告警类型
        :param message: 告警消息
        :param timestamp: 时间戳
        """
        if not self.log_enabled:
            return
        
        try:
            # 生成日志文件名（按日期分文件）
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(self.log_dir, f'alerts_{date_str}.json')
            
            # 准备日志条目
            log_entry = {
                'timestamp': timestamp,
                'match_id': match_id,
                'alert_type': alert_type,
                'alert_type_name': self._get_alert_type_original_name(alert_type),  # v5修复: 使用原始名称
                'message': message,
                'datetime': datetime.now().isoformat()
            }
            
            # 读取现有日志
            logs = []
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        logs = json.load(f)
                except (json.JSONDecodeError, IOError):
                    logs = []
            
            # 追加新日志
            logs.append(log_entry)
            
            # 保存日志（保持最近1000条）
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"[AlertService] 保存日志失败: {e}")

    def configure_email(self, smtp_server, smtp_port, sender_email, sender_password, receiver_emails):
        """配置邮件参数（注意：不自动开启email_enabled，由UI开关控制）
        :param receiver_emails: 可以是字符串（单个邮箱）或列表（多个邮箱）
        """
        # 处理接收者邮箱：支持字符串或列表
        if isinstance(receiver_emails, str):
            # 如果是字符串，按逗号或分号分割
            emails = [e.strip() for e in receiver_emails.replace(';', ',').split(',') if e.strip()]
        elif isinstance(receiver_emails, list):
            emails = receiver_emails
        else:
            emails = []
        
        self.email_config = {
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'sender_email': sender_email,
            'sender_password': sender_password,
            'receiver_emails': emails,  # v5优化: 改为列表
        }
        # 不再自动设置 self.email_enabled = True
        # 邮件开关完全由 UI 的 email_cb 复选框控制

    def trigger_alert(self, match_id, alert_type, message):
        """
        统一触发告警 - 根据开关状态分别调用各通知方式
        :param match_id: 比赛ID
        :param alert_type: 告警类型 (goal_reached / first_half_goal / second_half_goal /
                         asian_home_odds / asian_away_odds / ou_over_odds / ou_under_odds)
        :param message: 告警详情信息
        """
        self.total_alerts += 1
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # v2新增: 保存告警日志
        self._save_alert_log(match_id, alert_type, message, timestamp)

        # 并行执行各通知方式（不阻塞主线程）
        threads = []

        if self.popup_enabled:
            # 通过信号将弹窗请求安全地投递到主线程（跨线程信号自动QueuedConnection）
            self._popup_requested.emit(message, alert_type, timestamp)

        if self.sound_enabled:
            t = threading.Thread(target=self._play_sound, args=(alert_type,), daemon=True)
            threads.append(t)

        if self.email_enabled and self.email_config.get('receiver_emails'):
            # v2优化: 伪装成美股股票信息，替换敏感词
            original_subject = f"[盘口监控] {self._get_alert_type_name(alert_type)} - {timestamp}"
            original_body = f"比赛ID: {match_id}\n告警类型: {self._get_alert_type_name(alert_type)}\n时间: {timestamp}\n\n{message}\n\n---\n此邮件由盘口监控系统自动发送"
            
            # 替换敏感词
            sanitized_subject = self._sanitize_email_content(original_subject)
            sanitized_body = self._sanitize_email_content(original_body)
            
            # 使用伪装后的标题和内容
            subject = f"[美股股票信息] {sanitized_subject}"
            body = sanitized_body
            
            t = threading.Thread(target=self._send_email, args=(subject, body,), daemon=True)
            threads.append(t)

        for t in threads:
            t.start()

    def _show_popup_on_main_thread(self, message, alert_type, timestamp):
        """
        在主线程中实际执行弹窗（由 _popup_requested 信号触发，自动在主线程执行）
        这是唯一合法的 Qt UI 操作入口。
        v2优化: 使用非模态对话框，允许多个告警同时显示
        """
        try:
            from PyQt5.QtWidgets import QMessageBox
            from PyQt5.QtCore import Qt

            type_icons = {
                'goal_reached': QMessageBox.Warning,
                'first_half_goal': QMessageBox.Information,
                'second_half_goal': QMessageBox.Information,
                'asian_home_odds': QMessageBox.Critical,
                'asian_away_odds': QMessageBox.Critical,
                'ou_over_odds': QMessageBox.Critical,
                'ou_under_odds': QMessageBox.Critical,
                'engine_crash': QMessageBox.Critical,  # v5新增: 引擎崩溃用严重图标
                'match_ended': QMessageBox.Information,  # v5新增: 比赛结束用信息图标
            }

            icon = type_icons.get(alert_type, QMessageBox.Warning)
            title = f"⚠ {self._get_alert_type_name(alert_type)}"
            full_message = f"{message}\n\n时间: {timestamp}"

            msg_box = QMessageBox(icon, title, full_message)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.setDefaultButton(QMessageBox.Ok)
            msg_box.setWindowTitle("盘口监控告警")
            msg_box.setTextFormat(Qt.PlainText)
            
            # v2优化: 设置为非模态对话框，允许多个弹窗同时显示
            msg_box.setModal(False)
            
            # 设置窗口标志，使弹窗始终在最前
            msg_box.setWindowFlags(
                msg_box.windowFlags() | 
                Qt.WindowStaysOnTopHint |  # 始终置顶
                Qt.WindowCloseButtonHint   # 显示关闭按钮
            )

            if self.parent_widget and not self.parent_widget.isHidden():
                # v2优化: 使用show()而非exec_()，非阻塞显示
                msg_box.show()
                # 保持引用，防止被垃圾回收
                if not hasattr(self, '_active_popups'):
                    self._active_popups = []
                self._active_popups.append(msg_box)
                
                # 清理已关闭的弹窗（保留最近20个）
                if len(self._active_popups) > 50:
                    self._active_popups = self._active_popups[-20:]

        except Exception as e:
            print(f"[AlertService] 弹窗失败: {e}")

    @staticmethod
    def _play_sound(alert_type):
        """声音报警（纯后台操作，不需要Qt）"""
        try:
            import winsound
            import time

            # 根据告警类型选择不同的声音模式
            if alert_type in ('goal_reached', 'first_half_goal', 'second_half_goal'):
                # 进球提醒：使用系统默认提示音（比MessageBeep更可靠）
                for i in range(2):
                    winsound.PlaySound('SystemDefault', winsound.SND_ALIAS | winsound.SND_ASYNC)
                    if i < 1:
                        time.sleep(0.25)

            elif alert_type.startswith('asian'):
                # 亚盘水位告警：高频急促蜂鸣
                for _ in range(4):
                    try:
                        winsound.Beep(880, 300)  # A5音符
                    except (OSError, RuntimeError):
                        # Beep失败时降级为PlaySound
                        winsound.PlaySound('SystemExclamation', winsound.SND_ALIAS | winsound.SND_ASYNC)
                    time.sleep(0.15)

            elif alert_type.startswith('ou') or 'handicap_change' in alert_type:
                # 大小球/盘口变化告警：中频警示音
                for _ in range(3):
                    try:
                        winsound.Beep(660, 350)  # E5音符
                    except (OSError, RuntimeError):
                        winsound.PlaySound('SystemHand', winsound.SND_ALIAS | winsound.SND_ASYNC)
                    time.sleep(0.2)

            else:
                # 默认：系统警告音
                winsound.PlaySound('SystemExclamation', winsound.SND_ALIAS | winsound.SND_ASYNC)

        except ImportError:
            print("[AlertService] winsound模块不可用，跳过声音（非Windows系统？）")
        except Exception as e:
            print(f"[AlertService] 声音播放失败: {type(e).__name__}: {e}")

    def _send_email(self, subject, body):
        """发送邮件通知（纯后台操作）"""
        max_retries = 2  # v7新增: 最大重试次数
        retry_delay = 5  # v7新增: 重试间隔（秒）
        
        for attempt in range(1, max_retries + 1):
            try:
                from email_config import EmailService
                
                # v7修复: 创建服务时设置超时
                svc = EmailService(
                    self.email_config['smtp_server'],
                    self.email_config['smtp_port'],
                    self.email_config['sender_email'],
                    self.email_config['sender_password'],
                )
                
                receiver_emails = self.email_config.get('receiver_emails', [])
                if isinstance(receiver_emails, list) and len(receiver_emails) > 0:
                    success_count = 0
                    for receiver in receiver_emails:
                        if receiver:
                            try:
                                svc.send(receiver, subject, body)
                                print(f"[AlertService] 邮件已发送至: {receiver}")
                                success_count += 1
                            except Exception as e:
                                print(f"[AlertService] 发送至 {receiver} 失败: {e}")
                    
                    if success_count > 0:
                        print(f"[AlertService] 邮件发送完成: {success_count}/{len(receiver_emails)} 成功")
                        return  # 至少有一个成功就返回
                    else:
                        raise Exception("所有接收者都发送失败")
                else:
                    print("[AlertService] 无有效接收者邮箱")
                    return
                    
            except Exception as e:
                print(f"[AlertService] 第{attempt}次尝试失败: {e}")
                if attempt < max_retries:
                    print(f"[AlertService] {retry_delay}秒后重试...")
                    time.sleep(retry_delay)
                else:
                    print(f"[AlertService] 邮件发送最终失败，已重试{max_retries}次")

    def send_test_email(self):
        """发送测试邮件（已伪装成美股股票信息）"""
        original_subject = f"[盘口监控] 测试邮件 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        original_body = (
            "这是一封盘口监控系统的测试邮件。\n\n"
            "如果您收到这封邮件，说明邮件配置正确！\n\n"
            "---\n盘口监控与邮件提醒系统"
        )
        
        # 替换敏感词
        sanitized_subject = self._sanitize_email_content(original_subject)
        sanitized_body = self._sanitize_email_content(original_body)
        
        # 使用伪装后的标题和内容
        subject = f"[美股股票信息] {sanitized_subject}"
        body = sanitized_body
        
        try:
            self._send_email(subject, body)
            return True, "测试邮件已发送"
        except Exception as e:
            return False, f"测试邮件发送失败: {e}"

    @staticmethod
    def _sanitize_email_content(text):
        """
        替换邮件内容中的敏感字眼，伪装成美股股票信息
        :param text: 原始文本
        :return: 替换后的文本
        """
        # 敏感词替换映射表
        replacements = {
            # 比赛相关
            '比赛': '股票',
            '球队': '公司',
            '主队': 'AAPL',
            '客队': 'TSLA',
            '对阵': 'vs',
            '比分': '价格比',
            '进球': '涨幅',
            '球': '%',
            
            # 盘口相关
            '盘口': '指数',
            '亚盘': '技术指标',
            '大小球': '波动率',
            '初盘': '开盘价',
            '水位': '收益率',
            '大球': '上涨',
            '小球': '下跌',
            '半球': '0.5%',
            '一球': '1.0%',
            '平手': '持平',
            
            # 时间相关
            '上半场': '早盘',
            '下半场': '午盘',
            '分钟': '分钟',
            '中场': '盘中',
            
            # 告警类型
            '达标': '触发',
            '无进球': '无波动',
            '仅0球': '无涨幅',
            '仅1球': '仅1%涨幅',
            '仅2球': '仅2%涨幅',
            '仅3球': '仅3%涨幅',
            '仅4球': '仅4%涨幅',
            '仅5球': '仅5%涨幅',
            '变化': '变动',
            
            # 其他
            '监控': '监测',
            '告警': '通知',
            '提醒': '提示',
            '系统': '平台',
        }
        
        # 执行替换
        result = text
        for old_word, new_word in replacements.items():
            result = result.replace(old_word, new_word)
        
        return result

    @staticmethod
    def _get_alert_type_name(alert_type):
        """获取告警类型的中文显示名称（已脱敏，用于邮件）"""
        names = {
            'goal_reached': '全场涨幅达标',
            'first_half_goal': '早盘涨幅',
            'second_half_goal': '午盘涨幅',
            'first_half_no_goal': '早盘无波动',
            'second_half_no_goal': '午盘无波动',
            'full_match_no_goal': '全天无波动',  # v16新增
            'asian_home_odds': 'AAPL收益率达标',
            'asian_away_odds': 'TSLA收益率达标',
            'ou_over_odds': '上涨收益率达标',
            'ou_under_odds': '下跌收益率达标',
            'handicap_change_asian': '技术指标变动',
            'handicap_change_ou': '波动率变动',
            'engine_crash': '系统异常',  # v5新增
            'match_ended': '比赛结束',  # v5新增
        }
        return names.get(alert_type, alert_type)
    
    @staticmethod
    def _get_alert_type_original_name(alert_type):
        """获取告警类型的原始中文名称（未脱敏，用于日志）"""
        names = {
            'goal_reached': '全场进球达标',
            'first_half_goal': '上半场进球',
            'second_half_goal': '下半场进球',
            'first_half_no_goal': '上半场仅N球',
            'second_half_no_goal': '下半场仅N球',
            'full_match_no_goal': '全场仅N球',  # v16新增
            'asian_home_odds': '主队水位达标',
            'asian_away_odds': '客队水位达标',
            'ou_over_odds': '大球水位达标',
            'ou_under_odds': '小球水位达标',
            'handicap_change_asian': '亚盘变化',
            'handicap_change_ou': '大小球变化',
            'engine_crash': '监控引擎崩溃',  # v5新增
            'match_ended': '比赛结束',  # v5新增
        }
        return names.get(alert_type, alert_type)

    def reset_counter(self):
        """重置告警计数器"""
        self.total_alerts = 0
