# v13 修复"上半场仅N球"和"下半场仅N球"规则逻辑错误

## 🐛 问题描述

**用户报告：**
```json
{
  "timestamp": "2026-04-28 22:42:00",
  "match_id": "2980858",
  "alert_type": "first_half_no_goal",
  "message": "【阿后备】⚠️ 上半场仅1球! 艾斯潘诺 (后备) vs 波多黎各努埃沃 (后备): 
             比赛进行到第37分钟，上半场第37分钟进1球后，至今未进第2球"
}
```

**问题分析：**
- 用户设定：上半场仅1球，时间点设为 **30分钟**
- 实际触发：第 **37分钟** 进了1球后立即触发
- **错误原因**：代码没有检查进球是否发生在设定的时间点（30分钟）**之前**

---

## 🔍 根本原因

### 错误的逻辑

**原代码逻辑：**
```python
# 记录上半场第threshold_goals个进球的时间
if first_half_goals == threshold_goals and state.get('first_half_one_goal_time') is None:
    state['first_half_one_goal_time'] = current_minute

# 如果上半场有threshold_goals个进球，且到达设定时间还没有第(threshold_goals+1)个进球
if (first_half_goals == threshold_goals and 
    current_minute >= threshold_minute and 
    not state.get('first_half_no_goal_alerted', False)):
    # ❌ 触发提醒
```

**问题：**
1. 只要 `first_half_goals == threshold_goals`（当前进球数等于阈值）
2. 且 `current_minute >= threshold_minute`（当前时间超过设定时间）
3. **就触发提醒，不管进球是什么时候发生的！**

**错误场景：**
```
用户设定：上半场仅1球，时间点30分钟

实际情况：
- 第37分钟进了1球
- 此时 current_minute = 37, first_half_goals = 1
- 条件检查：
  ✓ first_half_goals == 1 (threshold_goals)
  ✓ current_minute >= 30 (threshold_minute)
  → 立即触发提醒 ❌

但这是错误的！因为：
- 进球发生在第37分钟（已经超过30分钟）
- 用户想要的是：在30分钟之前进了1球，然后到30分钟时还是只有1球
```

---

### 正确的逻辑

**应该满足的条件：**
1. ✅ 在 `threshold_minute` **之前**，进球数达到了 `threshold_goals`
2. ✅ 到了 `threshold_minute` 时，进球数仍然是 `threshold_goals`（没有增加）
3. ✅ 此时才触发提醒

**正确场景：**
```
用户设定：上半场仅1球，时间点30分钟

正确情况：
- 第20分钟进了1球 ← 在30分钟之前 ✅
- 第30分钟时，仍然是1球 ← 没有增加 ✅
- 触发提醒 ✅

错误情况：
- 第37分钟进了1球 ← 已经超过30分钟 ❌
- 不触发提醒 ✅
```

---

## ✅ 修复方案

### 核心改进

**新增状态字段：**
```python
'first_half_reached_threshold_before_minute': False  # v13新增: 标记是否在threshold_minute之前达到阈值
```

**修复后的逻辑：**

#### 1. 记录进球时间时判断是否在设定时间之前

```python
# v13修复: 记录上半场第threshold_goals个进球的时间（必须在threshold_minute之前）
if first_half_goals == threshold_goals and state.get('first_half_one_goal_time') is None:
    if current_minute < threshold_minute:
        # ✅ 在设定时间之前达到了阈值，记录时间
        state['first_half_one_goal_time'] = current_minute
        state['first_half_reached_threshold_before_minute'] = True
    else:
        # ❌ 已经超过设定时间才达到阈值，不触发提醒
        state['first_half_one_goal_time'] = current_minute
        state['first_half_reached_threshold_before_minute'] = False
```

#### 2. 触发提醒时检查是否在设定时间之前达到阈值

```python
# v13修复: 如果上半场有threshold_goals个进球，且是在threshold_minute之前达到的，
#          且到达设定时间还没有第(threshold_goals+1)个进球
if (first_half_goals == threshold_goals and 
    state.get('first_half_reached_threshold_before_minute', False) and  # ← 新增检查
    current_minute >= threshold_minute and 
    not state.get('first_half_no_goal_alerted', False)):
    # ✅ 触发提醒
```

---

### 完整修复代码

#### 修复1: 上半场仅N球规则

**文件：** `v13/monitor_engine.py` 第1324-1351行

**修改前：**
```python
if match_id not in self.no_goal_states:
    self.no_goal_states[match_id] = {
        'first_half_one_goal_time': None,
        'first_half_no_goal_alerted': False
    }

state = self.no_goal_states[match_id]

# 记录上半场第threshold_goals个进球的时间
if first_half_goals == threshold_goals and state.get('first_half_one_goal_time') is None:
    state['first_half_one_goal_time'] = current_minute

# 如果上半场有threshold_goals个进球，且到达设定时间还没有第(threshold_goals+1)个进球
if (first_half_goals == threshold_goals and 
    current_minute >= threshold_minute and 
    not state.get('first_half_no_goal_alerted', False)):
    goal_time = state.get('first_half_one_goal_time', 0)
    self._try_trigger(...)
    state['first_half_no_goal_alerted'] = True
```

