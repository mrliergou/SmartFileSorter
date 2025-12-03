# -*- coding: utf-8 -*-
"""
文件批量移动器（现代化版本）
功能：
- 使用 customtkinter 现代化UI
- 支持批量关键词输入（多种分隔符）
- 规则管理器：可添加/删除/上移/下移规则；规则中支持多个关键词以 | 分隔
- 规则建议（扫描文件名词频并建议）
- 当多条规则匹配时可交互选择目标
- 复制模式（保留原文件）可在主界面勾选
- 自动创建目标目录；重名自动重命名 (name(1).ext)
"""

import os
import sys
import json
import shutil
import re
from collections import Counter
from typing import List, Dict, Tuple
import customtkinter as ctk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image

# 设置外观模式和默认颜色主题
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# -------------------- 配置 --------------------
def get_config_path(name: str = 'config.json') -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), name)
    try:
        return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), name)
    except Exception:
        return os.path.join(os.getcwd(), name)

CONFIG_PATH = get_config_path()

DEFAULT_CONFIG: Dict = {
    'keywords': [],
    'exts': ['pdf', 'doc', 'docx', 'txt'],
    'recursive': True,
    'routes': [
        {'pattern': '试卷|卷子', 'target': '试卷'},
        {'pattern': '练习|作业', 'target': '练习'}
    ],
    'copy_mode': False,
    'auto_use_first_rule': True  # 多规则匹配时自动使用第一条规则
}

def load_config() -> Dict:
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cfg = DEFAULT_CONFIG.copy()
        for k in ['keywords', 'exts', 'recursive', 'copy_mode', 'auto_use_first_rule']:
            if k in data:
                cfg[k] = data[k]
        routes = data.get('routes', None)
        if isinstance(routes, list):
            newr = []
            for it in routes:
                if isinstance(it, dict) and 'pattern' in it and 'target' in it:
                    newr.append({'pattern': str(it['pattern']), 'target': str(it['target'])})
            if newr:
                cfg['routes'] = newr
        elif isinstance(routes, dict):
            cfg['routes'] = [{'pattern': k, 'target': v} for k, v in routes.items()]
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict) -> None:
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('保存配置失败：', e)

# -------------------- 工具函数 --------------------
def normalize_exts(extstr: str) -> List[str]:
    if not extstr:
        return []
    parts = re.split(r'[,，]+', extstr)
    return [p.strip().lstrip('.').lower() for p in parts if p.strip()]

def parse_keywords(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r'[ ,，;；/|\t\n]+', text.strip())
    seen = set()
    out = []
    for p in parts:
        k = p.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out

def file_matches(name: str, keywords: List[str], exts: List[str]) -> bool:
    low = name.lower()
    if exts:
        if not any(low.endswith('.' + e) for e in exts):
            return False
    if not keywords:
        return True
    return any(k.lower() in low for k in keywords)

def match_routes_for_name(name: str, routes: List[Dict]) -> List[Tuple[str, str]]:
    low = name.lower()
    matches = []
    for rule in routes:
        pattern = rule.get('pattern', '')
        target = rule.get('target', '')
        keys = [x.strip().lower() for x in str(pattern).split('|') if x.strip()]
        for k in keys:
            if k and k in low:
                matches.append((pattern, target))
                break
    return matches

def find_matching_files(folder: str, keywords: List[str], exts: List[str], recursive: bool) -> List[str]:
    found: List[str] = []
    if not folder or not os.path.isdir(folder):
        return found
    if recursive:
        for root, dirs, files in os.walk(folder):
            for f in files:
                if file_matches(f, keywords, exts):
                    found.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and file_matches(f, keywords, exts):
                found.append(full)
    return found

def safe_copy(src: str, dst_dir: str) -> str:
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.basename(src)
    target = os.path.join(dst_dir, base)
    if not os.path.exists(target):
        shutil.copy2(src, target)
        return target
    name, ext = os.path.splitext(base)
    i = 1
    while True:
        new = f"{name}({i}){ext}"
        nt = os.path.join(dst_dir, new)
        if not os.path.exists(nt):
            shutil.copy2(src, nt)
            return nt
        i += 1

