# organize-projects

## 项目简介
`organize-projects` 是一个用于识别和处理项目文件夹的Python工具。它能够自动转换和合并文件，简化项目管理流程。

## 功能
- 识别项目文件夹及其结构
- 将 `.docx` 文件转换为 `.pdf`
- 合并多个 PDF 文件
- 自动处理文件重命名和移动

## 安装
1. 克隆项目：
   ```
   git clone https://github.com/yourusername/organize-projects.git
   cd organize-projects
   ```

2. 创建虚拟环境并激活：
   ```
   python -m venv venv
   source venv/bin/activate  # 在 Windows 上使用 venv\Scripts\activate
   ```

3. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

## 使用
运行主脚本以处理项目文件夹：
```
python src/organize_projects/organize_projects.py --root <项目根目录>
```

## 贡献
欢迎任何形式的贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 以获取更多信息。

## 许可证
该项目采用 MIT 许可证，详细信息请查看 [LICENSE](LICENSE)。

### 在 GitHub 上创建新项目的步骤
1. 登录到你的 GitHub 账户。
2. 点击右上角的 "+" 按钮，然后选择 "New repository"。
3. 输入仓库名称（例如 `organize-projects`）。
4. 选择仓库的可见性（Public 或 Private）。
5. 点击 "Create repository" 按钮。
6. 按照页面上的说明将本地代码推送到新创建的 GitHub 仓库。