**修改后：**
```python
if match_id not in self.no_goal_states:
    self.no_goal_states[match_id] = {
        'first_half_one_goal_time': None,
        'first_half_no_goal_alerted': False,
        'first_half_reached_threshold_before_minute': False  # v13新增
    }

state = self.no_goal_states[match_id]

# v13修复: 记录上半场第threshold_goals个进球的时间（必须在threshold_minute之前）
if first_half_goals == threshold_goals and state.get('first_half_one_goal_time') is None:
    if current_minute < threshold_minute:
        # ✅ 在设定时间之前达到了阈值，记录时间
        state['first_half_one_goal_time'] = current_minute
        state['first_half_reached_threshold_before_minute'] = True
    else:
        # ❌ 已经超过设定时间才达到阈值，不触发提醒
        state['first_half_one_goal_time'] = current_minute
        state['first_half_reached_threshold_before_minute'] = False

# v13修复: 如果上半场有threshold_goals个进球，且是在threshold_minute之前达到的，
#          且到达设定时间还没有第(threshold_goals+1)个进球
if (first_half_goals == threshold_goals and 
    state.get('first_half_reached_threshold_before_minute', False) and  # ← 新增检查
    current_minute >= threshold_minute and 
    not state.get('first_half_no_goal_alerted', False)):
    goal_time = state.get('first_half_one_goal_time', 0)
    self._try_trigger(...)
    state['first_half_no_goal_alerted'] = True
```

---

#### 修复2: 下半场仅N球规则

**文件：** `v13/monitor_engine.py` 第1362-1391行

**同样的修复逻辑应用于下半场规则：**

```python
if match_id not in self.no_goal_states:
    self.no_goal_states[match_id] = {
        'second_half_one_goal_time': None,
        'second_half_no_goal_alerted': False,
        'second_half_baseline_goals': None,
        'second_half_reached_threshold_before_minute': False  # v13新增
    }

state = self.no_goal_states[match_id]

# ... 计算 actual_second_half_goals ...

# v13修复: 记录下半场第threshold_goals个进球的时间（必须在threshold_minute之前）
if actual_second_half_goals == threshold_goals and state.get('second_half_one_goal_time') is None:
    if current_minute < threshold_minute:
        # ✅ 在设定时间之前达到了阈值，记录时间
        state['second_half_one_goal_time'] = current_minute
        state['second_half_reached_threshold_before_minute'] = True
    else:
        # ❌ 已经超过设定时间才达到阈值，不触发提醒
        state['second_half_one_goal_time'] = current_minute
        state['second_half_reached_threshold_before_minute'] = False

# v13修复: 触发提醒时检查是否在设定时间之前达到阈值
if (actual_second_half_goals == threshold_goals and 
    state.get('second_half_reached_threshold_before_minute', False) and  # ← 新增检查
    current_minute >= threshold_minute and 
    not state.get('second_half_no_goal_alerted', False)):
    goal_time = state.get('second_half_one_goal_time', 0)
    self._try_trigger(...)
    state['second_half_no_goal_alerted'] = True
```

---

## 📊 修复对比

### 场景示例

**用户设定：**
- 规则：上半场仅1球
- 时间点：30分钟

---

#### 修复前（错误）

**场景1: 第37分钟进1球**
```
第37分钟: first_half_goals = 1

条件检查:
✓ first_half_goals == 1 (threshold_goals)
✓ current_minute >= 30 (threshold_minute)
→ ❌ 立即触发提醒（错误！）

日志:
【阿后备】⚠️ 上半场仅1球! ... 比赛进行到第37分钟，上半场第37分钟进1球后，至今未进第2球
```

**问题：**
- 进球发生在第37分钟（已经超过30分钟）
- 不应该触发提醒

---

#### 修复后（正确）

**场景1: 第37分钟进1球**
```
第37分钟: first_half_goals = 1

记录进球时间:
current_minute (37) >= threshold_minute (30)
→ first_half_reached_threshold_before_minute = False ❌

触发检查:
✓ first_half_goals == 1
✗ first_half_reached_threshold_before_minute == False
→ ✅ 不触发提醒（正确！）
```

**场景2: 第20分钟进1球，第30分钟时仍是1球**
```
第20分钟: first_half_goals = 1

记录进球时间:
current_minute (20) < threshold_minute (30)
→ first_half_reached_threshold_before_minute = True ✅

第30分钟: first_half_goals = 1

触发检查:
✓ first_half_goals == 1
✓ first_half_reached_threshold_before_minute == True
✓ current_minute >= 30
→ ✅ 触发提醒（正确！）

日志:
【阿后备】⚠️ 上半场仅1球! ... 比赛进行到第30分钟，上半场第20分钟进1球后，至今未进第2球
```

