#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统配置对话框 - 统一管理邮件和代理配置
功能：
1. 邮件SMTP配置
2. 代理池配置（账密认证模式）
3. 配置持久化（JSON文件）
"""

import json
import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QTabWidget,
    QWidget, QGroupBox, QMessageBox, QCheckBox, QListWidget,
    QListWidgetItem
)
from PyQt5.QtCore import Qt


class EmailService:
    """SMTP邮件发送服务"""

    def __init__(self, smtp_server='', smtp_port=465, sender_email='', sender_password=''):
        self.smtp_server = smtp_server
        self.smtp_port = int(smtp_port)
        self.sender_email = sender_email
        self.sender_password = sender_password

    def send(self, receiver_email, subject, body, html_body=None):
        """发送邮件"""
        if not all([self.smtp_server, self.sender_email, self.sender_password]):
            return False, "邮件配置不完整"
        
        if isinstance(receiver_email, list):
            receivers = [e.strip() for e in receiver_email if e.strip()]
        elif isinstance(receiver_email, str):
            receivers = [e.strip() for e in receiver_email.replace(';', ',').split(',') if e.strip()]
        else:
            return False, "收件人格式错误"
        
        if not receivers:
            return False, "未设置收件邮箱"

        try:
            if html_body:
                msg = MIMEText(html_body, 'html', 'utf-8')
            else:
                msg = MIMEText(body, 'plain', 'utf-8')

            msg['From'] = self.sender_email
            msg['To'] = ', '.join(receivers)
            msg['Subject'] = Header(subject, 'utf-8')
            msg['Date'] = formatdate(localtime=True)

            success = False
            last_error = None

            # 方式1: SSL连接
            try:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=15) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.sendmail(self.sender_email, receivers, msg.as_string())
                    success = True
            except Exception as e_ssl:
                last_error = f"SSL: {e_ssl}"

                # 方式2: TLS连接
                try:
                    with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=15) as server:
                        server.starttls()
                        server.login(self.sender_email, self.sender_password)
                        server.sendmail(self.sender_email, receivers, msg.as_string())
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
        """测试SMTP连接"""
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.login(self.sender_email, self.sender_password)
                return True, "连接成功"
        except Exception as e:
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.sender_email, self.sender_password)
                    return True, "连接成功(TLS)"
            except Exception as e2:
                return False, str(e2)


# ===== macOS .app 配置路径辅助函数 =====
if sys.platform == 'darwin':
    APP_NAME = "盘口监控邮件提醒"
    APP_CONFIG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
else:
    APP_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_config_path(filename):
    """获取配置文件路径（优先用户配置目录，其次.app资源目录）"""
    import sys as _sys
    
    # 1. 用户配置目录（可写）
    user_path = os.path.join(APP_CONFIG_DIR, filename)
    
    # 2. .app 资源目录（打包内置，只读）
    bundle_path = None
    try:
        bundle_path = os.path.join(_sys._MEIPASS, filename)
    except (AttributeError, ImportError):
        # 未打包：当前目录
        return user_path
    
    # 打包模式下：用户目录优先
    if os.path.exists(user_path):
        return user_path
    return bundle_path

# ========================================

class SystemConfigDialog(QDialog):
    """系统配置对话框（邮件 + 代理）"""

    EMAIL_CONFIG_FILE = "email_config.json"
    PROXY_CONFIG_FILE = "proxy_config.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 系统配置")
        self.setMinimumSize(650, 500)
        self.setModal(True)
        
        # 加载配置
        self.email_config = self._load_email_config()
        self.proxy_config = self._load_proxy_config()
        
        # 创建UI
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # 选项卡
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # 邮件配置选项卡
        email_tab = self._create_email_tab()
        self.tabs.addTab(email_tab, "📧 邮件配置")
        
        # 代理配置选项卡
        proxy_tab = self._create_proxy_tab()
        self.tabs.addTab(proxy_tab, "🌐 代理配置")
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        self.save_all_btn = QPushButton("💾 保存所有配置")
        self.save_all_btn.setMinimumHeight(40)
        self.save_all_btn.clicked.connect(self._on_save_all)
        btn_layout.addWidget(self.save_all_btn)
        
        close_btn = QPushButton("关闭")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    # ==================== 邮件配置 ====================
    def _create_email_tab(self):
        """创建邮件配置选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # SMTP服务器
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("SMTP服务器:"))
        self.smtp_server_input = QLineEdit(self.email_config.get('smtp_server', ''))
        self.smtp_server_input.setPlaceholderText("如: smtp.qq.com / smtp.163.com")
        row1.addWidget(self.smtp_server_input)
        layout.addLayout(row1)
        
        # 端口 + 发件人
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("端口:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(self.email_config.get('smtp_port', 465)))
        row2.addWidget(self.port_spin)
        row2.addWidget(QLabel("发件邮箱:"))
        self.sender_input = QLineEdit(self.email_config.get('sender_email', ''))
        self.sender_input.setPlaceholderText("your_email@qq.com")
        row2.addWidget(self.sender_input)
        layout.addLayout(row2)
        
        # 授权码/密码
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("授权码/密码:"))
        self.password_input = QLineEdit(self.email_config.get('sender_password', ''))
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("QQ邮箱请填授权码而非密码")
        row3.addWidget(self.password_input)
        layout.addLayout(row3)
        
        # 收件人管理
        receiver_group = QGroupBox("收件邮箱列表")
        receiver_layout = QVBoxLayout(receiver_group)
        
        self.receiver_list = QListWidget()
        self.receiver_list.setMinimumHeight(100)
        self._refresh_receiver_list()
        receiver_layout.addWidget(self.receiver_list)
        
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
        
        # 测试邮件按钮
        test_btn = QPushButton("📧 发送测试邮件")
        test_btn.setMinimumHeight(40)
        test_btn.clicked.connect(self._test_email)
        layout.addWidget(test_btn)
        
        layout.addStretch()
        
        return widget
    
    def _refresh_receiver_list(self):
        """刷新收件人列表"""
        if not hasattr(self, 'receiver_list'):
            return
        
        self.receiver_list.clear()
        receiver_emails_str = self.email_config.get('receiver_emails', '')
        
        if receiver_emails_str:
            emails = [e.strip() for e in receiver_emails_str.replace(';', ',').split(',') if e.strip()]
            for email in emails:
                item = QListWidgetItem(email)
                self.receiver_list.addItem(item)
    
    def _show_add_receiver_dialog(self):
        """显示添加邮箱对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加收件邮箱")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("邮箱地址:"))
        email_input = QLineEdit()
        email_input.setPlaceholderText("例如: user@example.com")
        input_layout.addWidget(email_input)
        layout.addLayout(input_layout)
        
        hint_label = QLabel("提示: 可以输入多个邮箱，用逗号或分号分隔")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(hint_label)
        
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
            
            import re
            new_emails = [e.strip() for e in emails_text.replace(';', ',').split(',') if e.strip()]
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
                current_emails_str = self.email_config.get('receiver_emails', '')
                if current_emails_str:
                    current_emails = [e.strip() for e in current_emails_str.replace(';', ',').split(',') if e.strip()]
                else:
                    current_emails = []
                
                for email in valid_emails:
                    if email not in current_emails:
                        current_emails.append(email)
                
                self.email_config['receiver_emails'] = ', '.join(current_emails)
                self._refresh_receiver_list()
                dialog.accept()
        
        ok_btn.clicked.connect(on_ok)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
    
    def _remove_selected_receiver(self):
        """删除选中的邮箱"""
        selected_items = self.receiver_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先选择要删除的邮箱")
            return
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_items)} 个邮箱吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            current_emails_str = self.email_config.get('receiver_emails', '')
            if current_emails_str:
                current_emails = [e.strip() for e in current_emails_str.replace(';', ',').split(',') if e.strip()]
            else:
                current_emails = []
            
            for item in selected_items:
                email = item.text()
                if email in current_emails:
                    current_emails.remove(email)
            
            self.email_config['receiver_emails'] = ', '.join(current_emails)
            self._refresh_receiver_list()
    
    def send_test_email_from_config(self):
        """v8新增: 从配置发送测试邮件（无需UI）"""
        email_config = self.get_email_config()
        
        smtp_server = email_config.get('smtp_server', '')
        smtp_port = email_config.get('smtp_port', 465)
        sender_email = email_config.get('sender_email', '')
        sender_password = email_config.get('sender_password', '')
        receiver = email_config.get('receiver_emails', '')
        
        if not all([smtp_server, sender_email, sender_password]):
            return False, "邮件配置不完整"
        
        if not receiver:
            return False, "未设置收件邮箱"
        
        svc = EmailService(smtp_server, smtp_port, sender_email, sender_password)
        return svc.send(receiver, "盘口监控 - 邮件测试", "这是一封测试邮件。\n\n--- 盘口监控系统")
    
    def _test_email(self):
        """测试邮件发送（可被主窗口调用）"""
        smtp_server = self.smtp_server_input.text().strip()
        smtp_port = self.port_spin.value()
        sender_email = self.sender_input.text().strip()
        sender_password = self.password_input.text().strip()
        
        if not all([smtp_server, sender_email, sender_password]):
            QMessageBox.warning(self, "警告", "请先填写完整的邮件配置")
            return False, "配置不完整"
        
        receiver = self.email_config.get('receiver_emails', '')
        if not receiver:
            QMessageBox.warning(self, "警告", "请先添加收件邮箱")
            return False, "未设置收件邮箱"
        
        svc = EmailService(smtp_server, smtp_port, sender_email, sender_password)
        success, msg = svc.send(receiver, "盘口监控 - 邮件测试", "这是一封测试邮件。\n\n--- 盘口监控系统")
        
        if success:
            QMessageBox.information(self, "成功", f"测试邮件发送成功！\n\n{msg}")
        else:
            QMessageBox.critical(self, "失败", f"测试邮件发送失败！\n\n{msg}")
        
        return success, msg
    
    # ==================== 代理配置 ====================
    def _create_proxy_tab(self):
        """创建代理配置选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # 代理开关
        self.proxy_enabled_cb = QCheckBox("启用代理")
        self.proxy_enabled_cb.setChecked(self.proxy_config.get('enabled', False))
        layout.addWidget(self.proxy_enabled_cb)
        
        # API接口地址
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("API接口:"))
        self.api_url_input = QLineEdit(self.proxy_config.get('api_url', ''))
        self.api_url_input.setPlaceholderText("https://share.proxy.qg.net/get?key=xxx&num=50&format=txt")
        row1.addWidget(self.api_url_input)
        layout.addLayout(row1)
        
        # 每次提取数量
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("提取数量:"))
        self.extract_num_spin = QSpinBox()
        self.extract_num_spin.setRange(1, 100)
        self.extract_num_spin.setValue(int(self.proxy_config.get('extract_num', 10)))
        self.extract_num_spin.setSuffix(" 个IP")
        row2.addWidget(self.extract_num_spin)
        row2.addStretch()
        layout.addLayout(row2)
        
        # v8.3新增: 代理认证信息（如果需要）
        auth_group = QGroupBox("🔐 代理认证（可选）")
        auth_layout = QFormLayout(auth_group)
        
        self.auth_username_input = QLineEdit(self.proxy_config.get('auth_username', ''))
        self.auth_username_input.setPlaceholderText("如果代理需要认证，填写用户名")
        auth_layout.addRow("用户名:", self.auth_username_input)
        
        self.auth_password_input = QLineEdit(self.proxy_config.get('auth_password', ''))
        self.auth_password_input.setEchoMode(QLineEdit.Password)
        self.auth_password_input.setPlaceholderText("如果代理需要认证，填写密码")
        auth_layout.addRow("密码:", self.auth_password_input)
        
        layout.addWidget(auth_group)
        
        # 当前使用的代理（只读显示）
        current_proxy_group = QGroupBox("当前使用的代理")
        current_proxy_layout = QHBoxLayout(current_proxy_group)
        self.current_proxy_label = QLabel("未启用")
        self.current_proxy_label.setStyleSheet("color: #94a3b8; font-size: 13px;")
        current_proxy_layout.addWidget(self.current_proxy_label)
        current_proxy_layout.addStretch()
        layout.addWidget(current_proxy_group)
        
        # 说明文字
        info_group = QGroupBox("📖 配置说明")
        info_layout = QVBoxLayout(info_group)
        info_text = QLabel(
            "代理API接口说明（v11单IP轮换模式）：\n\n"
            "1. 填写代理服务商提供的API接口地址\n"
            "2. 系统每次只使用1个代理IP，所有请求都用这个IP\n"
            "3. 5分钟后自动更换一个新IP（定时轮换）\n"
            "4. 如果当前IP失效，立即用num=1获取新代理替换\n"
            "5. 支持的返回格式：txt（每行一个IP:端口）\n\n"
            "示例API：\n"
            "https://share.proxy.qg.net/get?key=YOUR_KEY&num=1&format=txt"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        layout.addWidget(info_group)
        
        # 测试代理按钮
        test_proxy_btn = QPushButton("🌐 测试代理连接")
        test_proxy_btn.setMinimumHeight(40)
        test_proxy_btn.clicked.connect(self._test_proxy)
        layout.addWidget(test_proxy_btn)
        
        # 提取测试按钮
        extract_test_btn = QPushButton("📥 测试API提取")
        extract_test_btn.setMinimumHeight(40)
        extract_test_btn.clicked.connect(self._test_api_extract)
        layout.addWidget(extract_test_btn)
        
        layout.addStretch()
        
        return widget
    
    def _test_proxy(self):
        """v11新增: 测试代理连接（单IP模式）"""
        if not self.proxy_enabled_cb.isChecked():
            QMessageBox.warning(self, "警告", "请先启用代理")
            return
            
        api_url = self.api_url_input.text().strip()
        if not api_url:
            QMessageBox.warning(self, "警告", "请先填写API接口地址")
            return
            
        # v11策略: 从 API 提取1个代理进行测试
        try:
            proxies = self._extract_proxies_from_api(api_url, num=1)
            if not proxies:
                QMessageBox.critical(self, "失败", "API提取失败，未获取到代理IP")
                return
                
            # 使用第一个代理测试
            test_proxy = proxies[0]
            proxy_url = f"http://{test_proxy}"
            proxies_dict = {
                "http": proxy_url,
                "https": proxy_url,
            }
                
            # v8修复: 使用HTTP网站测试（避免HTTPS代理认证问题）
            test_url = "http://httpbin.org/ip"  # 返回当前IP的测试网站
                
            try:
                response = requests.get(test_url, proxies=proxies_dict, timeout=10)
                    
                if response.status_code == 200:
                    ip_info = response.json().get('origin', '未知')
                    self.current_proxy_label.setText(f"✓ {test_proxy}")
                    self.current_proxy_label.setStyleSheet("color: #10b981; font-size: 13px;")
                    QMessageBox.information(
                        self,
                        "成功",
                        f"代理连接成功！\n\n"
                        f"当前出口IP: {ip_info}\n"
                        f"使用代理: {test_proxy}\n\n"
                        f"注意: v11采用单IP轮换模式，所有请求都用这个IP，5分钟后自动更换"
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "失败",
                        f"代理连接失败！\n\nHTTP状态码: {response.status_code}"
                    )
            except requests.exceptions.ProxyError as e:
                # 代理认证错误
                QMessageBox.critical(
                    self,
                    "代理认证失败",
                    f"代理需要认证！\n\n"
                    f"错误: {str(e)}\n\n"
                    f"可能原因：\n"
                    f"1. 此代理服务商返回的代理需要用户名密码认证\n"
                    f"2. 请在下方填写认证信息\n"
                    f"3. 或更换为不需要认证的代理API"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "失败",
                    f"代理连接失败！\n\n错误信息: {str(e)}\n\n"
                    f"请检查：\n"
                    f"1. API接口地址是否正确\n"
                    f"2. 网络连接是否正常\n"
                    f"3. 代理IP是否可用\n"
                    f"4. 代理是否需要认证"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "失败",
                f"测试过程出错！\n\n错误信息: {str(e)}"
            )
    
    def _test_api_extract(self):
        """测试API提取功能"""
        api_url = self.api_url_input.text().strip()
        if not api_url:
            QMessageBox.warning(self, "警告", "请先填写API接口地址")
            return
        
        try:
            proxies = self._extract_proxies_from_api(api_url, 5)
            if not proxies:
                QMessageBox.warning(self, "警告", "API返回空，未获取到代理IP")
                return
            
            # 显示提取结果
            proxy_list = "\n".join([f"{i+1}. {p}" for i, p in enumerate(proxies[:10])])
            if len(proxies) > 10:
                proxy_list += f"\n... 还有 {len(proxies)-10} 个"
            
            QMessageBox.information(
                self,
                "成功",
                f"API提取成功！\n\n"
                f"共获取 {len(proxies)} 个代理IP\n\n"
                f"前10个：\n{proxy_list}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "失败",
                f"API提取失败！\n\n错误信息: {str(e)}"
            )
    
    def _extract_proxies_from_api(self, api_url, num=10):
        """v8新增: 从API提取代理IP列表
        :param api_url: API接口地址
        :param num: 提取数量
        :return: 代理IP列表 ['IP:端口', ...]
        """
        try:
            # v8.3修复: 清理URL中的转义字符
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
            
            response = requests.get(api_url, timeout=10)
            if response.status_code != 200:
                print(f"[代理API] ❌ HTTP错误: {response.status_code}")
                return []
            
            # 解析返回的txt内容
            text = response.text.strip()
            if not text:
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
            
            return valid_proxies
            
        except Exception as e:
            print(f"[代理API] ❌ 提取失败: {e}")
            return []
    
    # ==================== 配置加载/保存 ====================
    def _load_email_config(self):
        """加载邮件配置"""
        default = {
            'smtp_server': '',
            'smtp_port': 465,
            'sender_email': '',
            'sender_password': '',
            'receiver_emails': '',
        }
        try:
            config_path = _get_config_path("email_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    if 'receiver_email' in saved and 'receiver_emails' not in saved:
                        saved['receiver_emails'] = saved.pop('receiver_email')
                    default.update(saved)
        except Exception:
            pass
        return default
    
    def _load_proxy_config(self):
        """加载代理配置"""
        default = {
            'enabled': False,
            'api_url': '',
            'extract_num': 10,
            'auth_username': '',  # v8.3新增
            'auth_password': '',  # v8.3新增
        }
        try:
            config_path = _get_config_path("proxy_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    default.update(saved)
        except Exception:
            pass
        return default
    
    def save_email_config(self):
        """保存邮件配置（始终写入用户配置目录）"""
        self._collect_email_config()
        try:
            os.makedirs(APP_CONFIG_DIR, exist_ok=True)
            save_path = os.path.join(APP_CONFIG_DIR, "email_config.json")
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.email_config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[EmailConfig] 保存失败: {e}")
            return False
    
    def save_proxy_config(self):
        """保存代理配置（始终写入用户配置目录）"""
        try:
            config = {
                'enabled': self.proxy_enabled_cb.isChecked(),
                'api_url': self.api_url_input.text().strip(),
                'extract_num': self.extract_num_spin.value(),
                'auth_username': self.auth_username_input.text().strip(),  # v8.3新增
                'auth_password': self.auth_password_input.text().strip(),  # v8.3新增
            }
            os.makedirs(APP_CONFIG_DIR, exist_ok=True)
            save_path = os.path.join(APP_CONFIG_DIR, "proxy_config.json")
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.proxy_config = config
            return True
        except Exception as e:
            print(f"[ProxyConfig] 保存失败: {e}")
            return False
    
    def _collect_email_config(self):
        """收集邮件配置"""
        self.email_config['smtp_server'] = self.smtp_server_input.text().strip()
        self.email_config['smtp_port'] = self.port_spin.value()
        self.email_config['sender_email'] = self.sender_input.text().strip()
        self.email_config['sender_password'] = self.password_input.text().strip()
    
    def _on_save_all(self):
        """保存所有配置"""
        self._collect_email_config()
        
        email_ok = self.save_email_config()
        proxy_ok = self.save_proxy_config()
        
        if email_ok and proxy_ok:
            QMessageBox.information(self, "成功", "所有配置已保存！")
            self.accept()
        elif email_ok:
            QMessageBox.information(self, "部分成功", "邮件配置已保存，代理配置保存失败")
        elif proxy_ok:
            QMessageBox.information(self, "部分成功", "代理配置已保存，邮件配置保存失败")
        else:
            QMessageBox.critical(self, "失败", "配置保存失败，请重试")
    
    # ==================== 获取配置 ====================
    def get_email_config(self):
        """获取邮件配置"""
        self._collect_email_config()
        return self.email_config.copy()
    
    def get_proxy_config(self):
        """获取代理配置"""
        return {
            'enabled': self.proxy_enabled_cb.isChecked(),
            'api_url': self.api_url_input.text().strip(),
            'extract_num': self.extract_num_spin.value(),
            'auth_username': self.auth_username_input.text().strip(),  # v8.3新增
            'auth_password': self.auth_password_input.text().strip(),  # v8.3新增
        }
