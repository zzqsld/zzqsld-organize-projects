#!/usr/bin/env python3
r"""
organize_projects.py

用途:
- 识别"项目文件夹"（项目根目录下有名为 "12" 的子文件夹）。
- 若找到项目则处理：根目录级别的文件（docx->pdf、6/7/8 重命名）以及在 12\开评标资料 下的 1..12 子文件夹做 7..18.pdf 的生成与移动（按你的规则）。
- 去掉 PNG -> PDF 处理与相关依赖。

说明:
- 保留 docx->pdf（docx2pdf 或 LibreOffice）和 PDF 合并（pypdf）逻辑。
- 脚本结束后仅对输出目录中的 PDF 去重（保留不带 (1) 的），不再检查是否齐全。
"""
from pathlib import Path
import argparse
import shutil
import sys
import subprocess
import hashlib
import zipfile
import tempfile
from typing import List, Set, Dict, Optional
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote, unquote

import requests

# optional imports
try:
    import docx2pdf
    _HAS_DOCX2PDF = True
except Exception:
    _HAS_DOCX2PDF = False

try:
    from pypdf import PdfWriter
    _HAS_PYPDF = True
except Exception:
    _HAS_PYPDF = False

# pypinyin for sorting by pinyin initial
try:
    from pypinyin import lazy_pinyin, Style
    _HAS_PYPINYIN = True
except Exception:
    _HAS_PYPINYIN = False

REQUIRED_SUBDIR = "12"
KAIPING_DIR_NAME = "开评标资料"  # look under 12\开评标资料 for 1..12
PROCESSED_SUFFIX = "_已处理"

MOVE_FILES_TO_OUTPUT = ["1.pdf", "6.pdf", "8.pdf"]
DOCX_TO_PDF = {"7.docx": "4.pdf"}  # convert 7.docx -> 4.pdf (rename)


# ----------------- 工具函数 -----------------


def has_chinese(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    parent = target.parent
    base = target.stem
    suffix = target.suffix
    i = 1
    while True:
        cand = parent / f"{base} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def move_file(src: Path, dst: Path, dry_run: bool = False):
    if not src.exists():
        print(f"[WARN] 源不存在，无法移动: {src}")
        return
    if dry_run:
        print(f"[DRY] Move: {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    t = unique_path(dst)
    shutil.move(str(src), str(t))
    print(f"[OK] Moved: {src} -> {t}")


def convert_docx_to_pdf(docx_path: Path, out_pdf_path: Path, dry_run: bool = False) -> bool:
    if dry_run:
        print(f"[DRY] Convert DOCX -> PDF: {docx_path} -> {out_pdf_path}")
        return True
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_DOCX2PDF:
        try:
            docx2pdf.convert(str(docx_path), str(out_pdf_path))
            return out_pdf_path.exists()
        except Exception as e:
            print(f"[WARN] docx2pdf 转换失败: {e}，尝试 LibreOffice...")
    try:
        cmd = ["soffice", "--headless", "--convert-to", "pdf", str(docx_path), "--outdir", str(out_pdf_path.parent)]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        generated = out_pdf_path.parent / (docx_path.stem + ".pdf")
        if generated.exists():
            if generated.resolve() != out_pdf_path.resolve():
                shutil.move(str(generated), str(out_pdf_path))
            return out_pdf_path.exists()
        else:
            print(f"[ERROR] LibreOffice 未生成预期 PDF: {generated}")
            return False
    except FileNotFoundError:
        print("[ERROR] LibreOffice (soffice) 未找到，且 docx2pdf 不可用，无法将 DOCX 转为 PDF。")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] LibreOffice 转换失败: {e}")
        return False


def merge_pdfs(pdf_paths: List[Path], out_pdf_path: Path, dry_run: bool = False) -> bool:
    if not _HAS_PYPDF:
        print("[ERROR] 未安装 pypdf，无法合并 PDF。请运行: pip install pypdf")
        return False
    if dry_run:
        print(f"[DRY] Merge PDFs -> {out_pdf_path}: {[str(p) for p in pdf_paths]}")
        return True
    try:
        writer = PdfWriter()
        for p in pdf_paths:
            if not p.exists():
                print(f"[ERROR] 待合并 PDF 不存在: {p}")
                writer.close()
                return False
            writer.append(str(p))
        out_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_pdf_path, "wb") as fout:
            writer.write(fout)
        writer.close()
        return out_pdf_path.exists()
    except Exception as e:
        print(f"[ERROR] 合并 PDF 失败: {e}")
        return False


