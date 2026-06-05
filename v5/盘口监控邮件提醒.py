#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
盘口监控与邮件提醒系统 - 主程序
基于PyQt5的足球比赛盘口实时监控与邮件提醒系统
从7M体育(titan007.com)获取赛事初盘数据，支持按亚盘/大小球盘口条件筛选比赛，
实时监控盘口水位变化和进球数，达到用户设定阈值时触发弹窗、声音报警和邮件通知。

使用方法：
  python 盘口监控邮件提醒.py

依赖安装：
  pip install PyQt5 DrissionPage requests beautifulsoup4
"""

import sys
import os
import time
import random
import json
from datetime import datetime

# 确保当前目录在sys.path中，以便导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QTextEdit, QHeaderView, QMessageBox, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QCheckBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QComboBox, QScrollArea, QProgressBar, QStatusBar,
    QDialog, QDateEdit, QFormLayout, QTabWidget,
    QAbstractItemView, QSizePolicy, QToolTip, QCheckBox, QTabWidget,
    QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QColor, QBrush, QIcon, QPalette, QCursor

# 导入自定义模块
from filter_controller import FilterController
from odds_fetcher import OddsFetcher
from monitor_engine import MonitorEngine
from alert_service import AlertService
from email_config import EmailConfigDialog
from profile_manager import ProfileManager


# ============================================================
# 常量定义
# ============================================================

ASIAN_HANDICAP_ITEMS = [
    ('-0.25', '平/半(受)'), ('-0.5', '半球(受)'), ('-0.75', '半/一(受)'),
    ('-1', '一球(受)'), ('-1.25', '一/球半(受)'), ('-1.5', '球半(受)'),
    ('-1.75', '球半/两(受)'), ('-2', '两球(受)'),
    ('-2.25', '两/两球半(受)'), ('-2.75', '两球半/三(受)'),
    ('-3', '三球(受)'), ('-3.5', '三球半(受)'), ('-5.25', '五/五球半'),
    ('0', '平手'), ('0.25', '平/半'), ('0.5', '半球'), ('0.75', '半/一'),
    ('1', '一球'), ('1.25', '一/球半'), ('1.5', '球半'),
    ('1.75', '球半/两'), ('2', '两球'), ('2.5', '两球半'),
    ('2.75', '两球半/三'), ('3.25', '三/三球半'),
    ('3.5', '三球半'), ('4.5', '四球半'),
]

OVERUNDER_ITEMS = [
    ('1.75', '1.5/2'), ('2', '2'), ('2.25', '2/2.5'),
    ('2.5', '2.5'), ('2.75', '2.5/3'), ('3', '3'),
    ('3.25', '3/3.5'), ('3.5', '3.5'), ('3.75', '3.5/4'),
    ('4', '4'), ('4.25', '4/4.5'), ('4.5', '4.5'),
    ('4.75', '4.5/5'), ('5.25', '5/5.5'), ('6', '6'),
]

# 全局样式表
GLOBAL_STYLESHEET = """
    QMainWindow {
        background-color: #0f172a;
    }
    QWidget {
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 17px;  /* v2优化: 15px -> 17px 适配高分屏 */
        color: #e2e8f0;
    }
    QGroupBox {
        font-weight: bold;
        font-size: 17px;  /* v2优化: 15px -> 17px */
        border: 2px solid #334155;
        border-radius: 12px;
        margin-top: 16px;
        padding-top: 12px;
        padding: 14px;
        background-color: #1e293b;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 10px;
        color: #60a5fa;
        font-weight: bold;
        font-size: 17px;  /* v2优化: 15px -> 17px */
    }
    QPushButton {
        background-color: #2563eb;
        color: white;
        border: none;
        padding: 14px 28px;  /* v2优化: 增加内边距 */
        border-radius: 8px;
        font-weight: bold;
        font-size: 16px;  /* v2优化: 14px -> 16px */
        min-height: 32px;  /* v2优化: 28px -> 32px */
    }
    QPushButton:hover {
        background-color: #1d4ed8;
    }
    QPushButton:pressed {
        background-color: #1e40af;
    }
    QPushButton:disabled {
        background-color: #334155;
        color: #64748b;
    }
    QPushButton#startBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #059669, stop:1 #10b981);
        font-size: 20px;  /* v2优化: 18px -> 20px */
        padding: 18px 45px;  /* v2优化: 增加内边距 */
        border-radius: 10px;
        font-weight: bold;
    }
    QPushButton#startBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2=0, stop:0 #047857, stop:1 #059669); }
    QPushButton#stopBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #dc2626, stop:1 #ef4444);
        font-size: 16px;
        padding: 14px 30px;
    }
    QPushButton#stopBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2=0, stop:0 #b91c1c, stop:1 #dc2626); }
    QPushButton#filterBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #7c3aed, stop:1 #8b5cf6);
        font-size: 16px;
        padding: 14px 28px;
    }
    QPushButton#filterBtn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2=0, stop:0 #6d28d9, stop:1 #7c3aed); }
    QPushButton#backBtn {
        background-color: #475569;
    }
    QPushButton#backBtn:hover { background-color: #64748b; }
    QPushButton#testEmailBtn {
        background-color: #0891b2;
        font-size: 13px;
        padding: 8px 18px;
    }
    QPushButton#testEmailBtn:hover { background-color: #0e7490; }
    QPushButton#saveConfigBtn {
        background-color: #059669;
        font-size: 13px;
        padding: 8px 18px;
    }
    QPushButton#saveConfigBtn:hover { background-color: #047857; }

    QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox {
        padding: 10px 14px;  /* v2优化: 增加内边距 */
        border: 2px solid #475569;
        border-radius: 6px;
        background-color: #0f172a;
        color: #e2e8f0;
        font-size: 16px;  /* v2优化: 14px -> 16px */
    }
    QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {
        border: 2px solid #3b82f6;
    }
    QComboBox::drop-down {
        border: none;
        width: 28px;
    }
    QComboBox::down-arrow {
        image: none;
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 8px solid #94a3b8;
        margin-right: 10px;
    }
    QComboBox QAbstractItemView {
        background-color: #1e293b;
        color: #e2e8f0;
        selection-background-color: #2563eb;
        border: 2px solid #334155;
        font-size: 14px;
    }

    QTableWidget {
        background-color: #1e293b;
        border: 2px solid #334155;
        border-radius: 10px;
        gridline-color: #1e293b;
        font-size: 16px;  /* v2优化: 14px -> 16px */
        selection-background-color: #1e3a5f;
        alternate-background-color: #1e293b;
    }
    QTableWidget::item {
        padding: 10px;  /* v2优化: 8px -> 10px */
        color: #e2e8f0;
    }
    QTableWidget::item:selected {
        background-color: #1d4ed8;
        color: white;
    }
    QHeaderView::section {
        background-color: #0f172a;
        color: #93c5fd;
        padding: 12px 10px;  /* v2优化: 增加内边距 */
        border: none;
        border-bottom: 3px solid #3b82f6;
        font-weight: bold;
        font-size: 16px;  /* v2优化: 14px -> 16px */
    }
    QScrollBar:vertical {
        background: #1e293b;
        width: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background: #475569;
        border-radius: 6px;
        min-height: 35px;
    }
    QScrollBar::handle:vertical:hover { background: #64748b; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

    QTextEdit {
        background-color: #0f172a;
        color: #94a3b8;
        border: 2px solid #334155;
        border-radius: 8px;
        font-family: Consolas, "Courier New", monospace;
        font-size: 13px;
        padding: 10px;
    }
    QListWidget {
        background-color: #0f172a;
        border: 2px solid #334155;
        border-radius: 8px;
        font-size: 14px;
        outline: none;
    }
    QListWidget::item {
        padding: 7px 10px;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #2563eb;
        color: white;
    }
    QListWidget::item:hover {
        background-color: #1e3a5f;
    }
    QCheckBox {
        spacing: 8px;
        color: #e2e8f0;
        font-size: 14px;
    }
    QCheckBox::indicator {
        width: 22px;
        height: 22px;
        border-radius: 5px;
        border: 2px solid #475569;
        background-color: #0f172a;
    }
    QCheckBox::indicator:checked {
        background-color: #2563eb;
        border-color: #2563eb;
        image: url(none);
    }
    QCheckBox::indicator:hover {
        border-color: #3b82f6;
    }
    QSplitter::handle {
        background-color: #334155;
        width: 3px;
    }
    QSplitter::handle:hover {
        background-color: #3b82f6;
    }
    QLabel#titleLabel {
        color: #f8fafc;
        font-weight: bold;
    }
    QLabel#subtitleLabel {
        color: #64748b;
    }
    QLabel#statusOk { color: #10b981; font-weight: bold; }
    QLabel#statusError { color: #ef4444; font-weight: bold; }
    QLabel#statusWarn { color: #f59e0b; font-weight: bold; }
