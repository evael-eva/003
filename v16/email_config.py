#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
邮件配置管理 - SMTP设置读写和邮件发送服务
功能：
1. 提供SMTP配置的GUI界面（对话框）
2. 封装smtplib的邮件发送逻辑
3. 支持SSL/TLS加密连接
4. 配置持久化（可选，使用JSON文件保存）
"""

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate


class EmailService:
    """SMTP邮件发送服务"""

    def __init__(self, smtp_server='', smtp_port=465, sender_email='', sender_password=''):
        self.smtp_server = smtp_server
        self.smtp_port = int(smtp_port)
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send(self, receiver_email, subject, body, html_body=None):
        """
        发送邮件
        :param receiver_email: 收件人邮箱（可以是字符串用逗号分隔，也可以是列表）
        :param subject: 邮件主题
        :param body: 邮件正文(纯文本)
        :param html_body: 邮件HTML正文（可选）
        :return: (success: bool, message: str)
        """
        if not all([self.smtp_server, self.sender_email, self.sender_password]):
            return False, "邮件配置不完整"
        
        # 处理接收者邮箱
        if isinstance(receiver_email, list):
            receivers = [e.strip() for e in receiver_email if e.strip()]
        elif isinstance(receiver_email, str):
            receivers = [e.strip() for e in receiver_email.replace(';', ',').split(',') if e.strip()]
        else:
            return False, "收件人格式错误"
        
        if not receivers:
            return False, "未设置收件邮箱"

        try:
            # 构建邮件
            if html_body:
                msg = MIMEText(html_body, 'html', 'utf-8')
            else:
                msg = MIMEText(body, 'plain', 'utf-8')

            msg['From'] = self.sender_email
            msg['To'] = ', '.join(receivers)  # v5优化: 多个接收者
            msg['Subject'] = Header(subject, 'utf-8')
            msg['Date'] = formatdate(localtime=True)

            # 发送（优先尝试SSL，失败则TLS）
            success = False
            last_error = None

            # 方式1: SSL连接（端口465常用）
            try:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=15) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.sendmail(self.sender_email, receivers, msg.as_string())  # v5优化: 使用列表
                    success = True
            except Exception as e_ssl:
                last_error = f"SSL: {e_ssl}"

                # 方式2: TLS连接（端口587常用）
                try:
                    with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15) as server:
                        server.starttls()
                        server.login(self.sender_email, self.sender_password)
                        server.sendmail(self.sender_email, receivers, msg.as_string())  # v5优化: 使用列表
                        success = True
                except Exception as e_tls:
                    last_error = f"TLS: {e_tls}"

            if success:
                return True, "发送成功"
            else:
                return False, f"发送失败: {last_error}"

        except Exception as e:
            return False, f"异常: {e}"

    def test_connection(self):
        """测试SMTP连接是否可用"""
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.login(self.sender_email, self.sender_password)
                return True, "连接成功"
        except Exception as e:
            # 再试TLS
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.sender_email, self.sender_password)
                    return True, "连接成功(TLS)"
            except Exception as e2:
                return False, str(e2)


class EmailConfigDialog:
    """
    邮件配置对话框（PyQt5 QWidget）
    在主窗口中作为面板嵌入或独立弹出对话框使用
    """

    CONFIG_FILE = "email_config.json"

    def __init__(self, parent=None):
        self.parent = parent
        self.config = self._load_config()

    def _load_config(self):
        """从JSON文件加载配置"""
        default = {
            'smtp_server': '',
            'smtp_port': 465,
            'sender_email': '',
            'sender_password': '',
            'receiver_emails': '',  # v5优化: 支持多个邮箱，用逗号分隔
        }
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    # v5兼容: 如果旧配置有receiver_email，转换为receiver_emails
                    if 'receiver_email' in saved and 'receiver_emails' not in saved:
                        saved['receiver_emails'] = saved.pop('receiver_email')
                    default.update(saved)
        except Exception:
            pass
        return default

    def save_config(self):
        """保存配置到JSON文件"""
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[EmailConfig] 保存失败: {e}")
            return False

    def get_config(self):
        """获取当前配置字典"""
        return self.config.copy()

    def update_config(self, **kwargs):
        """更新配置项"""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
        self.save_config()

    def create_settings_widget(self):
        """
        创建邮件设置的UI控件组（QWidget），供主窗口嵌入使用
        返回一个包含所有输入控件的dict
        """
        from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout,
                                     QLabel, QLineEdit, QSpinBox, QPushButton,
                                     QWidget, QListWidget, QListWidgetItem,
                                     QDialog, QDialogButtonBox, QMessageBox)
        from PyQt5.QtCore import Qt

        widget = QGroupBox("📧 邮件通知设置")
        layout = QVBoxLayout(widget)

        # SMTP服务器
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("SMTP服务器:"))
        self.smtp_server_input = QLineEdit(self.config.get('smtp_server', ''))
        self.smtp_server_input.setPlaceholderText("如: smtp.qq.com / smtp.163.com")
        row1.addWidget(self.smtp_server_input)
        layout.addLayout(row1)

        # 端口 + 发件人
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("端口:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(self.config.get('smtp_port', 465)))
        row2.addWidget(self.port_spin)
        row2.addWidget(QLabel("发件邮箱:"))
        self.sender_input = QLineEdit(self.config.get('sender_email', ''))
        self.sender_input.setPlaceholderText("your_email@qq.com")
        row2.addWidget(self.sender_input)
        layout.addLayout(row2)

        # 授权码/密码
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("授权码/密码:"))
        self.password_input = QLineEdit(self.config.get('sender_password', ''))
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("QQ邮箱请填授权码而非密码")
        row3.addWidget(self.password_input)
        layout.addLayout(row3)

        # v5优化: 收件人管理 - 显示列表 + 管理按钮
        receiver_group = QGroupBox("收件邮箱列表")
        receiver_layout = QVBoxLayout(receiver_group)
        
        # 邮箱列表
        self.receiver_list = QListWidget()
        self.receiver_list.setMinimumHeight(100)
        self._refresh_receiver_list()  # 加载现有邮箱
        receiver_layout.addWidget(self.receiver_list)
        
        # 管理按钮
        btn_layout = QHBoxLayout()
        self.add_receiver_btn = QPushButton("➕ 添加邮箱")
        self.add_receiver_btn.setFixedWidth(90)
        self.add_receiver_btn.clicked.connect(self._show_add_receiver_dialog)
        btn_layout.addWidget(self.add_receiver_btn)
        
        self.remove_receiver_btn = QPushButton("➖ 删除选中")
        self.remove_receiver_btn.setFixedWidth(90)
        self.remove_receiver_btn.clicked.connect(self._remove_selected_receiver)
        btn_layout.addWidget(self.remove_receiver_btn)
        
        btn_layout.addStretch()
        receiver_layout.addLayout(btn_layout)
        
        layout.addWidget(receiver_group)

        # 底部按钮
        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("📧 发送测试邮件")
        self.save_btn = QPushButton("💾 保存配置")
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 状态标签
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        return {
            'widget': widget,
            'smtp_server': self.smtp_server_input,
            'port': self.port_spin,
            'sender_email': self.sender_input,
            'password': self.password_input,
            'receiver_list': self.receiver_list,  # v5优化: 改为列表控件
            'test_btn': self.test_btn,
            'save_btn': self.save_btn,
            'status_label': self.status_label,
        }
    
    def _refresh_receiver_list(self):
        """刷新收件人列表显示"""
        from PyQt5.QtWidgets import QListWidgetItem
        
        if not hasattr(self, 'receiver_list'):
            return
        
        self.receiver_list.clear()
        receiver_emails_str = self.config.get('receiver_emails', '')
        
        if receiver_emails_str:
            # 解析邮箱列表
            emails = [e.strip() for e in receiver_emails_str.replace(';', ',').split(',') if e.strip()]
            for email in emails:
                item = QListWidgetItem(email)
                self.receiver_list.addItem(item)
    
    def _show_add_receiver_dialog(self):
        """显示添加邮箱对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
        
        dialog = QDialog(self.parent if hasattr(self, 'parent') else None)
        dialog.setWindowTitle("添加收件邮箱")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # 输入框
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("邮箱地址:"))
        email_input = QLineEdit()
        email_input.setPlaceholderText("例如: user@example.com")
        input_layout.addWidget(email_input)
        layout.addLayout(input_layout)
        
        # 提示
        hint_label = QLabel("提示: 可以输入多个邮箱，用逗号或分号分隔")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(hint_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        def on_ok():
            emails_text = email_input.text().strip()
            if not emails_text:
                QMessageBox.warning(dialog, "警告", "请输入邮箱地址")
                return
            
            # 解析并验证邮箱
            new_emails = [e.strip() for e in emails_text.replace(';', ',').split(',') if e.strip()]
            
            # 简单验证邮箱格式
            import re
            valid_emails = []
            invalid_emails = []
            for email in new_emails:
                if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                    valid_emails.append(email)
                else:
                    invalid_emails.append(email)
            
            if invalid_emails:
                reply = QMessageBox.question(
                    dialog, 
                    "警告", 
                    f"以下邮箱格式不正确，是否忽略？\n{', '.join(invalid_emails)}",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
            if valid_emails:
                # 添加到配置
                current_emails_str = self.config.get('receiver_emails', '')
                if current_emails_str:
                    current_emails = [e.strip() for e in current_emails_str.replace(';', ',').split(',') if e.strip()]
                else:
                    current_emails = []
                
                # 合并并去重
                for email in valid_emails:
                    if email not in current_emails:
                        current_emails.append(email)
                
                # 保存
                self.config['receiver_emails'] = ', '.join(current_emails)
                self._refresh_receiver_list()
                dialog.accept()
        
        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def _remove_selected_receiver(self):
        """删除选中的邮箱"""
        from PyQt5.QtWidgets import QMessageBox
        
        if not hasattr(self, 'receiver_list'):
            return
        
        selected_items = self.receiver_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self.parent if hasattr(self, 'parent') else None, "提示", "请先选择要删除的邮箱")
            return
        
        # 确认删除
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self.parent if hasattr(self, 'parent') else None,
            "确认删除",
            f"确定要删除选中的 {len(selected_items)} 个邮箱吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 获取当前所有邮箱
            current_emails_str = self.config.get('receiver_emails', '')
            if current_emails_str:
                current_emails = [e.strip() for e in current_emails_str.replace(';', ',').split(',') if e.strip()]
            else:
                current_emails = []
            
            # 删除选中的邮箱
            for item in selected_items:
                email = item.text()
                if email in current_emails:
                    current_emails.remove(email)
            
            # 更新配置
            self.config['receiver_emails'] = ', '.join(current_emails)
            self._refresh_receiver_list()

    def collect_from_widgets(self, widgets_dict):
        """从UI控件收集当前值并更新配置"""
        self.config['smtp_server'] = widgets_dict['smtp_server'].text().strip()
        self.config['smtp_port'] = widgets_dict['port'].value()
        self.config['sender_email'] = widgets_dict['sender_email'].text().strip()
        self.config['sender_password'] = widgets_dict['password'].text().strip()
        # v5优化: receiver_emails已经在添加/删除时实时更新，这里不需要再从控件读取

    def apply_to_alert_service(self, alert_svc):
        """将当前配置应用到AlertService实例"""
        self.collect_from_ui_if_needed()
        alert_svc.configure_email(
            self.config.get('smtp_server', ''),
            int(self.config.get('smtp_port', 465)),
            self.config.get('sender_email', ''),
            self.config.get('sender_password', ''),
            self.config.get('receiver_emails', ''),  # v5优化: 改为receiver_emails
        )

    def collect_from_ui_if_needed(self):
        """如果UI已创建，从控件收集值（安全调用）"""
        if hasattr(self, 'smtp_server_input'):
            self.config['smtp_server'] = self.smtp_server_input.text().strip()
            self.config['smtp_port'] = self.port_spin.value()
            self.config['sender_email'] = self.sender_input.text().strip()
            self.config['sender_password'] = self.password_input.text().strip()
            # v5优化: receiver_emails已经在添加/删除时实时更新

    def send_test_email(self):
        """发送测试邮件（供主窗口调用）"""
        svc = EmailService(
            self.config.get('smtp_server', ''),
            int(self.config.get('smtp_port', 465)),
            self.config.get('sender_email', ''),
            self.config.get('sender_password', ''),
        )
        receiver = self.config.get('receiver_emails', '')  # v5优化
        if not receiver:
            return False, "未设置收件邮箱"
        subject = "盘口监控 - 邮件测试"
        body = "这是一封测试邮件。如果您收到此邮件，说明邮件配置正确。\n\n--- 盘口监控系统"
        return svc.send(receiver, subject, body)
