# 项目整理与发布

该项目提供一个脚本用于批量整理“项目文件夹”，支持本地处理，也支持直接从 WebDAV 目录批量拉取 zip 处理后回传（适合大于 GitHub 25MB 限制的文件）。

## 关键行为（与旧版差异）
- 识别“项目根”：只要目录下存在名为 `12` 的子文件夹，即视为项目根。脚本会自动规范化路径，避免重复处理同一个项目。
- 优先使用 `12/开评标资料` 作为基准目录；若该目录下存在 `1..12` 全部子文件夹，则在其中的 `1` 目录生成临时输出，最终会合并回项目根下的 `1`。
- 根级文件处理：将 `1.pdf`、`6.pdf`、`8.pdf` 移动到输出目录，其中 `6.pdf` 重命名为 `2.pdf`，`8.pdf` 重命名为 `5.pdf`。
- **图片支持**：自动扫描项目根目录及 `12/开评标资料` 下的图片文件（.png, .jpg, .jpeg, .bmp, .tif, .tiff），并将其复制到输出目录。若文件名冲突，会自动重命名（如 `image (1).png`），并在后处理阶段进行智能去重。
- `7.docx -> 4.pdf`：先尝试 `docx2pdf`，失败则回退使用 LibreOffice（`soffice`）。
- 中文名排序：若安装 `pypinyin`，会按“第一个汉字的拼音首字母”进行 A→Z 排序；否则按字典序。
- PNG -> PDF 处理已移除：如需合并图片请手动生成 PDF 放入输出目录。
- **智能去重**：后处理阶段会检查输出目录中的 PDF 和图片文件。若内容相同（MD5一致），优先保留原名文件，删除带 `(n)` 后缀的副本；若存在 `X.ext` 和 `X (n).ext`，无论内容是否完全一致，也会优先保留 `X.ext`。

## 本地运行
- 安装依赖：`pip install -r requirements.txt`
- 安装 LibreOffice 并确保 `soffice` 在 PATH 中；如已安装 `docx2pdf` 可优先使用（Windows/Mac 上体验更好）。
- 运行示例：
  - 扫描目录：`python organize_projects.py --root D:/path/to/projects`
  - 处理压缩包：`python organize_projects.py --archive D:/path/to/input.zip --output-zip D:/path/to/dist/output.zip`

## WebDAV 自动处理（本地或 GitHub Actions）
- 场景：GitHub 不能上传超过 25MB 的大压缩包时，可把 zip 放到支持 WebDAV 的网盘目录。
- 运行示例：
  - `python organize_projects.py --webdav-url https://example.com/dav/projects/ --webdav-username your_user --webdav-password your_pass`
  - 可选：`--webdav-delete-source` 上传处理结果后删除远端原压缩包（默认保留）。
- 行为：
  - 脚本会列出该目录下的所有 `.zip`，忽略文件名包含 `_已处理` 的压缩包。
  - 逐个下载 -> 解压 -> 按规则生成输出 -> 将生成结果再压缩为 `<原名>_已处理.zip` 上传回 WebDAV。
  - `--dry-run` 仍会列出计划操作，但不会下载/上传/写盘。

### 在 GitHub Actions 中跑 WebDAV
- 设置仓库 Secrets：`WEBDAV_URL`（目录 URL，末尾带 `/`）、`WEBDAV_USERNAME`、`WEBDAV_PASSWORD`。
- 手动触发 `Process Projects` workflow（仓库自带），可选输入：`delete_source`（true/false，默认 false）。
- workflow 会调用脚本的 WebDAV 模式：批量拉取 `.zip`，生成 `<原名>_已处理.zip` 并回传 WebDAV，忽略已带 `_已处理` 的压缩包，不再依赖把 zip 提交到仓库或发布 Release。

## 常用参数
- `--archive`：提供 zip 压缩包路径，脚本会自动解压并用解压后的目录作为 root。
- `--root`：直接指定根目录（未压缩时使用）。
- `--output-zip`：将所有项目的输出目录再次压缩，顶层文件夹为各“项目根目录名”，便于发布。
- `--dry-run`：仅打印操作，不写磁盘。
- `--no-recursive`：只检查第一层子目录。
- `--non-strict`：非严格模式（尽量处理）。

## Release 内容（本地或自建流程）
- 你可以继续使用 `--output-zip` 本地生成 `YYYY-MM-DD项目.zip`，结构与原流程一致：顶层为“项目根目录名”，内容为生成的 `1` 目录。若使用 WebDAV 模式，会为每个输入包单独生成 `<原名>_已处理.zip`（Actions 版直接回传 WebDAV，不再发 Release）。