def safe_move(src: str, dst_dir: str) -> str:
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.basename(src)
    target = os.path.join(dst_dir, base)
    if not os.path.exists(target):
        shutil.move(src, target)
        return target
    name, ext = os.path.splitext(base)
    i = 1
    while True:
        new = f"{name}({i}){ext}"
        nt = os.path.join(dst_dir, new)
        if not os.path.exists(nt):
            shutil.move(src, nt)
            return nt
        i += 1

def suggest_rules_from_folder(folder: str, top_n: int = 20) -> List[Tuple[str, int]]:
    tokens = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            name = os.path.splitext(f)[0]
            parts = re.split(r'[^\w\u4e00-\u9fff]+', name)
            for p in parts:
                p = p.strip()
                if len(p) >= 2:
                    tokens.append(p)
    cnt = Counter(tokens)
    return cnt.most_common(top_n)

# -------------------- 建议规则窗口 --------------------
class SuggestionWindow(ctk.CTkToplevel):
    def __init__(self, parent, cfg, suggestions):
        super().__init__(parent)
        self.cfg = cfg
        self.parent_window = parent
        self.suggestions = suggestions
        self.title("智能规则建议")
        self.geometry("700x600")

        # 说明标签
        info_label = ctk.CTkLabel(self, text="📊 根据文件名分析，以下是出现频率最高的关键词",
                                 font=("微软雅黑", 14, "bold"))
        info_label.pack(padx=20, pady=15)

        # 创建滚动框架
        scroll_frame = ctk.CTkScrollableFrame(self, width=650, height=400)
        scroll_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.selected_items = []
        self.checkboxes = []

        # 创建可选择的关键词列表
        for keyword, count in suggestions:
            item_frame = ctk.CTkFrame(scroll_frame)
            item_frame.pack(fill="x", padx=5, pady=3)

            var = ctk.BooleanVar()
            checkbox = ctk.CTkCheckBox(item_frame, text="", variable=var, width=30)
            checkbox.pack(side="left", padx=5)

            # 关键词标签（可复制）
            keyword_label = ctk.CTkLabel(item_frame, text=f"{keyword}",
                                        font=("微软雅黑", 12, "bold"),
                                        width=200, anchor="w")
            keyword_label.pack(side="left", padx=5)

            # 频率标签
            count_label = ctk.CTkLabel(item_frame, text=f"出现 {count} 次",
                                      text_color="gray", width=100)
            count_label.pack(side="left", padx=5)

            # 快速添加按钮
            add_btn = ctk.CTkButton(item_frame, text="快速添加", width=100,
                                   command=lambda k=keyword: self.quick_add_rule(k),
                                   fg_color="#2ecc71", hover_color="#27ae60")
            add_btn.pack(side="right", padx=5)

            self.checkboxes.append((var, keyword))

        # 底部按钮
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(padx=20, pady=15, fill="x")

        ctk.CTkButton(btn_frame, text="批量添加选中项", command=self.batch_add_rules,
                     width=150, height=35, fg_color="#3498db", hover_color="#2980b9",
                     font=("微软雅黑", 12, "bold")).pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text="全选", command=self.select_all,
                     width=80, height=35).pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text="取消全选", command=self.deselect_all,
                     width=80, height=35).pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text="关闭", command=self.destroy,
                     width=80, height=35, fg_color="#95a5a6", hover_color="#7f8c8d").pack(side="right", padx=5)

    def quick_add_rule(self, keyword):
        """快速添加单个规则"""
        target = simpledialog.askstring("目标文件夹",
                                       f"为关键词 '{keyword}' 指定目标子文件夹:\n(留空则使用关键词作为文件夹名)")
        if target is None:  # 用户取消
            return
        if not target.strip():
            target = keyword

        self.cfg['routes'].append({'pattern': keyword, 'target': target.strip()})
        save_config(self.cfg)

        if hasattr(self.parent_window, 'refresh_list'):
            self.parent_window.refresh_list()

        messagebox.showinfo("成功", f"已添加规则: {keyword} -> {target}")

    def batch_add_rules(self):
        """批量添加选中的规则"""
        selected = [(keyword, var.get()) for var, keyword in self.checkboxes if var.get()]

        if not selected:
            messagebox.showwarning("提示", "请至少选择一个关键词")
            return

        added_count = 0
        for keyword, _ in selected:
            # 默认使用关键词作为目标文件夹名
            self.cfg['routes'].append({'pattern': keyword, 'target': keyword})
            added_count += 1

        save_config(self.cfg)

        if hasattr(self.parent_window, 'refresh_list'):
            self.parent_window.refresh_list()

        messagebox.showinfo("成功", f"已批量添加 {added_count} 条规则")
        self.destroy()

    def select_all(self):
        for var, _ in self.checkboxes:
            var.set(True)

    def deselect_all(self):
        for var, _ in self.checkboxes:
            var.set(False)