def find_subfolders_1_to_12(base_dir: Path) -> List[str]:
    """
    在 base_dir 下（包含其子目录）查找名为 '1'..'12' 的目录，返回缺失名称列表。
    """
    found: Set[str] = set()
    if not base_dir or not base_dir.exists():
        return [str(i) for i in range(1, 13)]
    for d in base_dir.rglob("*"):
        if d.is_dir():
            name = d.name
            if name.isdigit():
                try:
                    n = int(name)
                    if 1 <= n <= 12:
                        found.add(name)
                except Exception:
                    pass
    missing = [str(i) for i in range(1, 13) if str(i) not in found]
    return missing


def calculate_md5(file_path: Path) -> str:
    """计算文件的 MD5 值"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"[ERROR] 计算 MD5 失败 {file_path}: {e}")
        return ""


def remove_duplicate_files(output_dir: Path, dry_run: bool = False):
    """
    仅对输出目录中的 PDF 做去重：
    - 若 MD5 相同，仅保留不带 (1) 等后缀者
    - 额外：若存在 “X.pdf” 和 “X (n).pdf”，无论 MD5 是否一致，一律删除 “X (n).pdf”
    """
    if not output_dir.exists():
        return
    
    print(f"\n[INFO] 检查重复文件: {output_dir}")
    md5_dict: Dict[str, List[Path]] = {}
    pdf_files = list(output_dir.glob("*.pdf"))
    for pdf_file in pdf_files:
        md5 = calculate_md5(pdf_file)
        if md5:
            md5_dict.setdefault(md5, []).append(pdf_file)
    
    deleted_count = 0
    for md5, files in md5_dict.items():
        if len(files) > 1:
            files_sorted = sorted(files, key=lambda f: (
                " (" in f.stem,
                f.stem.lower()
            ))
            keep_file = files_sorted[0]
            for dup in files_sorted[1:]:
                if dry_run:
                    print(f"  [DRY] 删除重复: {dup.name} (保留 {keep_file.name})")
                else:
                    try:
                        dup.unlink()
                        print(f"  [OK] 已删除重复: {dup.name}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"  [ERROR] 删除失败 {dup.name}: {e}")
    
    for pdf_file in output_dir.glob("* (*).pdf"):
        base_name = pdf_file.stem.rsplit(' (', 1)[0] + '.pdf'
        base_file = output_dir / base_name
        if base_file.exists():
            if dry_run:
                print(f"  [DRY] 删除带后缀文件: {pdf_file.name} (保留 {base_name})")
            else:
                try:
                    pdf_file.unlink()
                    print(f"  [OK] 已删除带后缀文件: {pdf_file.name}")
                    deleted_count += 1
                except Exception as e:
                    print(f"  [ERROR] 删除失败 {pdf_file.name}: {e}")
    
    if deleted_count > 0:
        print(f"[INFO] 共删除 {deleted_count} 个重复文件")
    else:
        print("[INFO] 未发现重复文件")


def extract_archive(archive_path: Path, dest_dir: Path) -> Path:
    """解压 zip 压缩包到 dest_dir 并返回作为 root 的目录。"""
    if not archive_path.exists() or not archive_path.is_file():
        raise FileNotFoundError(f"压缩包不存在: {archive_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)
    # 若解压后只有一个顶层目录，则返回该目录；否则返回 dest_dir 本身
    top_level_dirs = [p for p in dest_dir.iterdir() if p.is_dir()]
    if len(top_level_dirs) == 1:
        return top_level_dirs[0]
    return dest_dir


def zip_outputs(outputs: List[Path], zip_path: Path, dry_run: bool = False):
    """将所有项目的输出目录打包为 zip。"""
    if not outputs:
        print("[WARN] 没有可打包的输出目录，跳过压缩。")
        return
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"[DRY] Would zip outputs -> {zip_path} : {[str(o) for o in outputs]}")
        return
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for out_dir in outputs:
            if not out_dir.exists():
                print(f"[WARN] 输出目录不存在，跳过: {out_dir}")
                continue
            proj_label = out_dir.parent.name
            for file_path in out_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"{proj_label}/{file_path.relative_to(out_dir)}"
                    zf.write(file_path, arcname)
    print(f"[OK] 已生成压缩包: {zip_path}")


# ----------------- WebDAV 支持 -----------------


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else url + "/"


class WebDAVClient:
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None):
        self.base_url = _ensure_trailing_slash(base_url)
        self.auth = (username, password) if username or password else None

    def _build_url(self, remote_name: str) -> str:
        quoted = quote(remote_name)
        return urljoin(self.base_url, quoted)

    def list_archives(self, processed_suffix: str = PROCESSED_SUFFIX) -> List[str]:
        """列出 base_url 下的 zip 文件，过滤掉已处理标记。"""
        headers = {"Depth": "1", "Content-Type": "application/xml"}
        body = """<?xml version='1.0' encoding='utf-8'?>