---

### 关键改进点

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| **状态字段** | 无 | `first_half_reached_threshold_before_minute` |
| **进球时间判断** | 无条件记录 | 检查是否在 `threshold_minute` 之前 |
| **触发条件** | 只检查当前进球数和时间 | 额外检查是否在设定时间之前达到阈值 |
| **逻辑正确性** | ❌ 错误 | ✅ 正确 |

---

## 🎯 测试用例

### 测试1: 上半场仅1球，时间点30分钟

| 场景 | 进球时间 | 检查时间 | 预期结果 | 修复前 | 修复后 |
|------|---------|---------|---------|--------|--------|
| 场景1 | 第20分钟进1球 | 第30分钟 | ✅ 触发 | ✅ 触发 | ✅ 触发 |
| 场景2 | 第37分钟进1球 | 第37分钟 | ❌ 不触发 | ❌ 触发 | ✅ 不触发 |
| 场景3 | 第25分钟进1球，第28分钟进2球 | 第30分钟 | ❌ 不触发 | ❌ 不触发 | ❌ 不触发 |
| 场景4 | 第10分钟进1球，第35分钟仍是1球 | 第35分钟 | ✅ 触发 | ✅ 触发 | ✅ 触发 |

---

### 测试2: 下半场仅1球，时间点70分钟

| 场景 | 进球时间 | 检查时间 | 预期结果 | 修复前 | 修复后 |
|------|---------|---------|---------|--------|--------|
| 场景1 | 第60分钟进1球（下半场第15分钟） | 第70分钟 | ✅ 触发 | ✅ 触发 | ✅ 触发 |
| 场景2 | 第75分钟进1球（下半场第30分钟） | 第75分钟 | ❌ 不触发 | ❌ 触发 | ✅ 不触发 |
| 场景3 | 第55分钟进1球，第65分钟进2球 | 第70分钟 | ❌ 不触发 | ❌ 不触发 | ❌ 不触发 |

---

## 📝 代码修改统计

| 文件 | 修改内容 | 行数变化 |
|------|---------|----------|
| **v13/monitor_engine.py** | 修复上半场规则 + 修复下半场规则 | +28/-10 |
| **总计** | - | **+18行** |

---

## ✅ 验证方法

### 测试步骤

1. **启动 v13 版本**
2. **启用"上半场仅N球提醒"**
3. **设置参数：**
   - 进球数：1
   - 时间点：30分钟
4. **监控一场比赛**
5. **观察日志输出**

---

### 预期结果

#### 正确情况1: 第20分钟进1球，第30分钟仍是1球

```
[监控引擎] ⚠️ 上半场仅1球! XXX vs YYY: 
比赛进行到第30分钟，上半场第20分钟进1球后，至今未进第2球
```

✅ 触发提醒（正确）

---

#### 正确情况2: 第37分钟进1球

```
（无日志输出）
```

✅ 不触发提醒（正确）

---

#### 错误情况（修复前）: 第37分钟进1球

```
[监控引擎] ⚠️ 上半场仅1球! XXX vs YYY: 
比赛进行到第37分钟，上半场第37分钟进1球后，至今未进第2球
```

❌ 触发提醒（错误，已修复）

---

## 🎉 总结

### 问题根源

❌ 代码没有检查进球是否发生在设定的时间点之前  
❌ 只要当前进球数等于阈值，且当前时间超过设定时间，就触发提醒  
❌ 导致在设定时间之后进球也会触发提醒  

### 解决方案

✅ 新增状态字段 `first_half_reached_threshold_before_minute`  
✅ 记录进球时间时判断是否在 `threshold_minute` 之前  
✅ 触发提醒时检查是否在设定时间之前达到阈值  
✅ 同样修复下半场规则  

### 最终效果

- ✅ 逻辑正确：只在设定时间之前达到阈值时才触发提醒
- ✅ 避免误报：设定时间之后进球不会触发提醒
- ✅ 用户体验好：符合用户的预期行为
- ✅ 代码已通过语法检查

---

## 📌 注意事项

1. **状态字段的作用**
   - `first_half_reached_threshold_before_minute`: 标记是否在设定时间之前达到阈值
   - 只有这个字段为 `True` 时，才会触发提醒

2. **进球时间的记录**
   - 即使进球发生在设定时间之后，仍然会记录时间
   - 但会将 `first_half_reached_threshold_before_minute` 设为 `False`
   - 这样就不会触发提醒

3. **下半场规则的同步修复**
   - 下半场规则使用相同的逻辑
   - 新增 `second_half_reached_threshold_before_minute` 字段
   - 确保上下半场规则的一致性