# -------------------- 规则管理器窗口 --------------------
class RuleManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.title("规则管理器")
        self.geometry("800x600")

        # 输入框架
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(input_frame, text="关键词（用 | 分隔多个关键词）:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.pattern_entry = ctk.CTkEntry(input_frame, width=300)
        self.pattern_entry.grid(row=0, column=1, padx=5, pady=5)

        ctk.CTkLabel(input_frame, text="目标子文件夹:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.target_entry = ctk.CTkEntry(input_frame, width=300)
        self.target_entry.grid(row=1, column=1, padx=5, pady=5)

        # 按钮框架
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkButton(btn_frame, text="添加规则", command=self.add_rule, fg_color="#2ecc71", hover_color="#27ae60").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="删除规则", command=self.delete_rule, fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="上移", command=self.move_up, fg_color="#3498db", hover_color="#2980b9").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="下移", command=self.move_down, fg_color="#3498db", hover_color="#2980b9").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="建议规则", command=self.suggest_rules, fg_color="#9b59b6", hover_color="#8e44ad").pack(side="left", padx=5)

        # 规则列表
        list_frame = ctk.CTkFrame(self)
        list_frame.pack(padx=20, pady=10, fill="both", expand=True)

        ctk.CTkLabel(list_frame, text="当前规则列表:").pack(anchor="w", padx=5, pady=5)

        self.rule_textbox = ctk.CTkTextbox(list_frame, width=700, height=300)
        self.rule_textbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.refresh_list()

        # 关闭按钮
        ctk.CTkButton(self, text="关闭", command=self.destroy, fg_color="#95a5a6", hover_color="#7f8c8d").pack(pady=10)

    def refresh_list(self):
        self.rule_textbox.delete("1.0", "end")
        for i, r in enumerate(self.cfg['routes'], 1):
            self.rule_textbox.insert("end", f"{i}. {r['pattern']} -> {r['target']}\n")

    def add_rule(self):
        pattern = self.pattern_entry.get().strip()
        target = self.target_entry.get().strip()
        if pattern and target:
            self.cfg['routes'].append({'pattern': pattern, 'target': target})
            save_config(self.cfg)
            self.refresh_list()
            self.pattern_entry.delete(0, "end")
            self.target_entry.delete(0, "end")
            messagebox.showinfo("成功", "规则已添加")

    def delete_rule(self):
        try:
            selection = self.rule_textbox.get("sel.first", "sel.last").strip()
            if selection:
                idx = int(selection.split('.')[0]) - 1
                if 0 <= idx < len(self.cfg['routes']):
                    del self.cfg['routes'][idx]
                    save_config(self.cfg)
                    self.refresh_list()
                    messagebox.showinfo("成功", "规则已删除")
        except:
            messagebox.showwarning("提示", "请先选中要删除的规则")

    def move_up(self):
        try:
            selection = self.rule_textbox.get("sel.first", "sel.last").strip()
            if selection:
                idx = int(selection.split('.')[0]) - 1
                if idx > 0:
                    self.cfg['routes'][idx-1], self.cfg['routes'][idx] = self.cfg['routes'][idx], self.cfg['routes'][idx-1]
                    save_config(self.cfg)
                    self.refresh_list()
        except:
            messagebox.showwarning("提示", "请先选中要移动的规则")

    def move_down(self):
        try:
            selection = self.rule_textbox.get("sel.first", "sel.last").strip()
            if selection:
                idx = int(selection.split('.')[0]) - 1
                if idx < len(self.cfg['routes']) - 1:
                    self.cfg['routes'][idx+1], self.cfg['routes'][idx] = self.cfg['routes'][idx], self.cfg['routes'][idx+1]
                    save_config(self.cfg)
                    self.refresh_list()
        except:
            messagebox.showwarning("提示", "请先选中要移动的规则")

    def suggest_rules(self):
        folder = filedialog.askdirectory(title='选择要分析的文件夹')
        if folder:
            top = suggest_rules_from_folder(folder, top_n=30)
            if not top:
                messagebox.showinfo("提示", "未找到可建议的关键词")
                return

            # 创建建议窗口
            SuggestionWindow(self, self.cfg, top)

