#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
v11 代理失效检测与替换测试脚本
用于验证代理失效后是否能正确获取新代理
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from odds_fetcher import OddsFetcher


def test_proxy_failure_detection():
    """测试代理失效检测和替换逻辑"""
    print("=" * 70)
    print("v11 代理失效检测与替换测试")
    print("=" * 70)
    
    # 模拟配置（请根据实际情况修改API密钥）
    proxy_config = {
        'enabled': True,
        'api_url': 'https://share.proxy.qg.net/get?key=YOUR_KEY&format=txt',
        'extract_num': 10,
        'auth_username': '',
        'auth_password': '',
    }
    
    print("\n[步骤1] 初始化OddsFetcher并获取第一个代理...")
    fetcher = OddsFetcher(proxy_config)
    
    if not fetcher.current_proxy:
        print("❌ 未能获取初始代理，请检查API配置")
        return False
    
    initial_proxy = fetcher.current_proxy
    print(f"✅ 初始代理: {initial_proxy}")
    print(f"✅ 开始时间: {fetcher.proxy_start_time}")
    
    print("\n[步骤2] 模拟代理失效场景...")
    print(f"   当前代理: {initial_proxy}")
    print(f"   调用 _mark_proxy_failed() 标记失效...")
    
    # 模拟失效处理
    fetcher._mark_proxy_failed(initial_proxy)
    
    new_proxy = fetcher.current_proxy
    if new_proxy and new_proxy != initial_proxy:
        print(f"✅ 成功获取新代理: {new_proxy}")
        print(f"✅ 代理已更换: {initial_proxy} → {new_proxy}")
        print(f"✅ 新的开始时间: {fetcher.proxy_start_time}")
        return True
    elif new_proxy == initial_proxy:
        print(f"⚠️ 代理未更换（可能API调用失败）")
        print(f"   当前仍使用: {new_proxy}")
        return False
    else:
        print(f"❌ 获取新代理失败，current_proxy为None")
        return False


def test_timed_rotation():
    """测试定时轮换逻辑"""
    print("\n" + "=" * 70)
    print("测试5分钟定时轮换")
    print("=" * 70)
    
    proxy_config = {
        'enabled': True,
        'api_url': 'https://share.proxy.qg.net/get?key=YOUR_KEY&format=txt',
        'extract_num': 10,
        'auth_username': '',
        'auth_password': '',
    }
    
    print("\n[步骤1] 初始化并获取代理...")
    fetcher = OddsFetcher(proxy_config)
    
    if not fetcher.current_proxy:
        print("❌ 未能获取初始代理")
        return False
    
    old_proxy = fetcher.current_proxy
    print(f"✅ 当前代理: {old_proxy}")
    
    print("\n[步骤2] 模拟时间流逝（设置为6分钟前）...")
    import time
    original_time = fetcher.proxy_start_time
    fetcher.proxy_start_time = time.time() - 360  # 6分钟前
    
    print(f"   模拟开始时间: {fetcher.proxy_start_time}")
    print(f"   已过时间: 360秒 (6分钟)")
    print(f"   轮换阈值: {fetcher.PROXY_ROTATE_INTERVAL}秒 (5分钟)")
    
    print("\n[步骤3] 调用 _rotate_proxy_if_needed() 检查轮换...")
    rotated = fetcher._rotate_proxy_if_needed()
    
    if rotated:
        new_proxy = fetcher.current_proxy
        if new_proxy != old_proxy:
            print(f"✅ 触发轮换，获取新代理: {new_proxy}")
            print(f"✅ 代理已更换: {old_proxy} → {new_proxy}")
            # 恢复原始时间
            fetcher.proxy_start_time = original_time
            return True
        else:
            print(f"⚠️ 触发轮换但代理未变化（可能API失败）")
            # 恢复原始时间
            fetcher.proxy_start_time = original_time
            return False
    else:
        print(f"❌ 未触发轮换")
        # 恢复原始时间
        fetcher.proxy_start_time = original_time
        return False


def test_exception_handling():
    """测试异常捕获和失效处理"""
    print("\n" + "=" * 70)
    print("测试HTTP请求中的异常处理")
    print("=" * 70)
    
    print("\n说明: 以下测试会实际发起HTTP请求，如果代理不可用会触发失效处理")
    print("      请确保API配置正确，或准备好观察日志输出\n")
    
    proxy_config = {
        'enabled': True,
        'api_url': 'https://share.proxy.qg.net/get?key=YOUR_KEY&format=txt',
        'extract_num': 10,
        'auth_username': '',
        'auth_password': '',
    }
    
    fetcher = OddsFetcher(proxy_config)
    
    if not fetcher.current_proxy:
        print("❌ 未能获取代理，跳过测试")
        return False
    
    print(f"✅ 当前代理: {fetcher.current_proxy}")
    print(f"\n尝试请求一个不存在的比赛ID来测试异常处理...")
    
    try:
        # 使用一个可能不存在的比赛ID
        result = fetcher.fetch_asian_odds("999999999")
        
        if result.get('error'):
            print(f"⚠️ 请求返回错误: {result['error']}")
            if '代理' in result['error']:
                print(f"✅ 检测到代理错误，应该已触发失效处理")
                print(f"   当前代理: {fetcher.current_proxy}")
                return True
            else:
                print(f"   非代理错误，未触发失效处理")
                return False
        else:
            print(f"✅ 请求成功（意外）")
            print(f"   当前代理: {fetcher.current_proxy}")
            return True
            
    except Exception as e:
        print(f"❌ 测试过程异常: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "🔍" * 35)
    print("开始 v11 代理失效检测与替换测试")
    print("🔍" * 35 + "\n")
    
    results = []
    
    # 测试1: 失效检测和替换
    print("\n" + "─" * 70)
    print("测试1: 代理失效检测和立即替换")
    print("─" * 70)
    try:
        result1 = test_proxy_failure_detection()
        results.append(("失效检测与替换", result1))
    except Exception as e:
        print(f"❌ 测试1异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("失效检测与替换", False))
    
    # 测试2: 定时轮换
    print("\n" + "─" * 70)
    print("测试2: 5分钟定时轮换")
    print("─" * 70)
    try:
        result2 = test_timed_rotation()
        results.append(("定时轮换", result2))
    except Exception as e:
        print(f"❌ 测试2异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("定时轮换", False))
    
    # 测试3: 异常处理
    print("\n" + "─" * 70)
    print("测试3: HTTP请求异常处理")
    print("─" * 70)
    try:
        result3 = test_exception_handling()
        results.append(("异常处理", result3))
    except Exception as e:
        print(f"❌ 测试3异常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("异常处理", False))
    
    # 总结
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name:20s} : {status}")
    
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    
    print(f"\n总计: {passed_count}/{total} 测试通过")
    
    if passed_count == total:
        print("\n🎉 所有测试通过！代理失效检测和替换逻辑正常工作。")
    else:
        print(f"\n⚠️ 有 {total - passed_count} 个测试失败，请检查日志和配置。")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