"""


# ============================================================
# 比赛监控配置控件（卡片式，显示在表格下方独立区域）
# 增强版：支持启用复选框、比较符下拉框、盘口变化监控
# ============================================================

# ============================================================
# 告警历史查看对话框
# ============================================================
class AlertHistoryDialog(QDialog):
    """v5新增: 告警历史查看对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.alert_logs_dir = 'alert_logs'
        self.all_alerts = []
        self.filtered_alerts = []
        self._init_ui()
        self._load_all_alerts()
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("📋 历史告警记录")
        self.setMinimumSize(1000, 700)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # === 顶部筛选区 ===
        filter_group = QGroupBox("🔍 筛选条件")
        filter_layout = QHBoxLayout(filter_group)
        
        # 日期筛选
        filter_layout.addWidget(QLabel("起始日期:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(datetime.now().date())
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.start_date_edit)
        
        filter_layout.addWidget(QLabel("结束日期:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(datetime.now().date())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.end_date_edit)
        
        # 搜索框
        filter_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入比赛ID、球队名或告警内容...")
        self.search_input.setMinimumWidth(250)
        filter_layout.addWidget(self.search_input)
        
        # 按钮
        search_btn = QPushButton("🔍 搜索")
        search_btn.clicked.connect(self._apply_filter)
        filter_layout.addWidget(search_btn)
        
        reset_btn = QPushButton("🔄 重置")
        reset_btn.clicked.connect(self._reset_filter)
        filter_layout.addWidget(reset_btn)
        
        filter_layout.addStretch()
        layout.addWidget(filter_group)
        
        # === 中部表格区 ===
        self.alert_table = QTableWidget()
        self.alert_table.setColumnCount(5)
        self.alert_table.setHorizontalHeaderLabels([
            '时间', '联赛', '对阵', '告警类型', '详情'
        ])
        
        # 设置列宽
        header = self.alert_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 时间
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 联赛
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # 对阵
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 类型
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # 详情
        
        self.alert_table.setAlternatingRowColors(True)
        self.alert_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.alert_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.alert_table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.alert_table)
        
        # === 底部统计区 ===
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("共 0 条记录")
        self.stats_label.setStyleSheet("font-size: 12px; color: #64748b;")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        
        close_btn = QPushButton("❌ 关闭")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        stats_layout.addWidget(close_btn)
        
        layout.addLayout(stats_layout)
    
    def _load_all_alerts(self):
        """加载所有告警记录"""
        self.all_alerts = []
        
        if not os.path.exists(self.alert_logs_dir):
            return
        
        # 遍历所有JSON文件
        for filename in os.listdir(self.alert_logs_dir):
            if filename.startswith('alerts_') and filename.endswith('.json'):
                filepath = os.path.join(self.alert_logs_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        alerts = json.load(f)
                        self.all_alerts.extend(alerts)
                except Exception as e:
                    print(f"[告警历史] 读取{filename}失败: {e}")
        
        # 按时间排序（最新的在前）
        self.all_alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # 应用默认筛选（今天）
        self._apply_filter()
    
    def _apply_filter(self):
        """应用筛选条件"""
        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        search_text = self.search_input.text().strip().lower()
        
        self.filtered_alerts = []
        
        for alert in self.all_alerts:
            timestamp = alert.get('timestamp', '')
            # 提取日期部分 (YYYY-MM-DD HH:MM:SS -> YYYY-MM-DD)
            alert_date = timestamp[:10] if len(timestamp) >= 10 else ''
            
            # 日期筛选
            if alert_date < start_date or alert_date > end_date:
                continue
            
            # 搜索筛选
            if search_text:
                match_id = alert.get('match_id', '').lower()
                message = alert.get('message', '').lower()
                alert_type_name = alert.get('alert_type_name', '').lower()
                
                if (search_text not in match_id and 
                    search_text not in message and 
                    search_text not in alert_type_name):
                    continue
            
            self.filtered_alerts.append(alert)
        
        self._populate_table()
    
    def _reset_filter(self):
        """重置筛选条件"""
        today = datetime.now().date()
        self.start_date_edit.setDate(today)
        self.end_date_edit.setDate(today)
        self.search_input.clear()
        self._apply_filter()
    
    def _populate_table(self):
        """填充表格数据"""
        self.alert_table.setRowCount(0)
        
        for alert in self.filtered_alerts:
            row = self.alert_table.rowCount()
            self.alert_table.insertRow(row)
            
            # 时间
            timestamp = alert.get('timestamp', '')
            time_item = QTableWidgetItem(timestamp)
            time_item.setTextAlignment(Qt.AlignCenter)
            self.alert_table.setItem(row, 0, time_item)
            
            # 联赛（从消息中提取）
            message = alert.get('message', '')
            league = self._extract_league(message)
            league_item = QTableWidgetItem(league)
            league_item.setTextAlignment(Qt.AlignCenter)
            self.alert_table.setItem(row, 1, league_item)
            
            # 对阵（从消息中提取）
            teams = self._extract_teams(message)
            teams_item = QTableWidgetItem(teams)
            teams_item.setTextAlignment(Qt.AlignCenter)
            self.alert_table.setItem(row, 2, teams_item)
            
            # 告警类型
            alert_type_name = alert.get('alert_type_name', alert.get('alert_type', ''))
            type_item = QTableWidgetItem(alert_type_name)
            type_item.setTextAlignment(Qt.AlignCenter)
            self.alert_table.setItem(row, 3, type_item)
            
            # 详情
            detail_item = QTableWidgetItem(message)
            detail_item.setToolTip(message)  # 鼠标悬停显示完整内容
            self.alert_table.setItem(row, 4, detail_item)
        
        # 更新统计
        self.stats_label.setText(f"共 {len(self.filtered_alerts)} 条记录 / 总计 {len(self.all_alerts)} 条")
    
    def _extract_league(self, message):
        """从消息中提取联赛名称"""
        # 格式: 【联赛名】...
        if '【' in message and '】' in message:
            start = message.index('【') + 1
            end = message.index('】')
            return message[start:end]
        return '-'
    
    def _extract_teams(self, message):
        """从消息中提取对阵信息"""
        # 查找 "vs" 或 "VS"
        if ' vs ' in message:
            # 提取 vs 前后的球队名
            parts = message.split(' vs ')
            if len(parts) >= 2:
                # 第一部分可能包含联赛前缀，需要清理
                home_part = parts[0]
                if '】' in home_part:
                    home_part = home_part.split('】')[-1].strip()
                away_part = parts[1].split(':')[0].strip()
                return f"{home_part} vs {away_part}"
        return '-'


# ============================================================
class MatchMonitorWidget(QWidget):
    """单场比赛的监控参数配置控件 - 增强版卡片式设计"""

    # 比较符选项
    OPERATORS = ['<', '>', '=']
    OPERATOR_LABELS = {'<': '≤(低于)', '>': '≥(高于)', '=': '(等于)'}

    def __init__(self, match_data, parent=None):
        super().__init__(parent)
        self.match_id = match_data.get('match_id', '')
        self.match_data = match_data
        self._build_ui()

    @staticmethod
    def _make_operator_combo():
        """创建比较符下拉框"""
        cb = QComboBox()
        for op in MatchMonitorWidget.OPERATORS:
            cb.addItem(MatchMonitorWidget.OPERATOR_LABELS.get(op, op), op)
        cb.setCurrentText(MatchMonitorWidget.OPERATOR_LABELS['<'])
        cb.setMaximumWidth(70)
        cb.setStyleSheet("""
            QComboBox {
                padding: 3px 6px; border: 1px solid #475569; border-radius: 4px;
                background-color: #0f172a; color: #e2e8f0; font-size: 11px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow { image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #94a3b8; margin-right: 5px; }
            QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0; selection-background-color: #2563eb; }
        """)
        return cb

    def _threshold_row(self, label_text, row_idx, grid, default_val=0.85, step=0.05, decimals=2,
                       prefix=""):
        """
        创建一个完整的阈值行：[启用CB] [标签] [数值] [比较符]
        返回 (enable_cb, value_spin, operator_combo)
        """
        enable_cb = QCheckBox("")
        enable_cb.setChecked(False)
        enable_cb.setToolTip("勾选启用此规则")
        grid.addWidget(enable_cb, row_idx, 0)

        grid.addWidget(QLabel(label_text), row_idx, 1)

        spin = QDoubleSpinBox()
        spin.setRange(0.01, 20.0)
        spin.setValue(default_val)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setMinimumWidth(60)
        if prefix:
            spin.setPrefix(prefix)
        grid.addWidget(spin, row_idx, 2)

        op_combo = self._make_operator_combo()
        grid.addWidget(op_combo, row_idx, 3)

        return enable_cb, spin, op_combo

    def _build_ui(self):
        self.setStyleSheet("""
            MatchMonitorWidget {
                background-color: #1e293b;
                border: 2px solid #334155;
                border-radius: 10px;
                margin: 3px 0;
            }
            QLabel { color: #94a3b8; font-size: 13px; }
            QSpinBox, QDoubleSpinBox {
                padding: 5px 8px;
                border: 2px solid #475569;
                border-radius: 6px;
                background-color: #0f172a;
                color: #e2e8f0;
                font-size: 13px;
            }
            QCheckBox { color: #cbd5e1; font-size: 13px; spacing: 6px; }
            QCheckBox::indicator { width: 20px; height: 20px; border-radius: 5px; border: 2px solid #475569; background-color: #0f172a; }
            QCheckBox::indicator:checked { background-color: #2563eb; border-color: #2563eb; }
            QGroupBox {
                font-weight: bold; font-size: 13px; color: #60a5fa;
                border: 2px solid #334155; border-radius: 8px; margin-top: 10px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # === 标题栏 ===
        title_bar = QHBoxLayout()
        title_bar.setSpacing(6)
        
        team_label = QLabel(
            f"<span style='color:#60a5fa;font-weight:bold'>{self.match_data.get('home_team', '')}</span>"
            f" <span style='color:#64748b'>vs</span> "
            f"<span style='color:#f472b6;font-weight:bold'>{self.match_data.get('away_team', '')}</span>"
        )
        team_label.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        title_bar.addWidget(team_label)

        status_tag = QLabel(f"[{self.match_data.get('status', '-')}]")
        status_tag.setStyleSheet("""
            background-color: #059669; color: white; font-size: 11px;
            padding: 2px 8px; border-radius: 10px; font-weight: bold;
        """)
        title_bar.addWidget(status_tag)
        title_bar.addStretch()

        remove_btn = QPushButton("\u2715 \u79fb\u9664")  # ✕ 移除
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #ef4444; border: 2px solid #ef4444;
                padding: 3px 14px; border-radius: 6px; font-size: 12px;
            }
            QPushButton:hover { background-color: #ef4444; color: white; }
        """)
        remove_btn.setObjectName(f"remove_{self.match_id}")
        title_bar.addWidget(remove_btn)
        main_layout.addLayout(title_bar)

        # === 分区1: 进球提醒（v2优化版）===
        group1 = QGroupBox("\u26bd \u8fdb\u7403\u63d0\u9192")  # ⚽ 进球提醒
        g1_layout = QVBoxLayout(group1)
        g1_layout.setSpacing(8)

        # --- 第一行: 全场目标进球 ---
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.target_goals_enabled_cb = QCheckBox("")
        self.target_goals_enabled_cb.setToolTip("\u542f\u7528\u5168\u573a\u76ee\u6807\u8fdb\u7403\u89c4\u5219")
        row1.addWidget(self.target_goals_enabled_cb)
        row1.addWidget(QLabel("\u5168\u573a\u76ee\u6807:"))
        self.target_goals_spin = QSpinBox()
        self.target_goals_spin.setRange(0, 15)
        self.target_goals_spin.setValue(0)
        self.target_goals_spin.setSuffix(" \u7403")
        self.target_goals_spin.setMinimumWidth(60)
        row1.addWidget(self.target_goals_spin)
        row1.addStretch()
        g1_layout.addLayout(row1)

        # --- 第二行: 上半场进球（带阈值）---
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.first_half_goal_enabled_cb = QCheckBox("\u4e0a\u534a\u573a\u8fdb\u7403")
        self.first_half_goal_enabled_cb.setChecked(False)
        self.first_half_goal_enabled_cb.setToolTip("\u8fbe\u5230\u8bbe\u5b9a\u8fdb\u7403\u6570\u65f6\u63d0\u9192")
        row2.addWidget(self.first_half_goal_enabled_cb)

        row2.addWidget(QLabel("\u9608\u503c:"))
        self.first_half_goal_threshold_spin = QSpinBox()
        self.first_half_goal_threshold_spin.setRange(1, 10)
        self.first_half_goal_threshold_spin.setValue(1)
        self.first_half_goal_threshold_spin.setSuffix(" \u7403")
        self.first_half_goal_threshold_spin.setMinimumWidth(60)
        self.first_half_goal_threshold_spin.setEnabled(False)
        row2.addWidget(self.first_half_goal_threshold_spin)
        row2.addStretch()
        g1_layout.addLayout(row2)

        # 连接信号
        self.first_half_goal_enabled_cb.toggled.connect(self.first_half_goal_threshold_spin.setEnabled)

        # --- 第三行: 下半场进球（带阈值）---
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.second_half_goal_enabled_cb = QCheckBox("\u4e0b\u534a\u573a\u8fdb\u7403")
        self.second_half_goal_enabled_cb.setChecked(False)
        self.second_half_goal_enabled_cb.setToolTip("\u8fbe\u5230\u8bbe\u5b9a\u8fdb\u7403\u6570\u65f6\u63d0\u9192")
        row3.addWidget(self.second_half_goal_enabled_cb)

        row3.addWidget(QLabel("\u9608\u503c:"))
        self.second_half_goal_threshold_spin = QSpinBox()
        self.second_half_goal_threshold_spin.setRange(1, 10)
        self.second_half_goal_threshold_spin.setValue(1)
        self.second_half_goal_threshold_spin.setSuffix(" \u7403")
        self.second_half_goal_threshold_spin.setMinimumWidth(60)
        self.second_half_goal_threshold_spin.setEnabled(False)
        row3.addWidget(self.second_half_goal_threshold_spin)
        row3.addStretch()
        g1_layout.addLayout(row3)

        # 连接信号
        self.second_half_goal_enabled_cb.toggled.connect(self.second_half_goal_threshold_spin.setEnabled)

        main_layout.addWidget(group1)

        # === v2新增分区: 时间节点提醒 ===
        group_time = QGroupBox("\u23f1\ufe0f \u65f6\u95f4\u8282\u70b9\u63d0\u9192")  # ⏱️ 时间节点提醒
        time_layout = QVBoxLayout(group_time)
        time_layout.setSpacing(8)

        # --- 第一行: 上半场无进球提醒 ---
        row_t2 = QHBoxLayout()
        row_t2.setSpacing(8)
        self.first_half_no_goal_enabled_cb = QCheckBox("\u4e0a\u534a\u573a\u4ec5N\u7403")  # v2优化: 可配置阈值
        self.first_half_no_goal_enabled_cb.setChecked(False)
        self.first_half_no_goal_enabled_cb.setToolTip("\u4e0a\u534a\u573a\u8fdbN\u7403\u540e\uff0c\u5230\u8bbe\u5b9a\u65f6\u95f4\u4ecd\u672a\u8fdb\u7b2c(N+1)\u7403\u5219\u63d0\u9192")  # v2优化: 更新说明
        row_t2.addWidget(self.first_half_no_goal_enabled_cb)

        row_t2.addWidget(QLabel("\u8fdb\u7403\u6570:"))
        self.first_half_no_goal_threshold_spin = QSpinBox()
        self.first_half_no_goal_threshold_spin.setRange(0, 10)
        self.first_half_no_goal_threshold_spin.setValue(1)
        self.first_half_no_goal_threshold_spin.setSuffix(" \u7403")
        self.first_half_no_goal_threshold_spin.setMinimumWidth(70)
        self.first_half_no_goal_threshold_spin.setEnabled(False)
        row_t2.addWidget(self.first_half_no_goal_threshold_spin)

        row_t2.addWidget(QLabel("\u68c0\u6d4b\u65f6\u95f4:"))
        self.first_half_no_goal_minute_spin = QSpinBox()
        self.first_half_no_goal_minute_spin.setRange(20, 45)
        self.first_half_no_goal_minute_spin.setValue(30)
        self.first_half_no_goal_minute_spin.setSuffix(" \u5206\u949f")
        self.first_half_no_goal_minute_spin.setMinimumWidth(70)
        self.first_half_no_goal_minute_spin.setEnabled(False)
        row_t2.addWidget(self.first_half_no_goal_minute_spin)
        row_t2.addStretch()
        time_layout.addLayout(row_t2)

        # v2优化: 复选框控制两个输入框
        def toggle_first_half_inputs(enabled):
            self.first_half_no_goal_threshold_spin.setEnabled(enabled)
            self.first_half_no_goal_minute_spin.setEnabled(enabled)
        self.first_half_no_goal_enabled_cb.toggled.connect(toggle_first_half_inputs)

        # --- 第二行: 下半场进N球后无第(N+1)球提醒 ---
        row_t3 = QHBoxLayout()
        row_t3.setSpacing(8)
        self.second_half_no_goal_enabled_cb = QCheckBox("\u4e0b\u534a\u573a\u4ec5N\u7403")  # v2优化: 可配置阈值
        self.second_half_no_goal_enabled_cb.setChecked(False)
        self.second_half_no_goal_enabled_cb.setToolTip("\u4e0b\u534a\u573a\u8fdbN\u7403\u540e\uff0c\u5230\u8bbe\u5b9a\u65f6\u95f4\u4ecd\u672a\u8fdb\u7b2c(N+1)\u7403\u5219\u63d0\u9192")  # v2优化: 更新说明
        row_t3.addWidget(self.second_half_no_goal_enabled_cb)

        row_t3.addWidget(QLabel("\u8fdb\u7403\u6570:"))
        self.second_half_no_goal_threshold_spin = QSpinBox()
        self.second_half_no_goal_threshold_spin.setRange(0, 10)
        self.second_half_no_goal_threshold_spin.setValue(1)
        self.second_half_no_goal_threshold_spin.setSuffix(" \u7403")
        self.second_half_no_goal_threshold_spin.setMinimumWidth(70)
        self.second_half_no_goal_threshold_spin.setEnabled(False)
        row_t3.addWidget(self.second_half_no_goal_threshold_spin)

        row_t3.addWidget(QLabel("\u68c0\u6d4b\u65f6\u95f4:"))
        self.second_half_no_goal_minute_spin = QSpinBox()
        self.second_half_no_goal_minute_spin.setRange(50, 85)
        self.second_half_no_goal_minute_spin.setValue(70)
        self.second_half_no_goal_minute_spin.setSuffix(" \u5206\u949f")
        self.second_half_no_goal_minute_spin.setMinimumWidth(70)
        self.second_half_no_goal_minute_spin.setEnabled(False)
        row_t3.addWidget(self.second_half_no_goal_minute_spin)
        row_t3.addStretch()
        time_layout.addLayout(row_t3)

        # v2优化: 复选框控制两个输入框
        def toggle_second_half_inputs(enabled):
            self.second_half_no_goal_threshold_spin.setEnabled(enabled)
            self.second_half_no_goal_minute_spin.setEnabled(enabled)
        self.second_half_no_goal_enabled_cb.toggled.connect(toggle_second_half_inputs)

        main_layout.addWidget(group_time)

        # === 分区2: 水位监控 ===
        group2 = QGroupBox("\U0001f4ca \u4e9a\u76d8/\u5927\u5c0f\u7403\u6c34\u4f4d")  # 📊 亚盘/大小球水位
        g2_grid = QGridLayout(group2)
        g2_grid.setSpacing(6)

        # 第0行：亚盘主队
        self.asian_home_en, self.asian_home_th, self.asian_home_op = \
            self._threshold_row("\u4e9a\u76d8\u4e3b\u96df\u6c34\u4f4d", 0, g2_grid, default_val=0.85)
        # 第1行：亚盘客队
        self.asian_away_en, self.asian_away_th, self.asian_away_op = \
            self._threshold_row("\u4e9a\u76d8\u5ba2\u96df\u6c34\u4f4d", 1, g2_grid, default_val=0.85)
        # 第2行：大球水位
        self.ou_over_en, self.ou_over_th, self.ou_over_op = \
            self._threshold_row("\u5927\u7403\u6c34\u4f4d", 2, g2_grid, default_val=0.85)
        # 第3行：小球水位
        self.ou_under_en, self.ou_under_th, self.ou_under_op = \
            self._threshold_row("\u5c0f\u7403\u6c34\u4f4d", 3, g2_grid, default_val=0.85)

        g2_grid.setColumnStretch(4, 1)
        main_layout.addWidget(group2)

        # === 分区3: 盘口变化监控 ===
        group3 = QGroupBox("\U0001f4c9 \u76d8\u53e3\u53d8\u5316\u76d1\u63a7")  # 📉 盘口变化监控
        g3_grid = QGridLayout(group3)
        g3_grid.setSpacing(6)

        # 亚盘盘口变化
        self.hc_asian_en, self.hc_asian_th, self.hc_asian_op = \
            self._threshold_row(
                "\u4e9a\u76d8\u76d8\u53e3\u53d8\u5316(\u5982\u5347\u76d8/\u964d\u76d8)",
                0, g3_grid, default_val=0.25, step=0.25, decimals=2
            )

        # 大小球盘口变化
        self.hc_ou_en, self.hc_ou_th, self.hc_ou_op = \
            self._threshold_row(
                "\u5927\u5c0f\u7403\u76d8\u53e3\u53d8\u5316(\u59872.5\u21923)",
                1, g3_grid, default_val=0.25, step=0.25, decimals=2
            )

        g3_grid.setColumnStretch(4, 1)
        main_layout.addWidget(group3)

    def get_config(self):
        """获取当前控件的完整配置值（增强版）"""
        # 辅助方法：从比较符下拉框取值
        def _op(cb):
            idx = cb.currentIndex()
            if idx >= 0:
                return cb.itemData(idx)
            return '<'

        cfg = {
            'match_id': self.match_id,
            'home_team': self.match_data.get('home_team', ''),
            'away_team': self.match_data.get('away_team', ''),
            'league': self.match_data.get('league', ''),  # v5修复: 添加联赛信息
            'status': self.match_data.get('status', ''),  # v5新增: 比赛状态
            'match_time': self.match_data.get('match_time', ''),  # v5新增: 比赛时间

            # --- v2进球规则（新版）---
            'target_goals_enabled': self.target_goals_enabled_cb.isChecked(),
            'target_goals': int(self.target_goals_spin.value()),
            
            # 上半场进球（带阈值）
            'first_half_goal_enabled': self.first_half_goal_enabled_cb.isChecked(),
            'first_half_goal_threshold': int(self.first_half_goal_threshold_spin.value()),
            
            # 下半场进球（带阈值）
            'second_half_goal_enabled': self.second_half_goal_enabled_cb.isChecked(),
            'second_half_goal_threshold': int(self.second_half_goal_threshold_spin.value()),
            
            # --- v2时间节点提醒 ---
            'first_half_no_goal_enabled': self.first_half_no_goal_enabled_cb.isChecked(),
            'first_half_no_goal_threshold': int(self.first_half_no_goal_threshold_spin.value()),  # v2新增: 进球数阈值
            'first_half_no_goal_minute': int(self.first_half_no_goal_minute_spin.value()),
            
            'second_half_no_goal_enabled': self.second_half_no_goal_enabled_cb.isChecked(),
            'second_half_no_goal_threshold': int(self.second_half_no_goal_threshold_spin.value()),  # v2新增: 进球数阈值
            'second_half_no_goal_minute': int(self.second_half_no_goal_minute_spin.value()),

            # --- 水位监控（带启用开关和比较符）---
            'asian_home_enabled': self.asian_home_en.isChecked(),
            'asian_home_threshold': round(self.asian_home_th.value(), 2),
            'asian_home_operator': _op(self.asian_home_op),

            'asian_away_enabled': self.asian_away_en.isChecked(),
            'asian_away_threshold': round(self.asian_away_th.value(), 2),
            'asian_away_operator': _op(self.asian_away_op),

            'ou_over_enabled': self.ou_over_en.isChecked(),
            'ou_over_threshold': round(self.ou_over_th.value(), 2),
            'ou_over_operator': _op(self.ou_over_op),

            'ou_under_enabled': self.ou_under_en.isChecked(),
            'ou_under_threshold': round(self.ou_under_th.value(), 2),
            'ou_under_operator': _op(self.ou_under_op),

            # --- 盘口变化监控 ---
            'handicap_change_asian_enabled': self.hc_asian_en.isChecked(),
            'handicap_change_asian_threshold': round(self.hc_asian_th.value(), 2),
            'handicap_change_asian_operator': _op(self.hc_asian_op),

            'handicap_change_ou_enabled': self.hc_ou_en.isChecked(),
            'handicap_change_ou_threshold': round(self.hc_ou_th.value(), 2),
            'handicap_change_ou_operator': _op(self.hc_ou_op),
        }
        return cfg


# ============================================================
# 筛选工作线程 - 在后台执行耗时筛选，避免阻塞UI
# ============================================================
class FilterWorkerThread(QThread):
    """后台执行盘口筛选的工作线程"""

    # 自定义信号：完成时发送 (成功标志, 比赛列表, 初盘缓存, 错误信息)
    finished = pyqtSignal(bool, list, dict, str)
    # 进度信号: (阶段描述文字)
    progress = pyqtSignal(str)
    # 日志信号: (日志文本)
    log_signal = pyqtSignal(str)

    def __init__(self, filter_ctrl, fetcher, asian_enabled, asian_values, ou_enabled, ou_values,
                 half_ou_enabled=False, half_ou_min=0.75, half_ou_max=1.5):
        super().__init__()
        self.filter_ctrl = filter_ctrl
        self.fetcher = fetcher
        self.asian_enabled = asian_enabled
        self.asian_values = asian_values
        self.ou_enabled = ou_enabled
        self.ou_values = ou_values
        # v2新增: 半场大小球大球初盘范围筛选
        self.half_ou_enabled = half_ou_enabled
        self.half_ou_min = half_ou_min
        self.half_ou_max = half_ou_max
        self._stopped = False

    def run(self):
        """线程入口 - 执行完整筛选流程"""
        try:
            # 阶段1：打开浏览器并访问页面
            self.progress.emit("正在启动浏览器...")
            self.log_signal.emit("正在启动浏览器并访问7M页面...")
            self.filter_ctrl.open_live_page()

            if self._stopped:
                return

            # 阶段2：执行组合筛选
            self.progress.emit("正在执行盘口筛选...")
            self.log_signal.emit("开始执行筛选...")
            filtered_matches = self.filter_ctrl.filter_combined(
                self.asian_enabled, self.asian_values,
                self.ou_enabled, self.ou_values,
                self.half_ou_enabled, self.half_ou_min, self.half_ou_max  # v2新增
            )

            if self._stopped:
                return

            if not filtered_matches:
                self.finished.emit(True, [], {}, "")
                return

            # 阶段3：批量获取初盘数据
            self.progress.emit(f"正在获取 {len(filtered_matches)} 场比赛初盘数据...")
            self.log_signal.emit(f"获取到 {len(filtered_matches)} 场比赛，正在请求初盘数据...")

            match_ids = [m['match_id'] for m in filtered_matches]
            initial_results = self.fetcher.batch_fetch_initial(match_ids)

            initial_odds_cache = {}
            success_count = 0
            for mid, result in initial_results.items():
                if not result.get('error'):
                    initial_odds_cache[mid] = result
                    success_count += 1

            self.log_signal.emit(f"初盘数据获取完成: 成功 {success_count}/{len(match_ids)} 场")

            # 阶段4：批量获取半场初盘数据
            self.progress.emit(f"正在获取 {len(filtered_matches)} 场比赛半场初盘数据...")
            self.log_signal.emit("正在请求半场初盘数据...")
            
            half_time_success = 0
            for mid in match_ids:
                if self._stopped:
                    return
                try:
                    half_result = self.fetcher.fetch_half_time_initial(mid)
                    if mid in initial_odds_cache:
                        # 将半场数据合并到初盘缓存中
                        initial_odds_cache[mid]['asian_half_initial'] = half_result.get('asian_half_initial')
                        initial_odds_cache[mid]['ou_half_initial'] = half_result.get('ou_half_initial')
                        if not half_result.get('error'):
                            half_time_success += 1
                except Exception as e:
                    self.log_signal.emit(f"获取比赛{mid}半场数据失败: {e}")
            
            self.log_signal.emit(f"半场初盘数据获取完成: 成功 {half_time_success}/{len(match_ids)} 场")

            # v2新增: 阶段5 - 根据半场大球初盘范围过滤
            if self.half_ou_enabled:
                self.progress.emit("正在按半场大球初盘范围过滤...")
                self.log_signal.emit(f"应用半场大球初盘范围筛选: [{self.half_ou_min}, {self.half_ou_max}]")
                
                filtered_matches_after_half_ou = []
                for match in filtered_matches:
                    mid = match.get('match_id', '')
                    if mid in initial_odds_cache:
                        ou_half_initial = initial_odds_cache[mid].get('ou_half_initial')
                        if ou_half_initial:
                            # v2优化: 尝试从handicap字段获取，如果不存在则使用goal_line
                            handicap_raw = ou_half_initial.get('handicap') or ou_half_initial.get('goal_line', '')
                            
                            if handicap_raw:
                                try:
                                    # 将带/的格式转换为数字
                                    from odds_fetcher import OddsFetcher
                                    handicap_value = OddsFetcher._convert_handicap_to_number(str(handicap_raw))
                                    
                                    if handicap_value is not None:
                                        # 检查是否在范围内
                                        if self.half_ou_min <= handicap_value <= self.half_ou_max:
                                            filtered_matches_after_half_ou.append(match)
                                            self.log_signal.emit(
                                                f"保留比赛{mid}: 半场大球初盘{handicap_raw}(={handicap_value})在范围"
                                                f"[{self.half_ou_min}, {self.half_ou_max}]内"
                                            )
                                        else:
                                            self.log_signal.emit(
                                                f"排除比赛{mid}: 半场大球初盘{handicap_raw}(={handicap_value})不在范围"
                                                f"[{self.half_ou_min}, {self.half_ou_max}]内"
                                            )
                                    else:
                                        self.log_signal.emit(
                                            f"排除比赛{mid}: 无法解析半场大球初盘'{handicap_raw}'"
                                        )
                                except Exception as e:
                                    self.log_signal.emit(f"解析比赛{mid}半场大球初盘失败: {e}")
                            else:
                                self.log_signal.emit(f"排除比赛{mid}: 无半场大球初盘数据")
                        else:
                            self.log_signal.emit(f"排除比赛{mid}: 无半场大球初盘数据")
                    else:
                        self.log_signal.emit(f"排除比赛{mid}: 无初盘缓存")
                
                original_count = len(filtered_matches)
                filtered_matches = filtered_matches_after_half_ou
                self.log_signal.emit(
                    f"半场大球初盘范围筛选完成: {len(filtered_matches)}/{original_count} 场符合条件"
                )

            # 发送完成信号
            self.finished.emit(True, filtered_matches, initial_odds_cache, "")

        except Exception as e:
            error_msg = f"筛选过程出错: {e}"
            self.log_signal.emit(error_msg)
            self.finished.emit(False, [], {}, error_msg)

    def stop(self):
        """请求停止线程"""
        self._stopped = True


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """主窗口 - 整合所有模块的UI界面"""

    def __init__(self):
        super().__init__()
        # 核心组件实例
        self.filter_ctrl = FilterController()
        self.fetcher = OddsFetcher()
        self.monitor_engine = MonitorEngine()
        self.alert_svc = AlertService(log_dir='alert_logs')  # v2: 指定告警日志目录
        self.email_cfg_dialog = EmailConfigDialog(self)
        
        # v2新增: 方案管理器
        self.profile_manager = ProfileManager()

        # 数据存储
        self.filtered_matches = []      # 筛选后的比赛列表
        self.monitored_match_ids = set()  # 被勾选要监控的比赛ID集合
        self.match_widgets = {}         # {row_index: MatchMonitorWidget}
        self.initial_odds_cache = {}     # {match_id: initial_odds_data}

        # 初始化UI
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle("⚽ 盘口监控与邮件提醒系统")
        
        # v2优化: 适配高分辨率屏幕 (2736x1824)
        # 设置窗口大小为屏幕的90%，最小1600x900
        screen = QApplication.primaryScreen().geometry()
        window_width = int(screen.width() * 0.9)  # 屏幕宽度的90%
        window_height = int(screen.height() * 0.9)  # 屏幕高度的90%
        
        # 确保最小尺寸
        window_width = max(window_width, 1600)
        window_height = max(window_height, 900)
        
        self.setGeometry(50, 50, window_width, window_height)
        self.setMinimumSize(1400, 800)  # 设置最小窗口大小
        self.setStyleSheet(GLOBAL_STYLESHEET)
        
        # v2优化: 设置QMessageBox全局样式，确保弹窗文字为黑色
        self.setStyleSheet(self.styleSheet() + """
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #000000;
                font-size: 13px;
            }
            QMessageBox QPushButton {
                color: #000000;
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #e2e8f0;
            }
            QMessageBox QPushButton:pressed {
                background-color: #cbd5e1;
            }
        """)

        # 设置深色主题调色板
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor('#0f172a'))
        palette.setColor(QPalette.Base, QColor('#1e293b'))
        palette.setColor(QPalette.Text, QColor('#e2e8f0'))
        self.setPalette(palette)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ========== 顶部工具栏 ==========
        main_layout.addWidget(self._create_toolbar())

        # ========== 主体区域（水平分割）==========
        body_splitter = QSplitter(Qt.Horizontal)
        
        # v2优化: 适配高分辨率屏幕，增加面板宽度
        # 左侧：筛选面板（原280 -> 350）
        body_splitter.addWidget(self._create_filter_panel())
        
        # 中间：比赛数据区（弹性）
        body_splitter.addWidget(self._create_match_panel())
        
        # 右侧：设置面板（原300 -> 380）
        body_splitter.addWidget(self._create_settings_panel())
        
        # 设置各面板初始宽度比例
        body_splitter.setStretchFactor(0, 0)   # 左侧固定
        body_splitter.setStretchFactor(1, 4)   # 中间占主体（增加权重）
        body_splitter.setStretchFactor(2, 0)   # 右侧固定
                
        # v2优化: 根据窗口大小动态设置初始宽度
        initial_width = window_width
        left_width = min(350, int(initial_width * 0.12))   # 左侧12%
        right_width = min(380, int(initial_width * 0.13))  # 右侧13%
        center_width = initial_width - left_width - right_width - 40  # 中间剩余
                
        body_splitter.setSizes([left_width, center_width, right_width])

        main_layout.addWidget(body_splitter, stretch=1)

        # ========== 底部状态栏 ==========
        main_layout.addWidget(self._create_status_bar())

    # ==================== 工具栏 ====================
    def _create_toolbar(self):
        """创建顶部工具栏"""
        toolbar = QWidget()
        toolbar.setObjectName("toolbarWidget")
        toolbar.setStyleSheet("""
            #toolbarWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e293b, stop:1 #0f172a);
                border-radius: 8px;
                padding: 8px 16px;
                border-bottom: 2px solid #3b82f6;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 10, 16, 10)

        # 标题
        title_label = QLabel("⚽ 盘口监控与邮件提醒")
        title_label.setObjectName("titleLabel")
        title_label.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))  # v2优化: 22 -> 24
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addSpacing(30)

        # 状态指示
        self.toolbar_status = QLabel("● 就绪")
        self.toolbar_status.setObjectName("statusOk")
        self.toolbar_status.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))  # v2优化: 13 -> 15
        toolbar_layout.addWidget(self.toolbar_status)

        toolbar_layout.addSpacing(5)
        self.monitor_count_label = QLabel("监控中: 0 场")
        self.monitor_count_label.setStyleSheet("color: #94a3b8; font-size: 15px;")  # v2优化: 13 -> 15
        toolbar_layout.addWidget(self.monitor_count_label)

        toolbar_layout.addSpacing(5)
        self.alert_count_label = QLabel("告警: 0 次")
        self.alert_count_label.setStyleSheet("color: #f59e0b; font-size: 15px;")  # v2优化: 13 -> 15
        toolbar_layout.addWidget(self.alert_count_label)

        toolbar_layout.addStretch()

        # v2新增: 方案管理控件
        scheme_label = QLabel("📋 方案:")
        scheme_label.setStyleSheet("color: #94a3b8; font-size: 15px;")  # v2优化: 13 -> 15
        toolbar_layout.addWidget(scheme_label)
        
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(150)
        self.profile_combo.setFont(QFont("Microsoft YaHei", 12))
        self.profile_combo.setStyleSheet("""
            QComboBox {
                color: #000000;
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #64748b;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                color: #000000;
                background-color: #ffffff;
                selection-background-color: #3b82f6;
                selection-color: #ffffff;
            }
        """)
        self.profile_combo.addItem("-- 选择方案 --")
        self._refresh_profile_list()
        toolbar_layout.addWidget(self.profile_combo)
        
        self.load_profile_btn = QPushButton("📥 加载")
        self.load_profile_btn.setObjectName("actionBtn")
        self.load_profile_btn.setFixedWidth(70)
        toolbar_layout.addWidget(self.load_profile_btn)
        
        self.save_profile_btn = QPushButton("💾 保存")
        self.save_profile_btn.setObjectName("actionBtn")
        self.save_profile_btn.setFixedWidth(70)
        toolbar_layout.addWidget(self.save_profile_btn)
        
        self.delete_profile_btn = QPushButton("🗑️ 删除")
        self.delete_profile_btn.setObjectName("actionBtn")
        self.delete_profile_btn.setFixedWidth(70)
        toolbar_layout.addWidget(self.delete_profile_btn)
        
        toolbar_layout.addSpacing(20)
        
        # v5新增: 查看历史告警按钮
        self.view_alerts_btn = QPushButton("📋 历史告警")
        self.view_alerts_btn.setObjectName("actionBtn")
        self.view_alerts_btn.setFixedWidth(90)
        self.view_alerts_btn.setToolTip("查看所有历史告警记录")
        toolbar_layout.addWidget(self.view_alerts_btn)

        # 控制按钮
        self.start_btn = QPushButton("▶ 开始监控")
        self.start_btn.setObjectName("startBtn")
        toolbar_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止监控")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)
        toolbar_layout.addWidget(self.stop_btn)

        return toolbar

    # ==================== 左侧筛选面板 ====================
    def _create_filter_panel(self):
        """创建左侧筛选设置面板"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # v2优化: 适配高分辨率屏幕，增加宽度
        scroll_area.setMaximumWidth(400)  # 原320 -> 400
        scroll_area.setMinimumWidth(320)  # 原270 -> 320
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # --- 亚盘筛选组 ---
        asian_group = QGroupBox("📊 亚盘初盘筛选")
        asian_layout = QVBoxLayout(asian_group)

        self.asian_enabled_cb = QCheckBox("启用亚盘筛选")
        self.asian_enabled_cb.setChecked(True)
        asian_layout.addWidget(self.asian_enabled_cb)

        self.asian_list = QListWidget()
        self.asian_list.setMaximumHeight(200)
        for value, name in ASIAN_HANDICAP_ITEMS:
            item = QListWidgetItem(f"{name} ({value})")
            item.setData(Qt.UserRole, value)
            item.setCheckState(Qt.Unchecked)
            self.asian_list.addItem(item)
        asian_layout.addWidget(self.asian_list)

        # 快捷选择按钮
        asian_btn_row = QHBoxLayout()
        asian_select_all_btn = QPushButton("全选")
        asian_select_all_btn.clicked.connect(lambda: self._select_all_items(self.asian_list, Qt.Checked))
        asian_deselect_all_btn = QPushButton("清空")
        asian_deselect_all_btn.clicked.connect(lambda: self._select_all_items(self.asian_list, Qt.Unchecked))
        common_asian_btn = QPushButton("常用盘口")
        common_asian_btn.clicked.connect(self._select_common_asian)
        asian_btn_row.addWidget(asian_select_all_btn)
        asian_btn_row.addWidget(asian_deselect_all_btn)
        asian_btn_row.addWidget(common_asian_btn)
        asian_layout.addLayout(asian_btn_row)

        layout.addWidget(asian_group)

        # --- 大小球筛选组 ---
        ou_group = QGroupBox("📈 大小球初盘筛选")
        ou_layout = QVBoxLayout(ou_group)

        self.ou_enabled_cb = QCheckBox("启用大小球筛选")
        self.ou_enabled_cb.setChecked(False)
        ou_layout.addWidget(self.ou_enabled_cb)

        self.ou_list = QListWidget()
        self.ou_list.setMaximumHeight(160)
        for value, name in OVERUNDER_ITEMS:
            item = QListWidgetItem(f"{name} ({value})")
            item.setData(Qt.UserRole, value)
            item.setCheckState(Qt.Unchecked)
            self.ou_list.addItem(item)
        ou_layout.addWidget(self.ou_list)

        ou_btn_row = QHBoxLayout()
        ou_select_all_btn = QPushButton("全选")
        ou_select_all_btn.clicked.connect(lambda: self._select_all_items(self.ou_list, Qt.Checked))
        ou_deselect_all_btn = QPushButton("清空")
        ou_deselect_all_btn.clicked.connect(lambda: self._select_all_items(self.ou_list, Qt.Unchecked))
        common_ou_btn = QPushButton("常用盘口")
        common_ou_btn.clicked.connect(self._select_common_ou)
        ou_btn_row.addWidget(ou_select_all_btn)
        ou_btn_row.addWidget(ou_deselect_all_btn)
        ou_btn_row.addWidget(common_ou_btn)
        ou_layout.addLayout(ou_btn_row)

        layout.addWidget(ou_group)

        # --- 半场大小球大球初盘范围筛选组 ---
        half_ou_group = QGroupBox("📈 半场大小球大球初盘范围")
        half_ou_layout = QVBoxLayout(half_ou_group)

        self.half_ou_enabled_cb = QCheckBox("启用半场大球初盘筛选")
        self.half_ou_enabled_cb.setChecked(False)
        half_ou_layout.addWidget(self.half_ou_enabled_cb)

        # 范围设置行
        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        range_row.addWidget(QLabel("最小值:"))
        self.half_ou_min_spin = QDoubleSpinBox()
        self.half_ou_min_spin.setRange(0.0, 5.0)
        self.half_ou_min_spin.setValue(0.75)
        self.half_ou_min_spin.setDecimals(2)
        self.half_ou_min_spin.setSingleStep(0.25)
        self.half_ou_min_spin.setMinimumWidth(80)
        self.half_ou_min_spin.setEnabled(False)
        range_row.addWidget(self.half_ou_min_spin)

        range_row.addWidget(QLabel("最大值:"))
        self.half_ou_max_spin = QDoubleSpinBox()
        self.half_ou_max_spin.setRange(0.0, 5.0)
        self.half_ou_max_spin.setValue(1.5)
        self.half_ou_max_spin.setDecimals(2)
        self.half_ou_max_spin.setSingleStep(0.25)
        self.half_ou_max_spin.setMinimumWidth(80)
        self.half_ou_max_spin.setEnabled(False)
        range_row.addWidget(self.half_ou_max_spin)

        range_row.addStretch()
        half_ou_layout.addLayout(range_row)

        # 联动：复选框控制输入框启用状态
        self.half_ou_enabled_cb.toggled.connect(self.half_ou_min_spin.setEnabled)
        self.half_ou_enabled_cb.toggled.connect(self.half_ou_max_spin.setEnabled)

        # 提示文字
        hint_label = QLabel("💡 说明: 筛选半场大球初盘在 [最小值, 最大值] 范围内的比赛")
        hint_label.setStyleSheet("color: #94a3b8; font-size: 13px;")
        hint_label.setWordWrap(True)
        half_ou_layout.addWidget(hint_label)

        layout.addWidget(half_ou_group)

        # --- 执行筛选按钮 ---
        self.filter_btn = QPushButton("🔍 执行筛选")
        self.filter_btn.setObjectName("filterBtn")
        self.filter_btn.setMinimumHeight(50)
        self.filter_btn.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        layout.addWidget(self.filter_btn)

        layout.addStretch()

        scroll_area.setWidget(panel)
        return scroll_area

    @staticmethod
    def _select_all_items(list_widget, check_state):
        """全选/清空ListWidget的所有项"""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(check_state)

    def _select_common_asian(self):
        """选中常用的亚盘盘口（0.25 ~ 1.5）"""
        common_values = {'0.25', '0.5', '0.75', '1', '1.25', '1.5'}
        for i in range(self.asian_list.count()):
            item = self.asian_list.item(i)
            val = item.data(Qt.UserRole)
            if val in common_values or str(val) in common_values:
                item.setCheckState(Qt.Checked)

    def _select_common_ou(self):
        """选用的大小球盘口（2.25 ~ 3）"""
        common_values = {'2.25', '2.5', '2.75', '3'}
        for i in range(self.ou_list.count()):
            item = self.ou_list.item(i)
            val = item.data(Qt.UserRole)
            if val in common_values or str(val) in common_values:
                item.setCheckState(Qt.Checked)

    # ==================== 中央比赛面板 ====================
    def _create_match_panel(self):
        """创建中央比赛列表和监控设置区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # ========== 比赛列表标题行 ==========
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 4, 4, 4)

        header_title = QLabel("📋 比赛列表")
        header_title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        header_title.setStyleSheet("color: #60a5fa; font-weight: bold;")
        header_layout.addWidget(header_title)

        header_layout.addSpacing(20)

        # 统计信息（带图标样式）
        self.match_summary_label = QLabel("共 0 场 | 已勾选 0 场")
        self.match_summary_label.setStyleSheet("""
            color: #94a3b8; font-size: 14px;
            background-color: #1e293b; padding: 5px 16px;
            border-radius: 12px; border: 2px solid #334155;
        """)
        header_layout.addWidget(self.match_summary_label)

        header_layout.addStretch()

        layout.addWidget(header_widget)

        # ========== 比赛表格（精简为11列） ==========
        self.match_table = QTableWidget()
        self.match_table.setColumnCount(11)
        self.match_table.setHorizontalHeaderLabels([
            '✓',          # 复选框
            '时间',       # 日期+时间
            '对阵',       # 主队 vs 客队
            '比分',
            '状态',
            '亚盘初盘',
            '大小球初盘',
            '半场亚盘初盘',   # 新增
            '半场大小球初盘', # 新增
            '来源',
            '实时水位',   # 合并"最新水位+更新时间"
        ])

        # 表格属性
        self.match_table.setAlternatingRowColors(False)
        self.match_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.match_table.setSelectionMode(QTableWidget.SingleSelection)
        self.match_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.match_table.verticalHeader().setVisible(False)

        # 表头样式优化
        self.match_table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #1e3a5f;
                color: #93c5fd; padding: 10px 7px;
                border: none; border-bottom: 3px solid #3b82f6;
                font-weight: bold; font-size: 13px;
            }
        """)

        # 列宽优化（11列，更合理分配）
        col_widths = [30, 95, 200, 50, 45, 150, 140, 150, 140, 55, 160]
        for i, w in enumerate(col_widths):
            self.match_table.setColumnWidth(i, w)

        # 行高自适应
        self.match_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.match_table.verticalHeader().setDefaultSectionSize(40)

        layout.addWidget(self.match_table, stretch=3)

        # ========== 分隔线 + 监控配置区标题 ==========
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: #334155; max-height: 1px;")
        layout.addWidget(divider)

        config_header = QHBoxLayout()
        config_title = QLabel("⚙️ 已选比赛的监控配置")
        config_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        config_title.setStyleSheet("color: #60a5fa;")
        config_header.addWidget(config_title)
        config_header.addStretch()
        hint_label = QLabel("( 勾选上方表格中的比赛后，此处显示对应的监控参数 )")
        hint_label.setStyleSheet("color: #64748b; font-size: 12px;")
        config_header.addWidget(hint_label)
        layout.addLayout(config_header)

        # ========== 监控配置卡片容器（可滚动） ==========
        self.monitor_scroll = QScrollArea()
        self.monitor_scroll.setWidgetResizable(True)
        self.monitor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.monitor_scroll.setStyleSheet("""
            QScrollArea { 
                border: 1px solid #334155; border-radius: 8px;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background: #1e293b; width: 10px; border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #475569; border-radius: 5px; min-height: 35px;
            }
            QScrollBar::handle:vertical:hover { background: #64748b; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        self.monitor_container = QWidget()
        self.monitor_container.setStyleSheet("background-color: transparent;")
        self.monitor_container_layout = QVBoxLayout(self.monitor_container)
        self.monitor_container_layout.setContentsMargins(6, 6, 6, 6)
        self.monitor_container_layout.setSpacing(6)
        self.monitor_container_layout.addStretch()  # 底部弹性占位

        self.monitor_scroll.setWidget(self.monitor_container)
        layout.addWidget(self.monitor_scroll, stretch=2)

        return widget

    # ==================== 右侧设置面板 ====================
    def _create_settings_panel(self):
        """创建右侧监控设置面板"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # v2优化: 适配高分辨率屏幕，增加宽度
        scroll_area.setMaximumWidth(420)  # 原330 -> 420
        scroll_area.setMinimumWidth(340)  # 原280 -> 340
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # --- 全局监控设置 ---
        global_group = QGroupBox("⚙️ 全局设置")
        global_layout = QVBoxLayout(global_group)

        # 刷新间隔
        refresh_row = QHBoxLayout()
        refresh_row.addWidget(QLabel("刷新间隔:"))
        self.refresh_interval_spin = QSpinBox()
        self.refresh_interval_spin.setRange(3, 300)
        self.refresh_interval_spin.setValue(5)
        self.refresh_interval_spin.setSuffix(" 秒")
        self.refresh_interval_spin.setMinimumWidth(80)
        refresh_row.addWidget(self.refresh_interval_spin)
        refresh_row.addStretch()
        global_layout.addLayout(refresh_row)

        # 告警冷却期
        cooldown_row = QHBoxLayout()
        cooldown_row.addWidget(QLabel("告警冷却:"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(10, 600)
        self.cooldown_spin.setValue(60)
        self.cooldown_spin.setSuffix(" 秒")
        self.cooldown_spin.setMinimumWidth(80)
        cooldown_row.addWidget(self.cooldown_spin)
        cooldown_row.addStretch()
        global_layout.addLayout(cooldown_row)

        layout.addWidget(global_group)

        # --- 提醒开关 ---
        alert_group = QGroupBox("🔔 提醒开关")
        alert_layout = QVBoxLayout(alert_group)

        self.popup_cb = QCheckBox("启用弹窗提醒")
        self.popup_cb.setChecked(True)
        alert_layout.addWidget(self.popup_cb)

        self.sound_cb = QCheckBox("启用声音提醒")
        self.sound_cb.setChecked(True)
        alert_layout.addWidget(self.sound_cb)

        self.email_cb = QCheckBox("启用邮件提醒")
        self.email_cb.setChecked(False)
        alert_layout.addWidget(self.email_cb)

        self.one_shot_alert_cb = QCheckBox("每条规则仅告警一次(触发后不再重复)")
        self.one_shot_alert_cb.setChecked(True)
        alert_layout.addWidget(self.one_shot_alert_cb)

        layout.addWidget(alert_group)

        # --- 邮件配置 ---
        email_widgets_dict = self.email_cfg_dialog.create_settings_widget()
        self.email_widgets = email_widgets_dict
        layout.addWidget(email_widgets_dict['widget'])

        # 绑定测试/保存按钮信号（稍后在_connect_signals中统一处理）
        layout.addStretch()

        # --- 运行日志 ---
        log_group = QGroupBox("📝 运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(220)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)

        scroll_area.setWidget(panel)
        return scroll_area

    # ==================== 底部状态栏 ====================
    def _create_status_bar(self):
        """创建底部状态栏"""
        status_bar = QStatusBar()
        status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #0f172a;
                border-top: 1px solid #334155;
                color: #64748b;
                font-size: 13px;
                padding: 2px 8px;
            }
        """)
        self.status_bar = status_bar

        # 最后更新时间
        self.last_update_time_label = QLabel("最后更新: --:--:--")
        status_bar.addWidget(self.last_update_time_label)

        status_bar.addPermanentWidget(QLabel("|"))

        # 网络连接状态
        self.net_status_label = QLabel("● 网络: 正常")
        self.net_status_label.setObjectName("statusOk")
        status_bar.addWidget(self.net_status_label)

        status_bar.addPermanentWidget(QLabel("|"))

        # 版本信息
        ver_label = QLabel("v1.0.0")
        status_bar.addWidget(ver_label)

        return status_bar

    # ==================== 信号连接 ====================
    def _connect_signals(self):
        """连接所有信号和槽"""
        # 按钮信号
        self.start_btn.clicked.connect(self.on_start_monitoring)
        self.stop_btn.clicked.connect(self.on_stop_monitoring)
        self.filter_btn.clicked.connect(self.on_execute_filter)
        self.email_widgets['test_btn'].clicked.connect(self.on_test_email)
        self.email_widgets['save_btn'].clicked.connect(self.on_save_email_config)
        
        # v2新增: 方案管理信号
        self.load_profile_btn.clicked.connect(self.on_load_profile)
        self.save_profile_btn.clicked.connect(self.on_save_profile)
        self.delete_profile_btn.clicked.connect(self.on_delete_profile)
        
        # v5新增: 查看历史告警
        self.view_alerts_btn.clicked.connect(self.on_view_alert_history)

        # 表格复选框变化 → 更新监控列表
        self.match_table.itemChanged.connect(self.on_checkbox_changed)

        # 监控引擎信号
        self.monitor_engine.data_updated.connect(self.on_monitor_data_updated)
        self.monitor_engine.alert_triggered.connect(self.on_alert_triggered)
        self.monitor_engine.log_signal.connect(self.add_log)
        self.monitor_engine.status_changed.connect(self.on_monitor_status_changed)
        self.monitor_engine.cycle_completed.connect(self.on_cycle_completed)

    # ==================== 核心业务逻辑 ====================

    def on_execute_filter(self):
        """启动后台线程执行盘口筛选"""
        # 收集亚盘选中项
        asian_enabled = self.asian_enabled_cb.isChecked()
        asian_values = []
        if asian_enabled:
            for i in range(self.asian_list.count()):
                item = self.asian_list.item(i)
                if item.checkState() == Qt.Checked:
                    val = item.data(Qt.UserRole)
                    if val:
                        asian_values.append(str(val))

        # 收集大小球选中项
        ou_enabled = self.ou_enabled_cb.isChecked()
        ou_values = []
        if ou_enabled:
            for i in range(self.ou_list.count()):
                item = self.ou_list.item(i)
                if item.checkState() == Qt.Checked:
                    val = item.data(Qt.UserRole)
                    if val:
                        ou_values.append(str(val))

        # v2新增: 收集半场大小球大球初盘范围
        half_ou_enabled = self.half_ou_enabled_cb.isChecked()
        half_ou_min = float(self.half_ou_min_spin.value()) if half_ou_enabled else 0.75
        half_ou_max = float(self.half_ou_max_spin.value()) if half_ou_enabled else 1.5

        if not asian_values and not ou_values and not half_ou_enabled:
            QMessageBox.warning(self, "提示", "请至少选择一个亚盘、大小球盘口或启用半场大球初盘筛选！")
            return

        add_log = self.add_log
        add_log("=" * 50)
        add_log("开始执行筛选...")
        add_log(f"  亚盘筛选: {'启用' if asian_enabled else '禁用'}, 已选{len(asian_values)}个盘口")
        add_log(f"  大小球筛选: {'启用' if ou_enabled else '禁用'}, 已选{len(ou_values)}个盘口")
        if half_ou_enabled:
            add_log(f"  半场大球初盘: 启用, 范围 [{half_ou_min}, {half_ou_max}]")

        # 禁用筛选按钮，防止重复点击
        self.filter_btn.setEnabled(False)
        self.filter_btn.setText("⏳ 等待中...")

        # 创建并启动后台工作线程
        self._filter_thread = FilterWorkerThread(
            self.filter_ctrl,
            self.fetcher,
            asian_enabled, asian_values,
            ou_enabled, ou_values,
            half_ou_enabled, half_ou_min, half_ou_max  # v2新增
        )

        # 连接信号
        self._filter_thread.finished.connect(self.on_filter_finished)
        self._filter_thread.progress.connect(self.on_filter_progress)
        self._filter_thread.log_signal.connect(add_log)

        # 启动线程
        self._filter_thread.start()

    def on_filter_progress(self, message):
        """筛选进度更新"""
        self.filter_btn.setText(f"⏳ {message}")

    def on_filter_finished(self, success, matches, initial_cache, error):
        """筛选线程完成的回调（自动在主线程执行）"""
        try:
            if success and matches:
                self.filtered_matches = matches
                self.initial_odds_cache = initial_cache

                self.add_log(f"筛选完成! 共获取到 {len(matches)} 场比赛")

                # 显示到表格
                self._populate_match_table()

                # 关闭浏览器释放资源
                self.filter_ctrl.close_browser()
            elif success and not matches:
                self.add_log("未找到符合条件的比赛，请尝试调整筛选条件。")
                QMessageBox.information(
                    self, "提示",
                    "未找到符合筛选条件的比赛。\n请尝试调整盘口选项后重新筛选。"
                )
            else:
                self.add_log(error)
                QMessageBox.critical(self, "错误", f"筛选失败:\n{error}")
        finally:
            # 恢复按钮状态
            self.filter_btn.setEnabled(True)
            self.filter_btn.setText("🔍 执行筛选")

    def _populate_match_table(self):
        """填充比赛数据到表格"""
        self.match_table.setRowCount(0)
        self.match_widgets.clear()
        self.monitored_match_ids.clear()

        # 安全清空旧的监控配置卡片（从后往前删除，保留最后的stretch）
        layout = self.monitor_container_layout
        # 先移除stretch
        if layout.count() > 0:
            last_item = layout.itemAt(layout.count() - 1)
            if last_item and last_item.spacerItem():
                # 这是底部的stretch，暂时跳过，最后重新添加
                pass
        
        # 从前往后移除所有widget（不包括最后一个stretch）
        items_to_remove = []
        for i in range(layout.count() - 1):  # 不包括最后一项(stretch)
            item = layout.itemAt(i)
            if item and item.widget():
                items_to_remove.append(item.widget())
        
        for widget in items_to_remove:
            layout.removeWidget(widget)
            widget.deleteLater()

        print(f"[UI] _populate_match_table: 准备填充 {len(self.filtered_matches)} 场比赛")

        for idx, match in enumerate(self.filtered_matches):
            row = self.match_table.rowCount()
            self.match_table.insertRow(row)

            match_id = match.get('match_id', '')

            if not match_id:
                print(f"[UI] 警告: 第{idx}条数据缺少match_id, 跳过: {match}")
                continue

            # Col 0: 复选框 (✓)
            checkbox_item = QTableWidgetItem('')
            checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.Unchecked)
            checkbox_item.setTextAlignment(Qt.AlignCenter)
            self.match_table.setItem(row, 0, checkbox_item)

            # Col 1: 时间（联赛 + 比赛时间）
            league = match.get('league', '')
            time_val = match.get('match_time', '')
            if league:
                time_str = f"{league}  {time_val}" if time_val else league
            else:
                time_str = time_val
            self._set_cell(row, 1, time_str, align_center=True)

            # Col 2: 对阵（主队 vs 客队，带颜色区分）
            home = match.get('home_team', '')
            away = match.get('away_team', '')
            team_text = f"{home} vs {away}"
            team_item = QTableWidgetItem(team_text)
            team_item.setToolTip(f"主队: {home}\n客队: {away}")
            self._set_cell(row, 2, team_item.text(), item=team_item, align_center=False)

            # Col 3: 比分
            score = match.get('score', '-')
            self._set_cell(row, 3, score if score else '-', align_center=True)

            # Col 4: 状态（带颜色标识）
            status = match.get('status', '')
            status_item = QTableWidgetItem(status)
            # 根据状态着色
            if status and status.strip().isdigit():
                min_val = int(status.strip())
                if min_val <= 45:
                    status_item.setForeground(QBrush(QColor('#34d399')))   # 上半场绿色
                elif min_val <= 90:
                    status_item.setForeground(QBrush(QColor('#fbbf24')))   # 下半场黄色
                else:
                    status_item.setForeground(QBrush(QColor('#f87171')))   # 补时红色
            elif '中' in str(status):
                status_item.setForeground(QBrush(QColor('#a78bfa')));     # 中场紫色
            self._set_cell(row, 4, status, item=status_item, align_center=True)

            # Col 5: 亚盘初盘
            asian_initial = "-"
            if match_id in self.initial_odds_cache:
                ai = self.initial_odds_cache[match_id].get('asian_initial')
                if ai:
                    asian_initial = f"{ai.get('home_odds','-')}  {ai.get('handicap','-')}  {ai.get('away_odds','-')}"
            # v2优化: 如果没有初盘数据，显示"-"而不是实时数据，避免混淆
            self._set_cell(row, 5, asian_initial, align_center=True)

            # Col 6: 大小球初盘
            ou_initial = "-"
            if match_id in self.initial_odds_cache:
                oi = self.initial_odds_cache[match_id].get('ou_initial')
                if oi:
                    ou_initial = f"{oi.get('over_odds','-')}  {oi.get('goal_line','-')}  {oi.get('under_odds','-')}"
            # v2优化: 如果没有初盘数据，显示"-"而不是实时数据，避免混淆
            self._set_cell(row, 6, ou_initial, align_center=True)

            # Col 7: 半场亚盘初盘（新增）
            asian_half_initial = "-"
            if match_id in self.initial_odds_cache:
                ahi = self.initial_odds_cache[match_id].get('asian_half_initial')
                if ahi:
                    asian_half_initial = f"{ahi.get('home_odds','-')}  {ahi.get('handicap','-')}  {ahi.get('away_odds','-')}"
            asian_half_item = QTableWidgetItem(asian_half_initial)
            asian_half_item.setTextAlignment(Qt.AlignCenter)
            if asian_half_initial != "-":
                asian_half_item.setForeground(QBrush(QColor('#fbbf24')))  # 黄色高亮
            self.match_table.setItem(row, 7, asian_half_item)

            # Col 8: 半场大小球初盘（新增）
            ou_half_initial = "-"
            if match_id in self.initial_odds_cache:
                ohi = self.initial_odds_cache[match_id].get('ou_half_initial')
                if ohi:
                    ou_half_initial = f"{ohi.get('over_odds','-')}  {ohi.get('goal_line','-')}  {ohi.get('under_odds','-')}"
            ou_half_item = QTableWidgetItem(ou_half_initial)
            ou_half_item.setTextAlignment(Qt.AlignCenter)
            if ou_half_initial != "-":
                ou_half_item.setForeground(QBrush(QColor('#34d399')))  # 绿色高亮
            self.match_table.setItem(row, 8, ou_half_item)

            # Col 9: 来源标签
            source = match.get('source', '')
            sources = match.get('sources', [source])
            source_item = QTableWidgetItem(', '.join(sources))
            if '亚盘' in sources:
                source_item.setBackground(QBrush(QColor('#1e3a5f')))
                source_item.setForeground(QBrush(QColor('#60a5fa')))
            elif '大小球' in sources:
                source_item.setBackground(QBrush(QColor('#064e3b')))
                source_item.setForeground(QBrush(QColor('#34d399')))
            self._set_cell(row, 9, source_item.text(), item=source_item, align_center=True)

            # Col 10: 实时水位（待监控时填充）
            self._set_cell(row, 10, '-', align_center=True)

        # 更新统计
        self._update_match_summary()
        self.last_update_time_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")

    def _set_cell(self, row, col, text, item=None, align_center=False):
        """辅助方法：设置单元格"""
        if item is None:
            item = QTableWidgetItem(str(text))
        if align_center:
            item.setTextAlignment(Qt.AlignCenter)
        self.match_table.setItem(row, col, item)

    # ==================== 监控控制逻辑 ====================

    def on_start_monitoring(self):
        """开始监控"""
        if not self.monitored_match_ids:
            reply = QMessageBox.question(
                self, "确认",
                "尚未勾选任何比赛进行监控！\n是否直接开始？（需要先执行筛选并勾选比赛）",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 收集提醒开关配置到AlertService
        self.alert_svc.popup_enabled = self.popup_cb.isChecked()
        self.alert_svc.sound_enabled = self.sound_cb.isChecked()
        self.alert_svc.email_enabled = self.email_cb.isChecked()
        self.alert_svc.set_parent(self)

        # 应用邮件配置
        self.email_cfg_dialog.apply_to_alert_service(self.alert_svc)

        # 配置监控引擎
        self.monitor_engine.set_refresh_interval(self.refresh_interval_spin.value())
        self.monitor_engine.set_cooldown(self.cooldown_spin.value())
        self.monitor_engine.set_one_shot_alert(self.one_shot_alert_cb.isChecked())
        
        # v5修复: 设置alert_service到monitor_engine，使告警能够正确发送
        self.monitor_engine.alert_service = self.alert_svc

        # 收集被勾选的比赛及其监控配置
        self.monitor_engine.clear_matches()
        for row_idx, widget in self.match_widgets.items():
            config = widget.get_config()
            self.monitor_engine.add_match(config['match_id'], config)

        # 启动监控引擎线程
        self.monitor_engine.start()

        # 更新UI状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.filter_btn.setEnabled(False)
        self.toolbar_status.setText("● 监控中...")
        self.toolbar_status.setObjectName("statusOk")
        self.toolbar_status.style().unpolish(self.toolbar_status)
        self.toolbar_status.style().polish(self.toolbar_status)

        self.add_log("=" * 50)
        self.add_log(f"▶ 监控已启动! 共监控 {len(self.monitored_match_ids)} 场比赛")
        self.add_log(f"  刷新间隔: {self.refresh_interval_spin.value()}秒")
        self.add_log(f"  弹窗:{'开' if self.popup_cb.isChecked() else '关'} "
                      f"| 声音:{'开' if self.sound_cb.isChecked() else '关'} "
                      f"| 邮件:{'开' if self.email_cb.isChecked() else '关'} "
                      f"| 单次告警:{'开' if self.one_shot_alert_cb.isChecked() else '关'}")

    def on_stop_monitoring(self):
        """停止监控"""
        self.monitor_engine.stop()
        self.monitor_engine.wait(5000)  # 等待最多5秒让线程优雅退出

        # 恢复UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.filter_btn.setEnabled(True)
        self.toolbar_status.setText("● 已停止")
        self.toolbar_status.setObjectName("statusWarn")
        self.toolbar_status.style().unpolish(self.toolbar_status)
        self.toolbar_status.style().polish(self.toolbar_status)

        self.add_log("⏹ 监控已停止")

    def on_alert_triggered(self, match_id, alert_type, message):
        """
        处理监控引擎发出的告警信号
        :param match_id: 比赛ID
        :param alert_type: 告警类型
        :param message: 告警消息（已包含联赛名等信息）
        """
        try:
            # 调用alert_service发送告警（弹窗/声音/邮件）
            self.alert_svc.trigger_alert(match_id, alert_type, message)
        except Exception as e:
            self.add_log(f"[告警处理] 失败: {e}")

    def on_checkbox_changed(self, item):
        """表格复选框变化处理"""
        if item.column() == 0:  # 只处理第一列(复选框列)
            row = item.row()
            checked = item.checkState() == Qt.Checked
            match_id = self.filtered_matches[row].get('match_id', '') if row < len(self.filtered_matches) else ''

            if checked:
                self.monitored_match_ids.add(match_id)
                # 在下方独立的监控配置区域添加卡片
                self._show_monitor_widget(row, self.filtered_matches[row])
            else:
                self.monitored_match_ids.discard(match_id)
                if row in self.match_widgets:
                    widget = self.match_widgets[row]
                    # 从布局中移除并删除
                    self.monitor_container_layout.removeWidget(widget)
                    widget.deleteLater()
                    del self.match_widgets[row]

            self._update_match_summary()

    def _show_monitor_widget(self, row_idx, match_data):
        """在下方独立区域显示监控参数卡片（不再嵌入表格单元格）"""
        # 如果已有则不重复创建
        if row_idx in self.match_widgets:
            return

        widget = MatchMonitorWidget(match_data)
        self.match_widgets[row_idx] = widget

        # 连接"移除"按钮信号
        remove_btn = widget.findChild(QPushButton, f"remove_{match_data.get('match_id', '')}")
        if remove_btn:
            remove_btn.clicked.connect(lambda _, r=row_idx: self._remove_monitor_card(r))

        # 插入到 stretch 之前（即底部弹性占位之前）
        insert_pos = self.monitor_container_layout.count() - 1  # -1 是底部的stretch
        self.monitor_container_layout.insertWidget(insert_pos, widget)

    def _remove_monitor_card(self, row_idx):
        """移除某张监控卡片（点击卡片的✕按钮时触发）"""
        if row_idx not in self.match_widgets:
            return

        # 取消表格中对应行的勾选
        checkbox_item = self.match_table.item(row_idx, 0)
        if checkbox_item:
            checkbox_item.setCheckState(Qt.Unchecked)

        # 清理数据
        match_id = self.filtered_matches[row_idx].get('match_id', '') if row_idx < len(self.filtered_matches) else ''
        if match_id:
            self.monitored_match_ids.discard(match_id)

        # 移除控件
        widget = self.match_widgets.pop(row_idx, None)
        if widget:
            self.monitor_container_layout.removeWidget(widget)
            widget.deleteLater()

        self._update_match_summary()

    def _update_match_summary(self):
        """更新比赛统计摘要"""
        total = len(self.filtered_matches)
        monitored = len(self.monitored_match_ids)
        self.match_summary_label.setText(f"共 {total} 场 | 已勾选 {monitored} 场监控")
        self.monitor_count_label.setText(f"监控中: {monitored} 场")

    # ==================== 监控引擎回调 ====================

    def on_monitor_data_updated(self, match_id, latest_data):
        """监控数据更新回调"""
        # 在表格中找到对应行并更新最新水位
        for row in range(self.match_table.rowCount()):
            item_0 = self.match_table.item(row, 0)
            if item_0 is None:
                continue
            # 通过match_data查找对应的行
            if row < len(self.filtered_matches):
                m = self.filtered_matches[row]
                if m.get('match_id') == match_id:
                    # 更新第10列：实时水位（合并显示水位+时间）
                    asian_l = latest_data.get('asian_latest')
                    ou_l = latest_data.get('ou_latest')
                    parts = []
                    if asian_l:
                        parts.append(f"亚:{asian_l.get('home_odds','?')}  {asian_l.get('handicap','?')}  {asian_l.get('away_odds','?')}")
                    if ou_l:
                        parts.append(f"球:{ou_l.get('over_odds','?')}  {ou_l.get('goal_line','?')}  {ou_l.get('under_odds','?')}")

                    now_str = datetime.now().strftime('%H:%M:%S')
                    display_text = ' | '.join(parts) if parts else f"[{now_str}]"
                    if parts:
                        display_text += f"  {now_str}"

                    new_item = QTableWidgetItem(display_text)
                    new_item.setTextAlignment(Qt.AlignCenter)
                    new_item.setForeground(QBrush(QColor('#34d399')))  # 绿色高亮实时数据
                    new_item.setToolTip(f"最后更新: {now_str}")
                    self.match_table.setItem(row, 10, new_item)

                    # 同时更新比分和状态
                    if ou_l:
                        score = ou_l.get('score', '')
                        minute = ou_l.get('time', '')
                        if score:
                            si = QTableWidgetItem(score)
                            si.setTextAlignment(Qt.AlignCenter)
                            self.match_table.setItem(row, 3, si)
                        if minute:
                            mi = QTableWidgetItem(minute)
                            mi.setTextAlignment(Qt.AlignCenter)
                            self.match_table.setItem(row, 4, mi)
                    break

    def on_alert_triggered(self, match_id, alert_type, message):
        """告警触发回调"""
        # 转发给AlertService
        self.alert_svc.trigger_alert(match_id, alert_type, message)
        self.alert_count_label.setText(f"告警: {self.alert_svc.total_alerts} 次")

    def on_monitor_status_changed(self, running, count):
        """监控状态变化"""
        self.monitor_count_label.setText(f"监控中: {count} 场")

    def on_cycle_completed(self):
        """一轮轮询完成"""
        self.last_update_time_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")

    # ==================== v2方案管理 ====================
    
    def _refresh_profile_list(self):
        """刷新方案下拉列表"""
        current_text = self.profile_combo.currentText()
        self.profile_combo.clear()
        self.profile_combo.addItem("-- 选择方案 --")
        
        profiles = self.profile_manager.get_profile_names()
        for name in profiles:
            self.profile_combo.addItem(name)
        
        # 尝试恢复之前选中的项
        if current_text and current_text != "-- 选择方案 --":
            idx = self.profile_combo.findText(current_text)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
    
    def _get_current_widget_config(self):
        """获取当前选中比赛的配置"""
        selected_rows = self.match_table.selectedItems()
        if not selected_rows:
            return None, "请先选择一个比赛"
        
        row = selected_rows[0].row()
        if row not in self.match_widgets:
            return None, "该行没有配置控件"
        
        widget = self.match_widgets[row]
        config = widget.get_config()
        return config, None
    
    def on_save_profile(self):
        """保存当前配置为方案"""
        config, error = self._get_current_widget_config()
        if error:
            QMessageBox.warning(self, "提示", error)
            return
        
        # 弹出对话框输入方案名称
        name, ok = QInputDialog.getText(
            self,
            "保存方案",
            "请输入方案名称:",
            QLineEdit.Normal,
            f"方案_{datetime.now().strftime('%m%d_%H%M')}"
        )
        
        if not ok or not name.strip():
            return
        
        name = name.strip()
        
        # 检查是否已存在
        if name in self.profile_manager.profiles:
            reply = QMessageBox.question(
                self,
                "确认覆盖",
                f"方案 '{name}' 已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        # 保存方案
        success = self.profile_manager.save_profile(name, config)
        if success:
            self.add_log(f"[方案] 已保存方案: {name}")
            QMessageBox.information(self, "成功", f"方案 '{name}' 已保存！")
            self._refresh_profile_list()
            # 自动选中新保存的方案
            idx = self.profile_combo.findText(name)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        else:
            QMessageBox.critical(self, "错误", "保存方案失败！")
    
    def on_load_profile(self):
        """加载方案到当前选中的比赛（支持批量应用）"""
        profile_name = self.profile_combo.currentText()
        
        if not profile_name or profile_name == "-- 选择方案 --":
            QMessageBox.warning(self, "提示", "请先选择一个方案！")
            return
        
        # 加载方案配置
        profile_config = self.profile_manager.load_profile(profile_name)
        if not profile_config:
            QMessageBox.critical(self, "错误", f"无法加载方案 '{profile_name}'")
            return
        
        # v2优化: 获取所有勾选的比赛
        checked_rows = []
        for row in range(self.match_table.rowCount()):
            checkbox_item = self.match_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.Checked:
                checked_rows.append(row)
        
        if not checked_rows:
            QMessageBox.warning(self, "提示", "请至少勾选一场比赛！")
            return
        
        # 批量应用方案
        success_count = 0
        failed_count = 0
        failed_matches = []
        
        for row in checked_rows:
            widget = self.match_widgets[row]
            # v2优化: 从widget对象获取比赛信息
            match_id = getattr(widget, 'match_id', '')
            match_data = getattr(widget, 'match_data', {})
            home_team = match_data.get('home_team', '')
            away_team = match_data.get('away_team', '')
            
            try:
                # 设置各控件的值
                # 进球规则
                widget.target_goals_enabled_cb.setChecked(profile_config.get('target_goals_enabled', False))
                widget.target_goals_spin.setValue(profile_config.get('target_goals', 0))
                
                widget.first_half_goal_enabled_cb.setChecked(profile_config.get('first_half_goal_enabled', False))
                widget.first_half_goal_threshold_spin.setValue(profile_config.get('first_half_goal_threshold', 1))
                
                widget.second_half_goal_enabled_cb.setChecked(profile_config.get('second_half_goal_enabled', False))
                widget.second_half_goal_threshold_spin.setValue(profile_config.get('second_half_goal_threshold', 1))
                
                # 时间节点提醒
                widget.first_half_no_goal_enabled_cb.setChecked(profile_config.get('first_half_no_goal_enabled', False))
                widget.first_half_no_goal_threshold_spin.setValue(profile_config.get('first_half_no_goal_threshold', 1))  # v2新增: 加载进球数阈值
                widget.first_half_no_goal_minute_spin.setValue(profile_config.get('first_half_no_goal_minute', 30))
                
                widget.second_half_no_goal_enabled_cb.setChecked(profile_config.get('second_half_no_goal_enabled', False))
                widget.second_half_no_goal_threshold_spin.setValue(profile_config.get('second_half_no_goal_threshold', 1))  # v2新增: 加载进球数阈值
                widget.second_half_no_goal_minute_spin.setValue(profile_config.get('second_half_no_goal_minute', 70))
                
                # 水位监控
                widget.asian_home_en.setChecked(profile_config.get('asian_home_enabled', False))
                widget.asian_home_th.setValue(profile_config.get('asian_home_threshold', 0.85))
                
                widget.asian_away_en.setChecked(profile_config.get('asian_away_enabled', False))
                widget.asian_away_th.setValue(profile_config.get('asian_away_threshold', 0.85))
                
                widget.ou_over_en.setChecked(profile_config.get('ou_over_enabled', False))
                widget.ou_over_th.setValue(profile_config.get('ou_over_threshold', 0.85))
                
                widget.ou_under_en.setChecked(profile_config.get('ou_under_enabled', False))
                widget.ou_under_th.setValue(profile_config.get('ou_under_threshold', 0.85))
                
                # 盘口变化
                widget.hc_asian_en.setChecked(profile_config.get('handicap_change_asian_enabled', False))
                widget.hc_asian_th.setValue(profile_config.get('handicap_change_asian_threshold', 0.25))
                
                widget.hc_ou_en.setChecked(profile_config.get('handicap_change_ou_enabled', False))
                widget.hc_ou_th.setValue(profile_config.get('handicap_change_ou_threshold', 0.25))
                
                success_count += 1
                
            except Exception as e:
                failed_count += 1
                failed_matches.append(f"{home_team} vs {away_team}: {e}")
        
        # 显示结果
        if failed_count == 0:
            QMessageBox.information(
                self, 
                "成功", 
                f"方案 '{profile_name}' 已成功应用到 {success_count} 场比赛！"
            )
            self.add_log(f"[方案] 已批量应用方案 '{profile_name}' 到 {success_count} 场比赛")
        else:
            QMessageBox.warning(
                self,
                "部分成功",
                f"成功: {success_count} 场\n失败: {failed_count} 场\n\n失败详情:\n" + "\n".join(failed_matches[:5])
            )
            self.add_log(f"[方案] 批量应用方案 '{profile_name}': 成功{success_count}场, 失败{failed_count}场")
    
    def on_delete_profile(self):
        """删除选中的方案"""
        profile_name = self.profile_combo.currentText()
        
        if not profile_name or profile_name == "-- 选择方案 --":
            QMessageBox.warning(self, "提示", "请先选择一个方案！")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除方案 '{profile_name}' 吗？\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 删除方案
        success = self.profile_manager.delete_profile(profile_name)
        if success:
            self.add_log(f"[方案] 已删除方案: {profile_name}")
            QMessageBox.information(self, "成功", f"方案 '{profile_name}' 已删除！")
            self._refresh_profile_list()
        else:
            QMessageBox.critical(self, "错误", "删除方案失败！")

    # ==================== 辅助方法 ====================

    def add_log(self, message):
        """添加运行日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_test_email(self):
        """发送测试邮件"""
        self.email_cfg_dialog.collect_from_widgets(self.email_widgets)
        ok, msg = self.email_cfg_dialog.send_test_email()
        self.email_widgets['status_label'].setText(msg)
        if ok:
            self.email_widgets['status_label'].setStyleSheet("color: #10b981; font-size: 11px;")
        else:
            self.email_widgets['status_label'].setStyleSheet("color: #ef4444; font-size: 11px;")
        self.add_log(f"[邮件] 测试结果: {msg}")

    def on_save_email_config(self):
        """保存邮件配置"""
        self.email_cfg_dialog.collect_from_widgets(self.email_widgets)
        saved = self.email_cfg_dialog.save_config()
        if saved:
            self.email_widgets['status_label'].setText("✓ 配置已保存")
            self.email_widgets['status_label'].setStyleSheet("color: #10b981; font-size: 11px;")
            self.add_log("[邮件] 配置已保存")
        else:
            self.email_widgets['status_label'].setText("✗ 保存失败")
            self.email_widgets['status_label'].setStyleSheet("color: #ef4444; font-size: 11px;")

    def on_view_alert_history(self):
        """v5新增: 查看历史告警记录"""
        dialog = AlertHistoryDialog(self)
        dialog.exec_()

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止监控
        if self.monitor_engine.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "监控正在运行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.on_stop_monitoring()
                event.accept()
            else:
                event.ignore()
        else:
            # 清理资源
            self.filter_ctrl.close_browser()
            event.accept()


# ============================================================
# 入口
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