<d:propfind xmlns:d='DAV:'>
  <d:allprop/>
</d:propfind>"""
        try:
            resp = requests.request("PROPFIND", self.base_url, data=body, headers=headers, auth=self.auth)
            resp.raise_for_status()
        except Exception as e:
            print(f"[ERROR] WebDAV 列表请求失败: {e}")
            return []

        try:
            root = ET.fromstring(resp.content)
        except Exception as e:
            print(f"[ERROR] 解析 WebDAV 列表响应失败: {e}")
            return []

        archives: List[str] = []
        for resp_el in root.findall(".//{DAV:}response"):
            href_el = resp_el.find("{DAV:}href")
            if href_el is None or not href_el.text:
                continue
            name = href_el.text
            name = name.rstrip("/")
            if not name:
                continue
            parts = name.split("/")
            if not parts:
                continue
            fname = unquote(parts[-1])
            if not fname or fname.endswith("/"):
                continue
            if fname.lower().endswith(".zip") and processed_suffix not in Path(fname).stem:
                archives.append(fname)
        return archives

    def download_file(self, remote_name: str, local_path: Path, dry_run: bool = False) -> bool:
        url = self._build_url(remote_name)
        if dry_run:
            print(f"[DRY] WebDAV 下载: {url} -> {local_path}")
            return True
        try:
            with requests.get(url, auth=self.auth, stream=True) as r:
                r.raise_for_status()
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            print(f"[OK] 已从 WebDAV 下载: {remote_name}")
            return True
        except Exception as e:
            print(f"[ERROR] 下载失败 {remote_name}: {e}")
            return False

    def upload_file(self, local_path: Path, remote_name: str, dry_run: bool = False) -> bool:
        url = self._build_url(remote_name)
        if dry_run:
            print(f"[DRY] WebDAV 上传: {local_path} -> {url}")
            return True
        try:
            with open(local_path, "rb") as f:
                resp = requests.put(url, data=f, auth=self.auth)
            resp.raise_for_status()
            print(f"[OK] 已上传到 WebDAV: {remote_name}")
            return True
        except Exception as e:
            print(f"[ERROR] 上传失败 {remote_name}: {e}")
            return False

    def delete_file(self, remote_name: str, dry_run: bool = False) -> bool:
        url = self._build_url(remote_name)
        if dry_run:
            print(f"[DRY] WebDAV 删除: {url}")
            return True
        try:
            resp = requests.request("DELETE", url, auth=self.auth)
            resp.raise_for_status()
            print(f"[OK] 已删除 WebDAV 文件: {remote_name}")
            return True
        except Exception as e:
            print(f"[ERROR] 删除失败 {remote_name}: {e}")
            return False


# ----------------- 拼音排序相关 -----------------


def get_first_chinese_char(s: str):
    for ch in s:
        if "\u4e00" <= ch <= "\u9fff":
            return ch
    return None


def pinyin_initial_of_first_chinese(s: str) -> str:
    """
    返回字符串中第一个汉字的拼音首字母（A-Z）。
    若无法得到首字母，则返回 '{'（在 ASCII 排序中位于 Z 之后，用于排到最后）。
    """
    ch = get_first_chinese_char(s or "")
    if not ch:
        return "{"
    if _HAS_PYPINYIN:
        try:
            initials = lazy_pinyin(ch, style=Style.FIRST_LETTER)
            if initials and initials[0]:
                c = initials[0][0].upper()
                if "A" <= c <= "Z":
                    return c
        except Exception:
            pass
    return "{"


def sort_dirs_by_pinyin(dirs: List[Path]) -> List[Path]:
    """
    按“姓名第一个汉字的拼音首字母”A→Z 排序；
    无法取到首字母（返回 '{'）的排在后面；同一首字母下按名称字典序。
    """
    if not dirs:
        return dirs

    def sort_key(p: Path):
        initial = pinyin_initial_of_first_chinese(p.name)
        return (initial, p.name)

    return sorted(dirs, key=sort_key)


# 辅助函数：安全获取编号子目录，存在则返回，不存在则返回 None
def get_sub_dir(base_dir: Path, n: int) -> Path:
    d = base_dir / str(n)
    return d if (d.exists() and d.is_dir()) else None


# ----------------- 处理单个项目 -----------------


def process_project(proj: Path, dry_run: bool = False, strict: bool = True):
    """
    proj 应该是项目根目录（即包含名为 REQUIRED_SUBDIR 的子文件夹）
    优先使用 proj/12/开评标资料 作为 base12_dir 查找 1..12。
    """
    print(f"\n--- 处理项目: {proj} ---")
    
    # 如果传入的是 12\开评标资料 路径，规范化为项目根
    proj_root = proj
    if proj.name == KAIPING_DIR_NAME:
        if proj.parent and proj.parent.name == REQUIRED_SUBDIR and proj.parent.parent:
            proj_root = proj.parent.parent
        else:
            proj_root = proj.parent or proj
    elif proj.name == REQUIRED_SUBDIR:
        proj_root = proj.parent or proj
    
    if proj_root != proj:
        print(f"[INFO] 已将路径规范为项目根: {proj_root}")
    proj = proj_root
    
    # 确定 base12_dir：优先 proj/12/开评标资料，其次 proj/12
    base12_candidate = proj / REQUIRED_SUBDIR / KAIPING_DIR_NAME
    if base12_candidate.exists() and base12_candidate.is_dir():
        base12_dir = base12_candidate
    else:
        base12_fallback = proj / REQUIRED_SUBDIR
        base12_dir = base12_fallback if base12_fallback.exists() and base12_fallback.is_dir() else None

    if base12_dir is None:
        print(f"[WARN] 项目中未找到 '{REQUIRED_SUBDIR}' 或 '{REQUIRED_SUBDIR}/{KAIPING_DIR_NAME}'，将以 proj/1 作为默认输出目录并仅执行根级处理。")
    else:
        print(f"[INFO] 使用 base12_dir: {base12_dir} 进行 1..12 检查与汇总（若存在）。")

    # 在 base12_dir 下查找 1..12
    missing_subs = find_subfolders_1_to_12(base12_dir) if base12_dir else [str(i) for i in range(1, 13)]
    has_all = (len(missing_subs) == 0)
    if base12_dir:
        if missing_subs:
            print(f"[WARN] 在 '12\\开评标资料' 中未找到以下编号文件夹: {missing_subs}，但仍将继续处理存在的文件夹。")
        else:
            print(f"[INFO] 在 '12\\开评标资料' 中已找到 1..12 的全部子文件夹。")

    # 决定输出目录：若 base12_dir 包含完整 1..12，使用 base12_dir/1 作为输出目录，否则 proj/1
    if has_all and base12_dir:
        output_dir = base12_dir / "1"
    else:
        output_dir = proj / "1"
    print(f"[INFO] 使用输出目录: {output_dir}")
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    tmpdir = proj / ".organize_tmp"
    if not dry_run:
        tmpdir.mkdir(parents=True, exist_ok=True)

    # 根目录处理：移动并按需求改名（6->2.pdf, 8->5.pdf, 1.pdf 保持）
    for name in MOVE_FILES_TO_OUTPUT:
        src = proj / name
        if not src.exists():
            print(f"[WARN] 未找到待移动文件: {src}")
            continue
        if name == "6.pdf":
            dst = output_dir / "2.pdf"
        elif name == "8.pdf":
            dst = output_dir / "5.pdf"
        else:
            dst = output_dir / name
        move_file(src, dst, dry_run=dry_run)

    # 7.docx -> 4.pdf
    docx_name = "7.docx"
    if (proj / docx_name).exists():
        out_pdf_tmp = tmpdir / DOCX_TO_PDF[docx_name]
        ok = convert_docx_to_pdf(proj / docx_name, out_pdf_tmp, dry_run=dry_run)
        if ok:
            dst = output_dir / out_pdf_tmp.name
            if dry_run:
                print(f"[DRY] Would move converted PDF {out_pdf_tmp} -> {dst}")
            else:
                if out_pdf_tmp.exists():
                    move_file(out_pdf_tmp, dst, dry_run=False)
                else:
                    alt = proj / (Path(docx_name).stem + ".pdf")
                    if alt.exists():
                        move_file(alt, dst, dry_run=False)
                    else:
                        print(f"[ERROR] 转换成功但未找到生成的 PDF (期望 {out_pdf_tmp} 或 {alt})")
        else:
            print(f"[ERROR] 无法将 {proj/docx_name} 转换为 PDF")

    # 提示：PNG -> PDF 已移除
    print("[NOTICE] PNG -> PDF 的自动处理已移除。如需对图片合并或转换，请先手动生成并放到输出目录。")

    # base12_dir 下按编号文件夹生成目标 PDF
    if base12_dir:
        def sub_dir(n: int) -> Path:
            return get_sub_dir(base12_dir, n)

        # 1号: 评标委员会成员签到表.pdf -> 7评标委员会成员签到表.pdf
        s1_dir = sub_dir(1)
        if s1_dir:
            s1 = s1_dir / "评标委员会成员签到表.pdf"
            if s1.exists():
                dst = output_dir / ("7" + s1.name)
                move_file(s1, dst, dry_run=dry_run)
            else:
                print(f"[WARN] 未在 {s1_dir} 找到 '评标委员会成员签到表.pdf'。")
        else:
            print(f"[WARN] 文件夹 {base12_dir / '1'} 不存在，跳过 1 号处理。")

        # 2号: 评标委员会声明书.pdf -> 8评标委员会声明书.pdf
        s2_dir = sub_dir(2)
        if s2_dir:
            s2 = s2_dir / "评标委员会声明书.pdf"
            if s2.exists():
                dst = output_dir / ("8" + s2.name)
                move_file(s2, dst, dry_run=dry_run)

        # 3号 -> 9.pdf（三位姓名的 PDF 按拼音首字母排序后依次放前，最后追加“初步评审标准及记录表.pdf”）
        f3 = sub_dir(3)
        if f3:
            chinese_dirs = [d for d in f3.iterdir() if d.is_dir() and has_chinese(d.name)]
            chinese_dirs_sorted = sort_dirs_by_pinyin(chinese_dirs)
            if len(chinese_dirs_sorted) >= 3:
                abc = chinese_dirs_sorted[:3]
                pdfs = []
                for d in abc:
                    pdf_list = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
                    if pdf_list:
                        pdfs.append(pdf_list[0])  # 顺序与 abc 一致（已是按拼音首字母 A→Z）
                prelim = f3 / "初步评审标准及记录表.pdf"
                if len(pdfs) == 3 and prelim.exists():
                    merged = [*pdfs, prelim]  # 先三份姓名 PDF，最后追加评审标准
                    out_tmp = tmpdir / "9.pdf"
                    ok = merge_pdfs(merged, out_tmp, dry_run=dry_run)
                    if ok:
                        dst = output_dir / "9.pdf"
                        if dry_run:
                            print(f"[DRY] Would move {out_tmp} -> {dst}")
                        else:
                            if out_tmp.exists():
                                move_file(out_tmp, dst, dry_run=False)
                else:
                    print(f"[WARN] {f3} 无法满足 9.pdf 的合并条件。")

        # 4号 -> 10.pdf（同理，最后追加“初步评审标准及记录表（其他情况）.pdf”）
        f4 = sub_dir(4)
        if f4:
            chinese_dirs_4 = [d for d in f4.iterdir() if d.is_dir() and has_chinese(d.name)]
            chinese_dirs_4_sorted = sort_dirs_by_pinyin(chinese_dirs_4)
            if len(chinese_dirs_4_sorted) >= 3:
                abc = chinese_dirs_4_sorted[:3]
                pdfs = []
                for d in abc:
                    pdf_list = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
                    if pdf_list:
                        pdfs.append(pdf_list[0])  # 顺序与 abc 一致
                prelim_other = f4 / "初步评审标准及记录表（其他情况）.pdf"
                if len(pdfs) == 3 and prelim_other.exists():
                    merged = [*pdfs, prelim_other]  # 不再与姓名文件一起排序
                    out_tmp = tmpdir / "10.pdf"
                    ok = merge_pdfs(merged, out_tmp, dry_run=dry_run)
                    if ok:
                        dst = output_dir / "10.pdf"
                        if dry_run:
                            print(f"[DRY] Would move {out_tmp} -> {dst}")
                        else:
                            if out_tmp.exists():
                                move_file(out_tmp, dst, dry_run=False)
                else:
                    print(f"[WARN] {f4} 无法满足 10.pdf 的合并条件。")

        # 5号 -> 11未通过初步评审等情况汇总表.pdf
        s5_dir = sub_dir(5)
        if s5_dir:
            s5 = s5_dir / "未通过初步评审等情况汇总表.pdf"
            if s5.exists():
                dst = output_dir / ("11" + s5.name)
                move_file(s5, dst, dry_run=dry_run)

        # 6/7/8 -> 12/13/14
        for idx, outname in ((6, "12.pdf"), (7, "13.pdf"), (8, "14.pdf")):
            f = sub_dir(idx)
            if f:
                chinese_dirs_n = [d for d in f.iterdir() if d.is_dir() and has_chinese(d.name)]
                chinese_dirs_n_sorted = sort_dirs_by_pinyin(chinese_dirs_n)
                if len(chinese_dirs_n_sorted) >= 3:
                    pdfs = []
                    for d in chinese_dirs_n_sorted[:3]:
                        pdf_list = [fp for fp in d.iterdir() if fp.is_file() and fp.suffix.lower() == ".pdf"]
                        if pdf_list:
                            pdfs.append(pdf_list[0])
                    if len(pdfs) == 3:
                        merged = pdfs  # 已按拼音首字母排序
                        out_tmp = tmpdir / outname
                        ok = merge_pdfs(merged, out_tmp, dry_run=dry_run)
                        if ok:
                            dst = output_dir / outname
                            if dry_run:
                                print(f"[DRY] Would move {out_tmp} -> {dst}")
                            else:
                                if out_tmp.exists():
                                    move_file(out_tmp, dst, dry_run=False)

        # 9->15, 10->16, 11->17, 12->18
        mapping_single = {
            9: ("投标报价得分汇总表.pdf", "15"),
            10: ("评分汇总及得分记录表.pdf", "16"),
            11: ("承包商排序表.pdf", "17"),
            12: ("评审报告.pdf", "18")
        }
        for idx, (fname, prefix) in mapping_single.items():
            srcf_dir = get_sub_dir(base12_dir, idx)
            if srcf_dir:
                srcf = srcf_dir / fname
                if srcf.exists():
                    dst = output_dir / (prefix + srcf.name)
                    move_file(srcf, dst, dry_run=dry_run)

    # 清理临时目录
    if not dry_run:
        try:
            if tmpdir.exists():
                shutil.rmtree(tmpdir)
                print(f"[INFO] 已删除临时目录: {tmpdir}")
        except Exception as e:
            print(f"[WARN] 删除临时目录失败: {e}")

    # 若 output 最初位于 base12_dir/1，需要把它移动/合并到项目根 proj/1
    if base12_dir and has_all:
        out_candidate = base12_dir / "1"
        dest_root_1 = proj / "1"
        if out_candidate.exists() and out_candidate.resolve() != dest_root_1.resolve():
            if dry_run:
                print(f"[DRY] Would move output directory {out_candidate} -> {dest_root_1}")
            else:
                if dest_root_1.exists():
                    for item in out_candidate.iterdir():
                        target = dest_root_1 / item.name
                        if item.is_dir():
                            if target.exists():
                                for child in item.rglob("*"):
                                    if child.is_file():
                                        rel = child.relative_to(item)
                                        dest_child = target / rel
                                        dest_child.parent.mkdir(parents=True, exist_ok=True)
                                        shutil.move(str(child), str(unique_path(dest_child)))
                            else:
                                shutil.move(str(item), str(target))
                        else:
                            shutil.move(str(item), str(unique_path(target)))
                    try:
                        shutil.rmtree(out_candidate)
                    except Exception:
                        pass
                    print(f"[INFO] 已合并 {out_candidate} 到已存在的 {dest_root_1}")
                else:
                    shutil.move(str(out_candidate), str(dest_root_1))
                    print(f"[OK] 已把输出目录移动到项目根: {dest_root_1}")

    print(f"--- 项目处理完成: {proj} ---\n")
    # 返回最终输出目录和项目路径，用于后续去重
    return (proj, proj / "1")


# ----------------- 发现并处理多个项目 -----------------


def find_project_roots(root: Path, recursive: bool = True) -> List[Path]:
    """
    返回要处理的项目根目录列表（每个项目根目录下应包含名为 '12' 的子文件夹）。
    查找策略：
      1) 如果 root 自身或其祖先包含名为 '12' 的子文件夹，则把该祖先目录作为项目根。
      2) 在 root 的子树中查找所有名为 '12' 的目录，把它们的父目录作为项目根。
    去重并排序返回。
    """
    roots: Set[Path] = set()

    # 1) 检查 root 与其祖先
    for anc in [root] + list(root.parents):
        if (anc / REQUIRED_SUBDIR).is_dir():
            roots.add(anc)

    # 2) 在子树中查找名为 '12' 的目录
    if recursive:
        for d in root.rglob(REQUIRED_SUBDIR):
            if d.is_dir():
                roots.add(d.parent)

    roots_list = sorted(list(roots))
    return roots_list


def find_and_process(root: Path, dry_run: bool = False, recursive: bool = True, strict: bool = True):
    project_roots = find_project_roots(root, recursive=recursive)
    if not project_roots:
        print("[INFO] 未找到任何符合条件的项目目录（没有发现名为 '12' 的子文件夹）。")
        return []
    print(f"[INFO] 找到 {len(project_roots)} 个项目根，准备逐个处理：")
    for p in project_roots:
        print(f"  - {p}")
    
    # 收集所有项目的输出目录
    project_outputs = []
    for proj in project_roots:
        result = process_project(proj, dry_run=dry_run, strict=strict)
        if result:
            project_outputs.append(result)
    
    # 后处理：仅删除输出目录中的重复 PDF（不再检查是否齐全）
    if not dry_run:
        print("\n" + "="*60)
        print("开始后处理：仅删除输出目录中的重复 PDF")
        print("="*60)
        
        for proj, output_dir in project_outputs:
            remove_duplicate_files(output_dir, dry_run=dry_run)
        
        print("\n" + "="*60)
        print("后处理完成")
        print("="*60)

    return project_outputs


def process_webdav_archives(
    webdav_url: str,
    username: Optional[str],
    password: Optional[str],
    delete_source: bool = False,
    dry_run: bool = False,
    recursive: bool = True,
    strict: bool = True,
):
    """拉取 WebDAV 目录下的 zip，批量处理并回传。"""
    client = WebDAVClient(webdav_url, username, password)
    archives = client.list_archives(processed_suffix=PROCESSED_SUFFIX)
    if not archives:
        print("[INFO] WebDAV 目录下未找到待处理的 zip（或仅有已处理标记）。")
        return

    print(f"[INFO] WebDAV 待处理压缩包: {archives}")
    for remote_name in archives:
        print(f"\n==== 处理远端压缩包: {remote_name} ====")
        with tempfile.TemporaryDirectory() as td:
            tmpdir = Path(td)
            local_archive = tmpdir / Path(remote_name).name
            ok = client.download_file(remote_name, local_archive, dry_run=dry_run)
            if not ok:
                continue

            if dry_run:
                print("[DRY] 跳过解压和处理，仅展示将执行的操作。")
                continue

            extracted_root = extract_archive(local_archive, tmpdir / "extracted")
            outputs = find_and_process(extracted_root, dry_run=dry_run, recursive=recursive, strict=strict)

            output_dirs = [pair[1] for pair in outputs if pair and len(pair) == 2]
            processed_name = f"{Path(remote_name).stem}{PROCESSED_SUFFIX}.zip"
            processed_local = tmpdir / processed_name
            zip_outputs(output_dirs, processed_local, dry_run=dry_run)

            if processed_local.exists():
                client.upload_file(processed_local, processed_name, dry_run=dry_run)

            if delete_source:
                client.delete_file(remote_name, dry_run=dry_run)


# ----------------- CLI -----------------


def main():
    parser = argparse.ArgumentParser(description="按规则整理项目文件夹（优先在 12\\开评标资料 下查找 1..12 并生成 7..18.pdf；中文名按拼音首字母排序）")
    parser.add_argument("--root", help="要扫描的根目录（文件夹）")
    parser.add_argument("--archive", help="项目压缩包（zip）。若指定，将自动解压并使用解压后的目录作为 root")
    parser.add_argument("--output-zip", help="将所有项目的输出目录打包为 zip 的路径，便于上传到 Release")
    parser.add_argument("--dry-run", action="store_true", help="预览操作，不写入磁盘")
    parser.add_argument("--no-recursive", dest="recursive", action="store_false", help="只检查 root 的第一层子目录")
    parser.add_argument("--non-strict", dest="strict", action="store_false", help="非严格模式（尽量处理）")
    parser.add_argument("--webdav-url", help="WebDAV 目录 URL（指向存放压缩包的目录，需以 / 结尾或为目录路径）")
    parser.add_argument("--webdav-username", help="WebDAV 用户名")
    parser.add_argument("--webdav-password", help="WebDAV 密码")
    parser.add_argument("--webdav-delete-source", action="store_true", help="上传处理结果后删除远端原始压缩包")
    args = parser.parse_args()

    if not args.root and not args.archive and not args.webdav_url:
        parser.error("必须指定 --root、--archive 或 --webdav-url 之一。")
    if (args.root or args.archive) and args.webdav_url:
        print("[INFO] 同时指定了本地/压缩包与 WebDAV，将优先处理 WebDAV。")

    if args.webdav_url:
        if args.output_zip:
            print("[WARN] WebDAV 模式会为每个压缩包自动生成并上传 <原名>_已处理.zip，本地 --output-zip 将被忽略。")
        process_webdav_archives(
            webdav_url=args.webdav_url,
            username=args.webdav_username,
            password=args.webdav_password,
            delete_source=args.webdav_delete_source,
            dry_run=args.dry_run,
            recursive=args.recursive,
            strict=args.strict,
        )
        return

    if args.root and args.archive:
        print("[INFO] 同时指定了 --root 和 --archive，将优先使用 --archive 解压后的目录作为 root。")

    temp_dir = None
    try:
        if args.archive:
            archive_path = Path(args.archive).expanduser().resolve()
            if not archive_path.exists() or not archive_path.is_file():
                print(f"错误：指定的压缩包不存在或不是文件: {archive_path}")
                sys.exit(1)
            temp_dir = tempfile.TemporaryDirectory()
            extracted_root = extract_archive(archive_path, Path(temp_dir.name))
            root = extracted_root.resolve()
            print(f"[INFO] 已解压压缩包，使用根目录: {root}")
        else:
            root = Path(args.root).expanduser().resolve()
    except Exception as e:
        print(f"错误：处理 root/archive 参数时发生异常: {e}")
        if temp_dir:
            temp_dir.cleanup()
        sys.exit(1)

    if not root.exists() or not root.is_dir():
        print(f"错误：指定的目录不存在或不是文件夹: {root}")
        if temp_dir:
            temp_dir.cleanup()
        sys.exit(1)

    if not _HAS_PYPINYIN:
        print("[WARN] 未检测到 pypinyin，中文名将按字典序排序。如需按拼音排序请安装：pip install pypinyin")

    print(f"开始扫描: {root} (dry_run={args.dry_run}, recursive={args.recursive}, strict={args.strict})")
    outputs = find_and_process(root, dry_run=args.dry_run, recursive=args.recursive, strict=args.strict)

    if args.output_zip:
        out_zip = Path(args.output_zip).expanduser().resolve()
        output_dirs = [pair[1] for pair in outputs if pair and len(pair) == 2]
        zip_outputs(output_dirs, out_zip, dry_run=args.dry_run)

    if temp_dir:
        temp_dir.cleanup()

    print("\n全部完成。")


if __name__ == "__main__":
    main()