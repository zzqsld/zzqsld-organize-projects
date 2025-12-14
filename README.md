# 项目整理与发布

该项目提供一个脚本用于批量整理“项目文件夹”，并支持在本地或通过 GitHub Actions 生成压缩包发布。

## 关键行为（与旧版差异）
- 识别“项目根”：只要目录下存在名为 `12` 的子文件夹，即视为项目根。
- 优先使用 `12/开评标资料` 作为基准目录；若该目录下存在 `1..12` 全部子文件夹，则在其中的 `1` 目录生成临时输出，最终会合并回项目根下的 `1`。
- 根级文件处理：将 `1.pdf`、`6.pdf`、`8.pdf` 移动到输出目录，其中 `6.pdf` 重命名为 `2.pdf`，`8.pdf` 重命名为 `5.pdf`。
- `7.docx -> 4.pdf`：先尝试 `docx2pdf`，失败则回退使用 LibreOffice（`soffice`）。
- 中文名排序：若安装 `pypinyin`，会按“第一个汉字的拼音首字母”进行 A→Z 排序；否则按字典序。
- PNG -> PDF 处理已移除：如需合并图片请手动生成 PDF 放入输出目录。
- 后处理仅做“输出目录中的 PDF 去重”：保留不带 `(n)` 的文件，删除重复 MD5 的带后缀文件；不再检查是否“齐全”。

## 本地运行
- 安装依赖：`pip install -r requirements.txt`
- 安装 LibreOffice 并确保 `soffice` 在 PATH 中；如已安装 `docx2pdf` 可优先使用（Windows/Mac 上体验更好）。
- 运行示例：
  - 扫描目录：`python organize_projects.py --root D:/path/to/projects`
  - 处理压缩包：`python organize_projects.py --archive D:/path/to/input.zip --output-zip D:/path/to/dist/output.zip`

## 常用参数
- `--archive`：提供 zip 压缩包路径，脚本会自动解压并用解压后的目录作为 root。
- `--root`：直接指定根目录（未压缩时使用）。
- `--output-zip`：将所有项目的输出目录再次压缩，顶层文件夹为各“项目根目录名”，便于发布。
- `--dry-run`：仅打印操作，不写磁盘。
- `--no-recursive`：只检查第一层子目录。
- `--non-strict`：非严格模式（尽量处理）。

## GitHub Actions（可选）
如需在 CI 中批量处理并发布：
- 将项目文件夹压缩为 zip（例如 `uploads/input.zip`）并推送到仓库（路径相对仓库根，推荐放在已建的 `uploads/` 目录，仓库里有 `.gitkeep` 占位）。
- 在 Actions 标签页触发 workflow，参数：
  - `archive_path`：压缩包相对路径，如 `input.zip` 或 `uploads/input.zip`。
  - `release_tag`：生成 Release 的标签，如 `auto-${{ github.run_number }}`。
- workflow 将安装 LibreOffice 与依赖，执行脚本，并把每个项目根下的 `1` 目录内容按“项目根目录名”为顶层打包为 `dist/YYYY-MM-DD项目.zip`，并发布到 Release。

## Release 内容
- `YYYY-MM-DD项目.zip`：包含每个项目根目录名作为顶层文件夹，其下为该项目 `1` 目录的所有生成 PDF（已做重复去重）。