# -------------------- 主应用窗口 --------------------
class FileManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_config()
        self.title("文件批量移动器 - 现代版")
        self.geometry("1000x800")

        # 设置图标（如果存在）
        try:
            icon_path = get_config_path('icon.ico')
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except:
            pass

        # 创建主框架
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        # 源文件夹
        src_frame = ctk.CTkFrame(main_frame)
        src_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(src_frame, text="源文件夹:", width=100).pack(side="left", padx=5)
        self.src_entry = ctk.CTkEntry(src_frame, width=500)
        self.src_entry.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(src_frame, text="浏览", command=self.browse_src, width=80).pack(side="left", padx=5)

        # 目标文件夹
        dst_frame = ctk.CTkFrame(main_frame)
        dst_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(dst_frame, text="目标文件夹:", width=100).pack(side="left", padx=5)
        self.dst_entry = ctk.CTkEntry(dst_frame, width=500)
        self.dst_entry.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(dst_frame, text="浏览", command=self.browse_dst, width=80).pack(side="left", padx=5)

        # 文件类型和选项
        options_frame = ctk.CTkFrame(main_frame)
        options_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(options_frame, text="文件类型:", width=100).pack(side="left", padx=5)
        self.exts_entry = ctk.CTkEntry(options_frame, width=200)
        self.exts_entry.insert(0, ','.join(self.cfg['exts']))
        self.exts_entry.pack(side="left", padx=5)

        self.recursive_var = ctk.BooleanVar(value=self.cfg['recursive'])
        ctk.CTkCheckBox(options_frame, text="递归检测", variable=self.recursive_var).pack(side="left", padx=10)

        self.copy_mode_var = ctk.BooleanVar(value=self.cfg.get('copy_mode', False))
        ctk.CTkCheckBox(options_frame, text="复制模式", variable=self.copy_mode_var).pack(side="left", padx=10)

        self.auto_rule_var = ctk.BooleanVar(value=self.cfg.get('auto_use_first_rule', True))
        ctk.CTkCheckBox(options_frame, text="智能模式(自动使用首个匹配规则)",
                       variable=self.auto_rule_var).pack(side="left", padx=10)

        # 关键词输入
        kw_frame = ctk.CTkFrame(main_frame)
        kw_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(kw_frame, text="关键词:", width=100).pack(side="left", padx=5)
        self.kw_entry = ctk.CTkEntry(kw_frame, width=400)
        self.kw_entry.pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(kw_frame, text="添加", command=self.add_keyword, width=80, fg_color="#2ecc71", hover_color="#27ae60").pack(side="left", padx=5)
        ctk.CTkButton(kw_frame, text="清空", command=self.clear_keywords, width=80, fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", padx=5)

        # 关键词列表
        kw_list_frame = ctk.CTkFrame(main_frame)
        kw_list_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(kw_list_frame, text="当前关键词:").pack(anchor="w", padx=5)
        self.kw_textbox = ctk.CTkTextbox(kw_list_frame, height=60)
        self.kw_textbox.pack(padx=5, pady=5, fill="x")
        self.refresh_keywords()

        # 操作按钮
        action_frame = ctk.CTkFrame(main_frame)
        action_frame.pack(padx=10, pady=15, fill="x")
        ctk.CTkButton(action_frame, text="扫描文件", command=self.scan_files, width=120, height=40,
                     fg_color="#3498db", hover_color="#2980b9", font=("微软雅黑", 14, "bold")).pack(side="left", padx=10)
        ctk.CTkButton(action_frame, text="执行移动/复制", command=self.execute_move, width=150, height=40,
                     fg_color="#2ecc71", hover_color="#27ae60", font=("微软雅黑", 14, "bold")).pack(side="left", padx=10)
        ctk.CTkButton(action_frame, text="规则管理器", command=self.open_rule_manager, width=120, height=40,
                     fg_color="#9b59b6", hover_color="#8e44ad", font=("微软雅黑", 14, "bold")).pack(side="left", padx=10)

        # 文件列表
        files_frame = ctk.CTkFrame(main_frame)
        files_frame.pack(padx=10, pady=10, fill="both", expand=True)
        ctk.CTkLabel(files_frame, text="匹配的文件:").pack(anchor="w", padx=5)
        self.files_textbox = ctk.CTkTextbox(files_frame, height=200)
        self.files_textbox.pack(padx=5, pady=5, fill="both", expand=True)

        # 日志
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        ctk.CTkLabel(log_frame, text="操作日志:").pack(anchor="w", padx=5)
        self.log_textbox = ctk.CTkTextbox(log_frame, height=150)
        self.log_textbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.matched_files = []

    def browse_src(self):
        folder = filedialog.askdirectory(title="选择源文件夹")
        if folder:
            self.src_entry.delete(0, "end")
            self.src_entry.insert(0, folder)

    def browse_dst(self):
        folder = filedialog.askdirectory(title="选择目标文件夹")
        if folder:
            self.dst_entry.delete(0, "end")
            self.dst_entry.insert(0, folder)

    def add_keyword(self):
        raw = self.kw_entry.get()
        kws = parse_keywords(raw)
        if kws:
            existing = self.cfg.get('keywords', [])
            for k in kws:
                if k not in existing:
                    existing.append(k)
            self.cfg['keywords'] = existing
            save_config(self.cfg)
            self.refresh_keywords()
            self.kw_entry.delete(0, "end")
            self.log(f'添加关键词: {", ".join(kws)}')

    def clear_keywords(self):
        self.cfg['keywords'] = []
        save_config(self.cfg)
        self.refresh_keywords()
        self.log('关键词已清空')

    def refresh_keywords(self):
        self.kw_textbox.delete("1.0", "end")
        if self.cfg.get('keywords'):
            self.kw_textbox.insert("1.0", ", ".join(self.cfg['keywords']))

    def open_rule_manager(self):
        RuleManagerWindow(self, self.cfg)

    def scan_files(self):
        src = self.src_entry.get()
        if not src:
            messagebox.showwarning("警告", "请选择源文件夹")
            return

        exts = normalize_exts(self.exts_entry.get())
        self.cfg['exts'] = exts
        self.cfg['recursive'] = self.recursive_var.get()
        save_config(self.cfg)

        self.matched_files = find_matching_files(src, self.cfg.get('keywords', []), exts, self.cfg['recursive'])

        self.files_textbox.delete("1.0", "end")
        for f in self.matched_files:
            self.files_textbox.insert("end", f + "\n")

        self.log(f'扫描完成: 找到 {len(self.matched_files)} 个匹配文件')

    def execute_move(self):
        base = self.dst_entry.get()
        if not base:
            messagebox.showwarning("警告", "请选择目标文件夹")
            return

        if not self.matched_files:
            messagebox.showwarning("警告", "请先扫描文件")
            return

        copy_mode = self.copy_mode_var.get()
        auto_use_first = self.auto_rule_var.get()
        self.cfg['copy_mode'] = copy_mode
        self.cfg['auto_use_first_rule'] = auto_use_first
        save_config(self.cfg)

        # 智能分组：将文件按匹配情况分组
        no_match_files = []  # 无匹配规则的文件
        single_match_files = []  # 单一匹配的文件
        multi_match_files = []  # 多规则匹配的文件

        for f in self.matched_files:
            fn = os.path.basename(f)
            matches = match_routes_for_name(fn, self.cfg.get('routes', []))

            if not matches:
                no_match_files.append((f, base))
            elif len(matches) == 1:
                single_match_files.append((f, matches[0][1]))
            else:
                multi_match_files.append((f, matches))

        # 显示处理预览
        total = len(self.matched_files)
        self.log(f'\n📊 文件分析完成:')
        self.log(f'  - 总文件数: {total}')
        self.log(f'  - 无匹配规则: {len(no_match_files)} 个 (将移至根目录)')
        self.log(f'  - 单一匹配: {len(single_match_files)} 个')
        self.log(f'  - 多规则匹配: {len(multi_match_files)} 个')

        # 处理多规则匹配的文件
        if multi_match_files:
            if auto_use_first:
                self.log(f'\n🤖 智能模式: 多规则匹配文件将自动使用第一条匹配规则')
                for f, matches in multi_match_files:
                    single_match_files.append((f, matches[0][1]))
            else:
                # 批量处理模式：一次性展示所有冲突
                self.log(f'\n⚠️ 检测到 {len(multi_match_files)} 个文件有多个匹配规则')
                result = messagebox.askyesnocancel(
                    "多规则匹配处理",
                    f"检测到 {len(multi_match_files)} 个文件匹配多条规则\n\n"
                    f"• 点击【是】: 全部使用第一条匹配规则\n"
                    f"• 点击【否】: 跳过这些文件\n"
                    f"• 点击【取消】: 中止操作"
                )

                if result is None:  # 取消
                    self.log('❌ 操作已取消')
                    return
                elif result:  # 是 - 使用第一条规则
                    for f, matches in multi_match_files:
                        single_match_files.append((f, matches[0][1]))
                    self.log('✓ 多规则文件将使用第一条匹配规则')
                else:  # 否 - 跳过
                    self.log(f'⊘ 已跳过 {len(multi_match_files)} 个多规则匹配文件')

        # 确认执行
        action_text = "复制" if copy_mode else "移动"
        confirm = messagebox.askyesno(
            "确认执行",
            f"准备{action_text} {len(no_match_files) + len(single_match_files)} 个文件\n\n"
            f"是否继续？"
        )

        if not confirm:
            self.log('❌ 操作已取消')
            return

        # 执行文件处理
        self.log(f'\n🚀 开始{action_text}文件...')
        moved = 0
        failed = 0

        all_files_to_process = no_match_files + single_match_files

        for f, target in all_files_to_process:
            fn = os.path.basename(f)
            dest = target if os.path.isabs(target) else os.path.join(base, target)
            os.makedirs(dest, exist_ok=True)

            try:
                if copy_mode:
                    new = safe_copy(f, dest)
                    self.log(f'✓ 已复制: {fn} -> {os.path.basename(dest)}/')
                else:
                    new = safe_move(f, dest)
                    self.log(f'✓ 已移动: {fn} -> {os.path.basename(dest)}/')
                moved += 1
            except Exception as e:
                self.log(f'✗ 失败: {fn} -> {str(e)}')
                failed += 1

        # 完成总结
        self.log(f'\n{"="*50}')
        self.log(f'🎉 处理完成!')
        self.log(f'  ✓ 成功: {moved} 个文件')
        if failed > 0:
            self.log(f'  ✗ 失败: {failed} 个文件')
        self.log(f'{"="*50}\n')

        messagebox.showinfo("完成", f"成功处理 {moved} 个文件" + (f"\n失败 {failed} 个" if failed > 0 else ""))

    def log(self, msg: str):
        self.log_textbox.insert("end", msg + "\n")
        self.log_textbox.see("end")

# -------------------- 入口 --------------------
if __name__ == '__main__':
    app = FileManagerApp()
    app.mainloop()
