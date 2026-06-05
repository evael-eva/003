"""
测试半场大小球筛选逻辑
验证是否正确检查 over_odds（大球水位）而不是 goal_line（盘口大小）
"""

# 模拟数据结构
ou_half_initial = {
    'time': '初盘',
    'score': '',
    'over_odds': '0.95',  # 大球水位 ← 应该检查这个
    'goal_line': '1.25',  # 盘口大小 ← 不应该检查这个
    'handicap': '1.25',   # 转换后的盘口
    'under_odds': '0.85',
    'change_time': '',
    'status': '初'
}

# 用户设置的筛选范围
half_ou_min = 0.75
half_ou_max = 1.5

print("=" * 60)
print("测试半场大小球筛选逻辑")
print("=" * 60)
print()

print("用户设置的筛选范围:")
print(f"  最小值: {half_ou_min}")
print(f"  最大值: {half_ou_max}")
print()

print("比赛数据:")
print(f"  over_odds (大球水位): {ou_half_initial['over_odds']}")
print(f"  goal_line (盘口大小): {ou_half_initial['goal_line']}")
print(f"  handicap (转换后盘口): {ou_half_initial['handicap']}")
print()

# 正确的筛选逻辑：检查 over_odds
over_odds_raw = ou_half_initial.get('over_odds', '')
if over_odds_raw:
    try:
        over_odds_value = float(over_odds_raw)
        
        print("✅ 正确的筛选逻辑（检查 over_odds）:")
        if half_ou_min <= over_odds_value <= half_ou_max:
            print(f"  ✓ 保留比赛: 大球水位 {over_odds_raw} 在范围 [{half_ou_min}, {half_ou_max}] 内")
        else:
            print(f"  ✗ 排除比赛: 大球水位 {over_odds_raw} 不在范围 [{half_ou_min}, {half_ou_max}] 内")
    except (ValueError, TypeError) as e:
        print(f"  ✗ 排除比赛: 无法解析大球水位 '{over_odds_raw}'")
else:
    print("  ✗ 排除比赛: 无大球水位数据")

print()

# 错误的筛选逻辑：检查 goal_line（这是您遇到的bug）
goal_line_raw = ou_half_initial.get('goal_line', '')
if goal_line_raw:
    try:
        goal_line_value = float(goal_line_raw)
        
        print("❌ 错误的筛选逻辑（检查 goal_line）:")
        if half_ou_min <= goal_line_value <= half_ou_max:
            print(f"  ✓ 保留比赛: 盘口大小 {goal_line_raw} 在范围 [{half_ou_min}, {half_ou_max}] 内")
        else:
            print(f"  ✗ 排除比赛: 盘口大小 {goal_line_raw} 不在范围 [{half_ou_min}, {half_ou_max}] 内")
    except (ValueError, TypeError) as e:
        print(f"  ✗ 排除比赛: 无法解析盘口大小 '{goal_line_raw}'")
else:
    print("  ✗ 排除比赛: 无盘口大小数据")

print()
print("=" * 60)
print("结论:")
print("=" * 60)
print()
print("当前代码应该检查的是 over_odds (大球水位)")
print("如果您看到的日志显示的是 '半场大球初盘1.25'，说明:")
print("  1. 您可能运行的是旧版本代码")
print("  2. 或者代码中某处错误地使用了 goal_line")
print()
print("请确认您运行的是 v13/盘口监控邮件提醒.py 的最新版本")
