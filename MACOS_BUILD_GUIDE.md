# macOS 打包指南

本文档说明如何使用 GitHub Actions 自动将 v21 程序打包为 macOS 可用的应用程序。

## 📦 打包方式

### 方式一：GitHub Actions 自动打包（推荐）

#### 前置条件
git config --global https.proxy http://127.0.0.1:10809
git remote add origin https://ghproxy.com/https://github.com/evael-eva/001.git
1. **代码已推送到 GitHub 仓库**
   ```bash
git config --global http.sslVerify false

   git remote remove origin
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/evael-eva/001.git
   git push -u origin main
   ```

2. **确保有以下文件**：
   - `.github/workflows/build-macos.yml` - GitHub Actions 工作流配置
   - `v21/盘口监控邮件提醒.spec` - PyInstaller 打包配置
   - `requirements.txt` - Python 依赖列表

#### 触发打包

有以下几种方式触发自动打包：

**1. 推送代码到主分支**
```bash
git push origin main
```

**2. 创建版本标签（会生成 Release）**
```bash
git tag v1.0.0
git push origin v1.0.0
```

**3. 手动触发（在 GitHub 页面操作）**
- 进入仓库 → Actions → Build macOS App
- 点击 "Run workflow" → 选择分支 → 点击 "Run workflow"

#### 查看打包进度

1. 进入 GitHub 仓库页面
2. 点击 "Actions" 标签
3. 找到 "Build macOS App" 工作流
4. 点击运行记录查看详细日志

#### 下载打包结果

**方式A：从 Artifacts 下载（适合测试）**
1. 在 Actions 页面找到成功的运行记录
2. 滚动到页面底部 "Artifacts" 部分
3. 点击 "macOS-Build" 下载
4. 解压后会得到：
   - `盘口监控邮件提醒.app` - macOS 应用程序
   - `盘口监控邮件提醒.dmg` - 磁盘映像文件（可选）

**方式B：从 Release 下载（适合发布）**
1. 创建标签后会自动生成 Release
2. 进入仓库 → Releases
3. 下载最新版本的 `.app` 或 `.dmg` 文件

---

### 方式二：本地手动打包

如果您想在本地 Mac 上打包，可以按照以下步骤操作：

#### 1. 安装依赖

```bash
# 进入项目目录
cd v21

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r ../requirements.txt
```

#### 2. 执行打包

```bash
# 使用 PyInstaller 打包
pyinstaller --clean 盘口监控邮件提醒.spec
```

#### 3. 查找输出文件

打包完成后，会在 `dist/` 目录下生成：
- `盘口监控邮件提醒.app` - macOS 应用程序包

#### 4. 创建 DMG（可选）

```bash
# 使用 hdiutil 创建 DMG
hdiutil create -volname "盘口监控邮件提醒" \
  -srcfolder "dist/盘口监控邮件提醒.app" \
  -ov -format UDZO \
  "dist/盘口监控邮件提醒.dmg"
```

---

## 🔧 配置说明

### 修改 Bundle ID

编辑 `v21/盘口监控邮件提醒.spec` 文件，修改第 119 行：

```python
bundle_identifier='com.yourcompany.oddsmonitor',  # 修改为您的Bundle ID
```

建议格式：`com.公司名.应用名`

例如：
- `com.mycompany.oddsmonitor`
- `com.tangcheng.oddsmonitor`

### 添加应用图标

1. 准备一个 `.icns` 格式的图标文件
2. 将图标文件放到 `v21/` 目录
3. 修改 `v21/盘口监控邮件提醒.spec` 第 113 行：

```python
icon='app.icns',  # 替换为您的图标文件名
```

### 修改版本号

编辑 `v21/盘口监控邮件提醒.spec` 文件：

```python
version='1.0.0',  # 修改版本号
info_plist={
    'CFBundleVersion': '1.0.0',           # 构建版本号
    'CFBundleShortVersionString': '1.0.0', # 显示版本号
    ...
}
```

---

## 📱 在 macOS 上运行

### 首次运行

由于应用未签名，macOS 可能会阻止运行。解决方法：

**方法1：右键打开**
1. 右键点击 `盘口监控邮件提醒.app`
2. 选择 "打开"
3. 在弹出的警告中点击 "打开"

**方法2：终端命令**
```bash
xattr -cr /path/to/盘口监控邮件提醒.app
```

**方法3：系统偏好设置**
1. 打开 "系统偏好设置" → "安全性与隐私"
2. 在 "通用" 标签页，点击 "仍要打开"

### 权限说明

应用可能需要以下权限：
- **网络访问**：获取盘口数据
- **通知**：发送提醒通知
- **声音**：播放报警声音

---

## 🐛 常见问题

### Q1: GitHub Actions 打包失败

**可能原因**：
- 依赖安装失败
- PyInstaller 配置错误
- 文件路径问题

**解决方法**：
1. 查看 Actions 日志，找到错误信息
2. 检查 `requirements.txt` 是否正确
3. 确保 `v21/盘口监控邮件提醒.py` 存在

### Q2: 打包后的应用无法启动

**可能原因**：
- 缺少依赖库
- PyQt5 兼容性问题
- DrissionPage 需要 Chrome

**解决方法**：
```bash
# 在本地测试打包
cd v21
pyinstaller --clean 盘口监控邮件提醒.spec

# 运行测试
./dist/盘口监控邮件提醒.app/Contents/MacOS/盘口监控邮件提醒
```

### Q3: 应用体积太大

**优化方法**：
1. 编辑 `.spec` 文件，在 `excludes` 中添加更多不需要的库
2. 启用 UPX 压缩（已默认启用）
3. 使用 `strip=True` 移除调试符号

### Q4: DMG 文件创建失败

**可能原因**：
- `.app` 文件不存在
- hdiutil 命令不可用

**解决方法**：
```bash
# 确认 .app 文件存在
ls -lh dist/盘口监控邮件提醒.app

# 手动创建 DMG
hdiutil create -volname "盘口监控邮件提醒" \
  -srcfolder "dist/盘口监控邮件提醒.app" \
  -ov -format UDZO \
  "dist/盘口监控邮件提醒.dmg"
```

---

## 📝 工作流程说明

GitHub Actions 工作流程 (`build-macos.yml`) 执行以下步骤：

1. **Checkout code** - 检出代码
2. **Set up Python** - 安装 Python 3.10
3. **Cache pip dependencies** - 缓存 pip 依赖（加速后续构建）
4. **Install dependencies** - 安装 Python 依赖包
5. **Verify installation** - 验证依赖安装成功
6. **Build with PyInstaller** - 使用 PyInstaller 打包
7. **List build output** - 列出打包输出文件
8. **Create DMG** - 创建 DMG 磁盘映像（可选）
9. **Upload artifacts** - 上传打包结果
10. **Create Release** - 如果是标签推送，创建 GitHub Release

---

## 🚀 快速开始

最简单的使用方式：

```bash
# 1. 推送代码到 GitHub
git push origin main

# 2. 等待 GitHub Actions 完成（约5-10分钟）

# 3. 在 Actions 页面下载 macOS-Build

# 4. 解压并运行 盘口监控邮件提醒.app
```

---

## 📞 技术支持

如遇到问题，请：
1. 查看 GitHub Actions 日志
2. 检查本地打包是否成功
3. 提交 Issue 并附上错误日志

---

**最后更新**: 2024-01-20
