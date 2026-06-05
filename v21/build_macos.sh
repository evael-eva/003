#!/bin/bash
# macOS 本地打包测试脚本
# 使用方法: chmod +x build_macos.sh && ./build_macos.sh

echo "=========================================="
echo "  盘口监控邮件提醒 - macOS 打包测试"
echo "=========================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "盘口监控邮件提醒.py" ]; then
    echo "❌ 错误: 请在 v21 目录下运行此脚本"
    exit 1
fi

# 检查 Python
echo "📍 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "🔧 创建虚拟环境..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate
echo "✅ 虚拟环境已激活"
echo ""

# 安装依赖
echo "📦 安装依赖包..."
pip install --upgrade pip
pip install -r ../requirements.txt
echo "✅ 依赖安装完成"
echo ""

# 验证依赖
echo "🔍 验证依赖..."
python -c "import PyQt5; print('✅ PyQt5:', PyQt5.__version__)"
python -c "import DrissionPage; print('✅ DrissionPage installed')"
python -c "import requests; print('✅ requests:', requests.__version__)"
python -c "import bs4; print('✅ BeautifulSoup4:', bs4.__version__)"
echo ""

# 清理旧的构建
echo "🧹 清理旧的构建文件..."
rm -rf build dist
echo "✅ 清理完成"
echo ""

# 执行打包
echo "🚀 开始打包..."
pyinstaller --clean 盘口监控邮件提醒.spec

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 打包成功！"
    echo ""
    
    # 检查输出
    if [ -d "dist/盘口监控邮件提醒.app" ]; then
        echo "📦 应用包位置: dist/盘口监控邮件提醒.app"
        ls -lh dist/盘口监控邮件提醒.app
        echo ""
        
        # 询问是否创建 DMG
        read -p "是否创建 DMG 文件? (y/n): " create_dmg
        if [ "$create_dmg" = "y" ] || [ "$create_dmg" = "Y" ]; then
            echo "📀 创建 DMG..."
            hdiutil create -volname "盘口监控邮件提醒" \
                -srcfolder "dist/盘口监控邮件提醒.app" \
                -ov -format UDZO \
                "dist/盘口监控邮件提醒.dmg"
            
            if [ $? -eq 0 ]; then
                echo "✅ DMG 创建成功: dist/盘口监控邮件提醒.dmg"
                ls -lh dist/盘口监控邮件提醒.dmg
            else
                echo "❌ DMG 创建失败"
            fi
        fi
        
        echo ""
        echo "=========================================="
        echo "  🎉 打包完成！"
        echo "=========================================="
        echo ""
        echo "下一步："
        echo "1. 测试应用: open dist/盘口监控邮件提醒.app"
        echo "2. 上传到 GitHub 触发自动打包"
        echo ""
    else
        echo "❌ 错误: 未找到 .app 文件"
        exit 1
    fi
else
    echo ""
    echo "❌ 打包失败！请检查错误信息"
    exit 1
fi
