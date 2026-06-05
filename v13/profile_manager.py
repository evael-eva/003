#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
监控方案管理器 - 保存和加载监控配置方案
功能：
1. 保存当前配置为命名方案
2. 加载已有方案快速应用
3. 删除/管理方案
4. 方案持久化存储（JSON格式）
"""

import json
import os
from datetime import datetime


class ProfileManager:
    """监控方案管理器"""
    
    def __init__(self, profile_file='monitor_profiles.json'):
        """
        初始化方案管理器
        :param profile_file: 方案配置文件路径
        """
        self.profile_file = profile_file
        self.profiles = {}
        self.load_profiles()
    
    def load_profiles(self):
        """从文件加载所有方案"""
        if os.path.exists(self.profile_file):
            try:
                with open(self.profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.profiles = data.get('profiles', {})
                return True
            except Exception as e:
                print(f"[方案管理器] 加载失败: {e}")
                self.profiles = {}
                return False
        return True
    
    def save_profiles(self):
        """保存所有方案到文件"""
        try:
            data = {
                'profiles': self.profiles,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '2.0'
            }
            with open(self.profile_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[方案管理器] 保存失败: {e}")
            return False
    
    def save_profile(self, name, config):
        """
        保存单个方案
        :param name: 方案名称
        :param config: 配置字典（不包含match_id等比赛特定信息）
        :return: bool 是否成功
        """
        if not name or not name.strip():
            return False
        
        name = name.strip()
        
        # 过滤掉比赛特定的字段
        filtered_config = {k: v for k, v in config.items() 
                          if k not in ['match_id', 'home_team', 'away_team']}
        
        self.profiles[name] = {
            'config': filtered_config,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': f'创建于 {datetime.now().strftime("%Y-%m-%d %H:%M")}'
        }
        
        return self.save_profiles()
    
    def load_profile(self, name):
        """
        加载指定方案
        :param name: 方案名称
        :return: dict 配置字典，不存在返回None
        """
        if name in self.profiles:
            return self.profiles[name].get('config', {})
        return None
    
    def delete_profile(self, name):
        """
        删除指定方案
        :param name: 方案名称
        :return: bool 是否成功
        """
        if name in self.profiles:
            del self.profiles[name]
            return self.save_profiles()
        return False
    
    def get_profile_names(self):
        """获取所有方案名称列表"""
        return list(self.profiles.keys())
    
    def get_profile_info(self, name):
        """
        获取方案详细信息
        :param name: 方案名称
        :return: dict 包含配置、创建时间等信息
        """
        if name in self.profiles:
            return self.profiles[name]
        return None
    
    def rename_profile(self, old_name, new_name):
        """
        重命名方案
        :param old_name: 原名称
        :param new_name: 新名称
        :return: bool 是否成功
        """
        if old_name in self.profiles and new_name not in self.profiles:
            self.profiles[new_name] = self.profiles.pop(old_name)
            return self.save_profiles()
        return False
    
    def export_profile(self, name, filepath):
        """
        导出方案到文件
        :param name: 方案名称
        :param filepath: 导出文件路径
        :return: bool 是否成功
        """
        if name not in self.profiles:
            return False
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.profiles[name], f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[方案管理器] 导出失败: {e}")
            return False
    
    def import_profile(self, filepath, name=None):
        """
        从文件导入方案
        :param filepath: 导入文件路径
        :param name: 自定义方案名称（可选）
        :return: str 方案名称，失败返回None
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 兼容不同格式
            if 'config' in data:
                config = data['config']
                profile_name = name or data.get('name', os.path.basename(filepath))
            else:
                config = data
                profile_name = name or os.path.basename(filepath)
            
            self.profiles[profile_name] = {
                'config': config,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'description': f'导入自 {os.path.basename(filepath)}'
            }
            
            self.save_profiles()
            return profile_name
        except Exception as e:
            print(f"[方案管理器] 导入失败: {e}")
            return None


# 测试代码
if __name__ == '__main__':
    manager = ProfileManager()
    
    # 测试保存方案
    test_config = {
        'target_goals_enabled': True,
        'target_goals': 3,
        'first_half_alert': True,
        'second_half_alert': True,
        'asian_home_enabled': False,
        'asian_home_threshold': 0.85,
    }
    
    print("保存方案...")
    manager.save_profile('测试方案', test_config)
    
    print("\n所有方案:", manager.get_profile_names())
    
    print("\n加载方案...")
    loaded = manager.load_profile('测试方案')
    print("加载的配置:", loaded)
    
    print("\n删除方案...")
    manager.delete_profile('测试方案')
    print("剩余方案:", manager.get_profile_names())
