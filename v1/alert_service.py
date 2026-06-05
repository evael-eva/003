#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
告警服务 - 统一管理弹窗/声音/邮件三种通知方式
功能：
1. 弹窗提醒：通过信号投递到主线程，使用PyQt5的QMessageBox弹出警告窗口（禁止在子线程直接创建Qt窗口）
2. 声音报警：使用winsound播放Windows系统提示音
3. 邮件通知：调用EmailService发送SMTP邮件

提供统一的trigger_alert()接口，根据配置决定启用哪些通知渠道。
"""

import threading
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class AlertService(QObject):
    """告警服务管理器（继承QObject以便使用信号槽）"""

    # 弹窗请求信号：(message, alert_type, timestamp)
    _popup_requested = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        # 通知开关
        self.popup_enabled = True
        self.sound_enabled = True
        self.email_enabled = False

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

    def configure_email(self, smtp_server, smtp_port, sender_email, sender_password, receiver_email):
        """配置邮件参数（注意：不自动开启email_enabled，由UI开关控制）"""
        self.email_config = {
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'sender_email': sender_email,
            'sender_password': sender_password,
            'receiver_email': receiver_email,
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

        # 并行执行各通知方式（不阻塞主线程）
        threads = []

        if self.popup_enabled:
            # 通过信号将弹窗请求安全地投递到主线程（跨线程信号自动QueuedConnection）
            self._popup_requested.emit(message, alert_type, timestamp)

        if self.sound_enabled:
            t = threading.Thread(target=self._play_sound, args=(alert_type,), daemon=True)
            threads.append(t)

        if self.email_enabled and self.email_config.get('receiver_email'):
            subject = f"[盘口监控] {self._get_alert_type_name(alert_type)} - {timestamp}"
            body = f"比赛ID: {match_id}\n告警类型: {self._get_alert_type_name(alert_type)}\n时间: {timestamp}\n\n{message}\n\n---\n此邮件由盘口监控系统自动发送"
            t = threading.Thread(target=self._send_email, args=(subject, body,), daemon=True)
            threads.append(t)

        for t in threads:
            t.start()

    def _show_popup_on_main_thread(self, message, alert_type, timestamp):
        """
        在主线程中实际执行弹窗（由 _popup_requested 信号触发，自动在主线程执行）
        这是唯一合法的 Qt UI 操作入口。
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
            }

            icon = type_icons.get(alert_type, QMessageBox.Warning)
            title = f"⚠ {self._get_alert_type_name(alert_type)}"
            full_message = f"{message}\n\n时间: {timestamp}"

            msg_box = QMessageBox(icon, title, full_message)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.setDefaultButton(QMessageBox.Ok)
            msg_box.setWindowTitle("盘口监控告警")
            msg_box.setTextFormat(Qt.PlainText)

            if self.parent_widget and not self.parent_widget.isHidden():
                msg_box.exec_()

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
        try:
            from email_config import EmailService
            svc = EmailService(
                self.email_config['smtp_server'],
                self.email_config['smtp_port'],
                self.email_config['sender_email'],
                self.email_config['sender_password'],
            )
            svc.send(self.email_config['receiver_email'], subject, body)
        except Exception as e:
            print(f"[AlertService] email send failed: {e}")

    def send_test_email(self):
        """发送测试邮件"""
        subject = f"[盘口监控] 测试邮件 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        body = (
            "这是一封盘口监控系统的测试邮件。\n\n"
            "如果您收到这封邮件，说明邮件配置正确！\n\n"
            "---\n盘口监控与邮件提醒系统"
        )
        try:
            self._send_email(subject, body)
            return True, "测试邮件已发送"
        except Exception as e:
            return False, f"测试邮件发送失败: {e}"

    @staticmethod
    def _get_alert_type_name(alert_type):
        """获取告警类型的中文显示名称"""
        names = {
            'goal_reached': '全场进球达标',
            'first_half_goal': '上半场进球',
            'second_half_goal': '下半场进球',
            'asian_home_odds': '亚盘主队水位达标',
            'asian_away_odds': '亚盘客队水位达标',
            'ou_over_odds': '大球水位达标',
            'ou_under_odds': '小球水位达标',
        }
        return names.get(alert_type, alert_type)

    def reset_counter(self):
        """重置告警计数器"""
        self.total_alerts = 0
