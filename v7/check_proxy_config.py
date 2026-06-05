# -*- coding: utf-8 -*-
"""
代理配置诊断工具
用于检查代理配置是否正确加载和应用
"""

import json
import os

def check_proxy_config():
    """检查代理配置文件"""
    config_file = "proxy_config.json"
    
    print("=" * 60)
    print("代理配置诊断工具")
    print("=" * 60)
    
    # 检查配置文件是否存在
    if not os.path.exists(config_file):
        print(f"\n❌ 配置文件不存在: {config_file}")
        print("请先在程序中配置并保存代理设置")
        return False
    
    # 读取配置
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"\n✅ 找到配置文件: {config_file}")
        print("\n当前配置内容:")
        print("-" * 60)
        for key, value in config.items():
            if key == 'api_url' and len(str(value)) > 50:
                print(f"  {key}: {str(value)[:47]}...")
            else:
                print(f"  {key}: {value}")
        print("-" * 60)
        
        # 检查关键字段
        issues = []
        
        if not config.get('enabled'):
            issues.append("❌ 代理未启用 (enabled=False)")
        else:
            print("\n✅ 代理已启用")
        
        if not config.get('api_url'):
            issues.append("❌ API接口地址为空")
        else:
            print(f"✅ API接口: {config['api_url'][:50]}...")
        
        if not config.get('extract_num') or config.get('extract_num') < 1:
            issues.append("⚠️  提取数量不合理 (建议10-50)")
        else:
            print(f"✅ 提取数量: {config['extract_num']}")
        
        # 测试API是否可访问
        if config.get('api_url'):
            print("\n正在测试API接口...")
            try:
                import requests
                response = requests.get(config['api_url'], timeout=10)
                if response.status_code == 200:
                    text = response.text.strip()
                    if text:
                        import re
                        pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,5})'
                        matches = re.findall(pattern, text)
                        proxies = [f'{ip}:{port}' for ip, port in matches]
                        print(f"✅ API返回成功! 提取到 {len(proxies)} 个代理IP")
                        if proxies:
                            print(f"   示例: {proxies[0]}")
                    else:
                        issues.append("❌ API返回内容为空")
                else:
                    issues.append(f"❌ API返回HTTP错误: {response.status_code}")
            except Exception as e:
                issues.append(f"❌ API请求失败: {str(e)}")
        
        # 总结
        print("\n" + "=" * 60)
        if issues:
            print("发现问题:")
            for issue in issues:
                print(f"  {issue}")
            print("\n请根据上述提示修复配置")
            return False
        else:
            print("✅ 配置检查通过!")
            print("\n如果程序仍然显示'无代理'，请检查:")
            print("  1. 是否在启动监控前点击了'保存所有配置'")
            print("  2. 查看运行日志中的'[代理调试]'信息")
            print("  3. 重启程序后重新应用配置")
            return True
            
    except json.JSONDecodeError:
        print(f"\n❌ 配置文件格式错误: {config_file}")
        print("请删除该文件并重新配置")
        return False
    except Exception as e:
        print(f"\n❌ 检查过程出错: {str(e)}")
        return False

if __name__ == "__main__":
    check_proxy_config()
