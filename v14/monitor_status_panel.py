#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
监控状态面板 - 实时显示每场比赛的监控健康状况
功能：
1. 显示所有正在监控的比赛列表
2. 实时显示每场比赛的状态（正常/异常/离线）
3. 显示最后更新时间、数据获取成功率
4. 支持手动刷新和自动清理失效比赛
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QBrush


class MonitorStatusPanel(QWidget):
    """监控状态面板"""
    
    # 信号定义
    remove_match_requested = pyqtSignal(str)  # 请求移除某场比赛
    log_message_requested = pyqtSignal(str)  # v7修复: 请求发送日志消息
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 数据存储
        self.match_status_data = {}  # {match_id: status_info}
        
        # 初始化UI
        self._init_ui()
        
        # 自动刷新定时器（每30秒更新一次状态显示）
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_status_display)
        self.refresh_timer.start(30000)  # 30秒
    
    def _init_ui(self):
        """初始化界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # === 标题栏 ===
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 4, 4, 4)
        
        title_label = QLabel("📊 监控状态面板")
        title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title_label.setStyleSheet("color: #60a5fa; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 统计信息
        self.stats_label = QLabel("总计: 0 | 正常: 0 | 异常: 0 | 离线: 0")
        self.stats_label.setStyleSheet("""
            color: #94a3b8; font-size: 13px;
            background-color: #1e293b; padding: 4px 12px;
            border-radius: 8px; border: 1px solid #334155;
        """)
        header_layout.addWidget(self.stats_label)
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.clicked.connect(self._manual_refresh)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        header_layout.addWidget(refresh_btn)
        
        main_layout.addWidget(header_widget)
        
        # === 状态表格 ===
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(7)
        self.status_table.setHorizontalHeaderLabels([
            '比赛',
            '状态',
            '最后更新',
            '连续失败',
            '成功率',
            '运行时长',
            '操作'
        ])
        
        # 设置表格样式
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.status_table.setSelectionMode(QTableWidget.SingleSelection)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.verticalHeader().setVisible(False)
        
        # 设置列宽
        self.status_table.setColumnWidth(0, 250)  # 比赛
        self.status_table.setColumnWidth(1, 80)   # 状态
        self.status_table.setColumnWidth(2, 120)  # 最后更新
        self.status_table.setColumnWidth(3, 80)   # 连续失败
        self.status_table.setColumnWidth(4, 80)   # 成功率
        self.status_table.setColumnWidth(5, 100)  # 运行时长
        self.status_table.setColumnWidth(6, 80)   # 操作
        
        # 表头样式
        self.status_table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #1e293b;
                color: #60a5fa;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #334155;
            }
        """)
        
        # 表格样式
        self.status_table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                color: #e2e8f0;
                gridline-color: #334155;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #1e40af;
            }
        """)
        
        main_layout.addWidget(self.status_table)
        
        # === 底部说明 ===
        info_label = QLabel(
            "💡 提示: 绿色=正常 | 黄色=警告(连续失败≥3次) | 红色=异常(连续失败≥5次) | 灰色=离线"
        )
        info_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 4px;")
        info_label.setWordWrap(True)
        main_layout.addWidget(info_label)
    
    def update_match_status(self, match_id, match_name, status_info):
        """
        更新某场比赛的监控状态
        :param match_id: 比赛ID
        :param match_name: 比赛名称（主队 vs 客队）
        :param status_info: 状态信息字典
            {
                'status': 'normal' | 'warning' | 'error' | 'offline',
                'last_update': datetime,
                'consecutive_failures': int,
                'total_requests': int,
                'successful_requests': int,
                'start_time': datetime
            }
        """
        self.match_status_data[match_id] = {
            'name': match_name,
            **status_info
        }
        
        # 立即更新显示
        self._update_status_display()
    
    def remove_match(self, match_id):
        """移除某场比赛的状态记录"""
        if match_id in self.match_status_data:
            del self.match_status_data[match_id]
            self._update_status_display()
    
    def clear_all(self):
        """清空所有状态记录"""
        self.match_status_data.clear()
        self._update_status_display()
    
    def _manual_refresh(self):
        """手动刷新"""
        self._update_status_display()
        
        # v7修复: 使用信号发送日志消息，而不是直接访问父组件
        from datetime import datetime
        now = datetime.now().strftime('%H:%M:%S')
        self.log_message_requested.emit(f"[监控状态] 手动刷新完成 ({now})")
    
    def _update_status_display(self):
        """更新状态显示"""
        from datetime import datetime
        
        # 清空表格
        self.status_table.setRowCount(0)
        
        if not self.match_status_data:
            return
        
        # 统计数据
        total = len(self.match_status_data)
        normal_count = 0
        warning_count = 0
        error_count = 0
        offline_count = 0
        
        # 填充表格
        for match_id, info in self.match_status_data.items():
            row = self.status_table.rowCount()
            self.status_table.insertRow(row)
            
            status = info.get('status', 'offline')
            
            # 统计
            if status == 'normal':
                normal_count += 1
            elif status == 'warning':
                warning_count += 1
            elif status == 'error':
                error_count += 1
            else:
                offline_count += 1
            
            # 1. 比赛名称
            name_item = QTableWidgetItem(info.get('name', '未知'))
            name_item.setToolTip(f"ID: {match_id}\n{info.get('name', '')}")
            self.status_table.setItem(row, 0, name_item)
            
            # 2. 状态（带颜色）
            status_item = QTableWidgetItem(self._get_status_text(status))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setBackground(QBrush(self._get_status_color(status)))
            self.status_table.setItem(row, 1, status_item)
            
            # 3. 最后更新时间
            last_update = info.get('last_update')
            if last_update:
                time_str = last_update.strftime('%H:%M:%S')
                # 计算距今多久
                elapsed = (datetime.now() - last_update).total_seconds()
                if elapsed < 60:
                    time_text = f"{int(elapsed)}秒前"
                elif elapsed < 3600:
                    time_text = f"{int(elapsed/60)}分钟前"
                else:
                    time_text = f"{int(elapsed/3600)}小时前"
            else:
                time_str = '-'
                time_text = '-'
            
            time_item = QTableWidgetItem(time_text)
            time_item.setToolTip(f"最后更新: {time_str}")
            time_item.setTextAlignment(Qt.AlignCenter)
            self.status_table.setItem(row, 2, time_item)
            
            # 4. 连续失败次数
            failures = info.get('consecutive_failures', 0)
            failure_item = QTableWidgetItem(str(failures))
            failure_item.setTextAlignment(Qt.AlignCenter)
            if failures >= 5:
                failure_item.setForeground(QBrush(QColor('#ef4444')))  # 红色
            elif failures >= 3:
                failure_item.setForeground(QBrush(QColor('#f59e0b')))  # 黄色
            self.status_table.setItem(row, 3, failure_item)
            
            # 5. 成功率
            total_req = info.get('total_requests', 0)
            success_req = info.get('successful_requests', 0)
            if total_req > 0:
                success_rate = (success_req / total_req) * 100
                rate_text = f"{success_rate:.1f}%"
            else:
                success_rate = 0
                rate_text = '-'
            
            rate_item = QTableWidgetItem(rate_text)
            rate_item.setTextAlignment(Qt.AlignCenter)
            if success_rate < 50:
                rate_item.setForeground(QBrush(QColor('#ef4444')))
            elif success_rate < 80:
                rate_item.setForeground(QBrush(QColor('#f59e0b')))
            else:
                rate_item.setForeground(QBrush(QColor('#10b981')))
            self.status_table.setItem(row, 4, rate_item)
            
            # 6. 运行时长
            start_time = info.get('start_time')
            if start_time:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed < 3600:
                    duration_text = f"{int(elapsed/60)}分钟"
                elif elapsed < 86400:
                    duration_text = f"{int(elapsed/3600)}小时"
                else:
                    duration_text = f"{int(elapsed/86400)}天"
            else:
                duration_text = '-'
            
            duration_item = QTableWidgetItem(duration_text)
            duration_item.setTextAlignment(Qt.AlignCenter)
            self.status_table.setItem(row, 5, duration_item)
            
            # 7. 操作按钮
            remove_btn = QPushButton("移除")
            remove_btn.setMaximumWidth(60)
            remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #b91c1c;
                }
            """)
            remove_btn.clicked.connect(lambda checked, mid=match_id: self._on_remove_clicked(mid))
            
            # 将按钮放入单元格
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.addWidget(remove_btn)
            btn_layout.addStretch()
            
            self.status_table.setCellWidget(row, 6, btn_widget)
        
        # 更新统计信息
        self.stats_label.setText(
            f"总计: {total} | 正常: {normal_count} | 警告: {warning_count} | 异常: {error_count} | 离线: {offline_count}"
        )
    
    def _get_status_text(self, status):
        """获取状态文本"""
        status_map = {
            'normal': '✅ 正常',
            'warning': '⚠️ 警告',
            'error': '❌ 异常',
            'offline': '⭕ 离线'
        }
        return status_map.get(status, '❓ 未知')
    
    def _get_status_color(self, status):
        """获取状态颜色"""
        color_map = {
            'normal': QColor('#10b981'),   # 绿色
            'warning': QColor('#f59e0b'),  # 黄色
            'error': QColor('#ef4444'),    # 红色
            'offline': QColor('#6b7280')   # 灰色
        }
        return color_map.get(status, QColor('#6b7280'))
    
    def _on_remove_clicked(self, match_id):
        """移除按钮点击事件"""
        info = self.match_status_data.get(match_id, {})
        match_name = info.get('name', match_id)
        
        reply = QMessageBox.question(
            self,
            '确认移除',
            f'确定要移除比赛 "{match_name}" 的监控吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.remove_match_requested.emit(match_id)
    
    def closeEvent(self, event):
        """关闭时停止定时器"""
        self.refresh_timer.stop()
        super().closeEvent(event)
