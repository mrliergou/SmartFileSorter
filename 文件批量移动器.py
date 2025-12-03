# -*- coding: utf-8 -*-
"""
文件批量移动器（增强版）
功能：
- 优先使用 PySimpleGUI，若不可用回退 Tkinter（均不可用则提示）
- 支持批量关键词输入（多种分隔符）
- 规则管理器：可添加/删除/上移/下移规则；规则中支持多个关键词以 | 分隔
- 规则建议（扫描文件名词频并建议）
- 当多条规则匹配时可交互选择目标
- 复制模式（保留原文件）可在主界面勾选
- 自动创建目标目录；重名自动重命名 (name(1).ext)
- 支持 --test 单元测试
"""

import os
import sys
import json
import shutil
import traceback
import tempfile
import re
from collections import Counter
from typing import List, Dict, Tuple

# -------------------- 配置 --------------------
def get_config_path(name: str = 'config.json') -> str:
    # 支持 PyInstaller 打包场景
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
    # routes as list of ordered rules: each rule {'pattern':'k1|k2', 'target':'subfolder'}
    'routes': [
        {'pattern': '试卷|卷子', 'target': '试卷'},
        {'pattern': '练习|作业', 'target': '练习'}
    ],
    'copy_mode': False
}

def load_config() -> Dict:
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cfg = DEFAULT_CONFIG.copy()
        # 合并常用字段
        for k in ['keywords', 'exts', 'recursive', 'copy_mode']:
            if k in data:
                cfg[k] = data[k]
        # 处理 routes 的不同存储格式
        routes = data.get('routes', None)
        if isinstance(routes, list):
            # 验证并采用
            newr = []
            for it in routes:
                if isinstance(it, dict) and 'pattern' in it and 'target' in it:
                    newr.append({'pattern': str(it['pattern']), 'target': str(it['target'])})
            if newr:
                cfg['routes'] = newr
        elif isinstance(routes, dict):
            # backward compatibility: dict -> list
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
    """
    返回匹配的规则列表（按规则顺序），元素为 (pattern, target)
    """
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

# -------------------- GUI 能力检测 --------------------
use_sg = False
try:
    import PySimpleGUI as sg  # type: ignore
    ok = all(hasattr(sg, item) for item in ['Text', 'Input', 'Listbox', 'Button', 'Window', 'Checkbox', 'FolderBrowse', 'Multiline'])
    use_sg = ok
    if ok:
        try:
            if hasattr(sg, 'theme'):
                sg.theme('LightBlue')
        except Exception:
            pass
except Exception:
    use_sg = False

def can_use_tkinter() -> bool:
    try:
        import tkinter  # type: ignore
        return True
    except Exception:
        return False

# -------------------- PySimpleGUI 实现 --------------------
if use_sg:
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

    def open_rule_manager_sg(cfg: Dict):
        layout = [
            [sg.Text('关键词（用 | 分隔多个关键词）'), sg.Input(key='RK', size=(30,1)), sg.Text('目标子文件夹'), sg.Input(key='RV', size=(30,1))],
            [sg.Button('添加规则'), sg.Button('删除规则'), sg.Button('上移'), sg.Button('下移'), sg.Button('建议规则')],
            [sg.Listbox(values=[f"{r['pattern']} -> {r['target']}" for r in cfg['routes']], key='RULIST', size=(80,10))],
            [sg.Button('关闭')]
        ]
        win = sg.Window('规则管理器', layout, modal=True)
        while True:
            ev, val = win.read()
            if ev in (None, '关闭'):
                break
            if ev == '添加规则':
                k = val.get('RK', '').strip()
                v = val.get('RV', '').strip()
                if k and v:
                    cfg['routes'].append({'pattern': k, 'target': v})
                    save_config(cfg)
                    win['RULIST'].update([f"{r['pattern']} -> {r['target']}" for r in cfg['routes']])
            if ev == '删除规则':
                sel = val.get('RULIST')
                if sel:
                    text = sel[0]
                    pattern = text.split('->')[0].strip()
                    idx = next((i for i, r in enumerate(cfg['routes']) if r['pattern'] == pattern), None)
                    if idx is not None:
                        del cfg['routes'][idx]
                        save_config(cfg)
                        win['RULIST'].update([f"{r['pattern']} -> {r['target']}" for r in cfg['routes']])
            if ev in ('上移', '下移'):
                sel = val.get('RULIST')
                if sel:
                    text = sel[0]
                    pattern = text.split('->')[0].strip()
                    idx = next((i for i, r in enumerate(cfg['routes']) if r['pattern'] == pattern), None)
                    if idx is not None:
                        if ev == '上移' and idx > 0:
                            cfg['routes'][idx-1], cfg['routes'][idx] = cfg['routes'][idx], cfg['routes'][idx-1]
                        if ev == '下移' and idx < len(cfg['routes'])-1:
                            cfg['routes'][idx+1], cfg['routes'][idx] = cfg['routes'][idx], cfg['routes'][idx+1]
                        save_config(cfg)
                        win['RULIST'].update([f"{r['pattern']} -> {r['target']}" for r in cfg['routes']])
            if ev == '建议规则':
                folder = sg.popup_get_folder('选择要分析的文件夹以生成规则建议')
                if folder:
                    top = suggest_rules_from_folder(folder, top_n=30)
                    sugg_layout = [
                        [sg.Text('建议关键词（按频率倒序）：')],
                        [sg.Listbox(values=[f"{k} ({c})" for k, c in top], key='SUGGLIST', size=(60,10))],
                        [sg.Button('采纳所选为规则'), sg.Button('关闭')]
                    ]
                    sw = sg.Window('建议规则', sugg_layout, modal=True)
                    while True:
                        sev, sval = sw.read()
                        if sev in (None, '关闭'):
                            break
                        if sev == '采纳所选为规则':
                            sel = sval.get('SUGGLIST')
                            if sel:
                                item = sel[0]
                                token = item.split(' (')[0]
                                cfg['routes'].append({'pattern': token, 'target': token})
                                save_config(cfg)
                                win['RULIST'].update([f"{r['pattern']} -> {r['target']}" for r in cfg['routes']])
                                sw.close()
                                sg.popup('已采纳并加入规则')
                                break
                    sw.close()
        win.close()

    def run_sg_gui():
        cfg = load_config()
        layout = [
            [sg.Text('源文件夹:'), sg.Input(key='SRC'), sg.FolderBrowse()],
            [sg.Text('基础目标文件夹:'), sg.Input(key='DST'), sg.FolderBrowse()],
            [sg.Text('文件类型:'), sg.Input(','.join(cfg['exts']), key='EXTS')],
            [sg.Checkbox('递归检测', default=cfg['recursive'], key='RECUR')],
            [sg.Checkbox('复制模式（不移动原文件）', default=cfg.get('copy_mode', False), key='COPYMODE')],
            [sg.Text('关键词（支持批量输入）：'), sg.Input(key='KW'), sg.Button('添加关键词'), sg.Button('清空关键词')],
            [sg.Listbox(values=cfg['keywords'], key='KWLIST', size=(40,4))],
            [sg.Button('打开规则管理器')],
            [sg.Button('扫描'), sg.Button('执行', button_color=('white','green')), sg.Button('退出')],
            [sg.Text('匹配文件:')],
            [sg.Listbox(values=[], key='FILES', size=(80,10))],
            [sg.Multiline('', key='LOG', size=(80,10), disabled=True)]
        ]
        win = sg.Window('文件批量移动器', layout, finalize=True)

        def log(msg: str):
            try:
                win['LOG'].update(str(msg) + "\n", append=True)
            except Exception:
                pass

        while True:
            ev, val = win.read()
            if ev in (None, '退出'):
                break

            if ev == '添加关键词':
                raw = val.get('KW', '')
                kws = parse_keywords(raw)
                if kws:
                    existing = cfg.get('keywords', [])
                    for k in kws:
                        if k not in existing:
                            existing.append(k)
                    cfg['keywords'] = existing
                    save_config(cfg)
                    win['KWLIST'].update(cfg['keywords'])
                    win['KW'].update('')
                    log(f'添加关键词: {kws}')

            if ev == '清空关键词':
                cfg['keywords'] = []
                save_config(cfg)
                win['KWLIST'].update([])
                log('关键词已清空')

            if ev == '打开规则管理器':
                open_rule_manager_sg(cfg)
                cfg = load_config()
                win['KWLIST'].update(cfg.get('keywords', []))
                log('规则已更新')

            if ev == '扫描':
                exts = normalize_exts(val.get('EXTS', ''))
                cfg['exts'] = exts
                cfg['recursive'] = val.get('RECUR', False)
                save_config(cfg)
                found = find_matching_files(val.get('SRC', ''), cfg.get('keywords', []), exts, cfg['recursive'])
                win['FILES'].update(found)
                log(f'找到 {len(found)} 个文件')

            if ev == '执行':
                base = val.get('DST', '')
                if not base:
                    sg.popup('请设定基础目标文件夹')
                    continue
                copy_mode = bool(val.get('COPYMODE', False))
                cfg['copy_mode'] = copy_mode
                save_config(cfg)
                files = win['FILES'].get_list_values()
                moved = 0
                for f in files:
                    fn = os.path.basename(f)
                    matches = match_routes_for_name(fn, cfg.get('routes', []))
                    chosen_target = None
                    if not matches:
                        chosen_target = base
                    elif len(matches) == 1:
                        chosen_target = matches[0][1]
                    else:
                        opts = [m[1] for m in matches]
                        msg = '检测到多个规则匹配:\\n'
                        for i, o in enumerate(opts, 1):
                            msg += f"{i}) {o}\\n"
                        msg += '\\n请输入要应用的序号（默认 1），或留空跳过此文件。'
                        choice = sg.popup_get_text(msg, '选择规则')
                        if choice is None or choice.strip() == '':
                            log(f'跳过: {f} (未选择规则)')
                            continue
                        try:
                            idx = int(choice.strip()) - 1
                            if 0 <= idx < len(opts):
                                chosen_target = opts[idx]
                            else:
                                log(f'无效序号，跳过: {f}')
                                continue
                        except Exception:
                            log(f'解析选择失败，跳过: {f}')
                            continue
                    dest = chosen_target if os.path.isabs(chosen_target) else os.path.join(base, chosen_target)
                    os.makedirs(dest, exist_ok=True)
                    try:
                        if copy_mode:
                            newp = safe_copy(f, dest)
                        else:
                            newp = safe_move(f, dest)
                        log(f'已处理: {f} -> {newp}')
                        moved += 1
                    except Exception as e:
                        log(f'处理失败: {f} -> {e}')
                log(f'完成: {moved} 个文件被处理')
        win.close()

# -------------------- Tkinter 实现（回退） --------------------
else:
    def run_tk_gui():
        try:
            import tkinter as tk  # type: ignore
            from tkinter import filedialog, messagebox, simpledialog  # type: ignore
        except Exception as e:
            print('Tkinter 不可用：', e)
            return

        cfg = load_config()
        root = tk.Tk()
        root.title('文件批量移动器 - Tk 回退')
        root.geometry('900x700')

        frm = tk.Frame(root)
        frm.pack(padx=8, pady=8, fill='x')

        tk.Label(frm, text='源文件夹：').grid(row=0, column=0, sticky='w')
        src_var = tk.StringVar()
        tk.Entry(frm, textvariable=src_var, width=60).grid(row=0, column=1)
        tk.Button(frm, text='浏览', command=lambda: src_var.set(filedialog.askdirectory())).grid(row=0, column=2)

        tk.Label(frm, text='目标文件夹：').grid(row=1, column=0, sticky='w')
        dst_var = tk.StringVar()
        tk.Entry(frm, textvariable=dst_var, width=60).grid(row=1, column=1)
        tk.Button(frm, text='浏览', command=lambda: dst_var.set(filedialog.askdirectory())).grid(row=1, column=2)

        exts_var = tk.StringVar(value=','.join(cfg['exts']))
        tk.Label(frm, text='文件类型：').grid(row=2, column=0, sticky='w')
        tk.Entry(frm, textvariable=exts_var, width=40).grid(row=2, column=1, columnspan=2, sticky='w')

        recur_var = tk.BooleanVar(value=cfg['recursive'])
        tk.Checkbutton(frm, text='递归检测', variable=recur_var).grid(row=3, column=1, sticky='w')

        copy_var = tk.BooleanVar(value=cfg.get('copy_mode', False))
        tk.Checkbutton(frm, text='复制模式（不移动原文件）', variable=copy_var).grid(row=3, column=2, sticky='w')

        tk.Label(frm, text='关键词：').grid(row=4, column=0, sticky='w')
        kw_var = tk.StringVar()
        tk.Entry(frm, textvariable=kw_var, width=40).grid(row=4, column=1, sticky='w')

        kw_listbox = tk.Listbox(root, height=4, width=80)
        kw_listbox.pack(padx=8, pady=4)
        for k in cfg.get('keywords', []):
            kw_listbox.insert('end', k)

        def add_kw():
            raw = kw_var.get()
            kws = parse_keywords(raw)
            if kws:
                existing = list(kw_listbox.get(0, 'end'))
                changed = False
                for k in kws:
                    if k not in existing:
                        existing.append(k)
                        changed = True
                if changed:
                    kw_listbox.delete(0, 'end')
                    for x in existing:
                        kw_listbox.insert('end', x)
                    cfg['keywords'] = existing
                    save_config(cfg)
                    kw_var.set('')

        def clear_kw():
            kw_listbox.delete(0, 'end')
            cfg['keywords'] = []
            save_config(cfg)

        btn_frame = tk.Frame(root)
        btn_frame.pack(padx=8, pady=4, fill='x')
        tk.Button(btn_frame, text='添加关键词', command=add_kw).pack(side='left')
        tk.Button(btn_frame, text='清空关键词', command=clear_kw).pack(side='left')

        files_listbox = tk.Listbox(root, height=10, width=120)
        files_listbox.pack(padx=8, pady=6)

        log_text = tk.Text(root, height=8, width=120)
        log_text.pack(padx=8, pady=4)
        log_text.config(state='disabled')

        def log(s: str):
            log_text.config(state='normal')
            log_text.insert('end', s + "\n")
            log_text.see('end')
            log_text.config(state='disabled')

        def scan_files(preview=False):
            src = src_var.get()
            exts = normalize_exts(exts_var.get())
            rec = bool(recur_var.get())
            kws = list(kw_listbox.get(0, 'end'))
            found = find_matching_files(src, kws, exts, rec)
            files_listbox.delete(0, 'end')
            for p in found:
                files_listbox.insert('end', p)
            log(f'找到 {len(found)} 个文件')
            if preview:
                for p in found[:50]:
                    log(p)

        def open_rule_manager_tk():
            win = tk.Toplevel(root)
            win.title('规则管理器')
            win.geometry('600x360')

            tk.Label(win, text='关键词（用 | 分隔多个关键词）').pack(anchor='w', padx=8, pady=4)
            rk_var = tk.StringVar()
            tk.Entry(win, textvariable=rk_var, width=40).pack(padx=8)
            tk.Label(win, text='目标子文件夹').pack(anchor='w', padx=8, pady=4)
            rv_var = tk.StringVar()
            tk.Entry(win, textvariable=rv_var, width=40).pack(padx=8)

            listbox = tk.Listbox(win, width=80, height=10)
            listbox.pack(padx=8, pady=6)
            def refresh_list():
                listbox.delete(0, 'end')
                for r in cfg['routes']:
                    listbox.insert('end', f"{r['pattern']} -> {r['target']}")
            refresh_list()

            def add_rule():
                k = rk_var.get().strip()
                v = rv_var.get().strip()
                if k and v:
                    cfg['routes'].append({'pattern': k, 'target': v})
                    save_config(cfg)
                    refresh_list()
            def del_rule():
                sel = listbox.curselection()
                if sel:
                    text = listbox.get(sel[0])
                    pattern = text.split('->')[0].strip()
                    idx = next((i for i, r in enumerate(cfg['routes']) if r['pattern'] == pattern), None)
                    if idx is not None:
                        del cfg['routes'][idx]
                        save_config(cfg)
                        refresh_list()
            def move_up():
                sel = listbox.curselection()
                if sel:
                    text = listbox.get(sel[0])
                    pattern = text.split('->')[0].strip()
                    idx = next((i for i, r in enumerate(cfg['routes']) if r['pattern'] == pattern), None)
                    if idx is not None and idx > 0:
                        cfg['routes'][idx-1], cfg['routes'][idx] = cfg['routes'][idx], cfg['routes'][idx-1]
                        save_config(cfg)
                        refresh_list()
            def move_down():
                sel = listbox.curselection()
                if sel:
                    text = listbox.get(sel[0])
                    pattern = text.split('->')[0].strip()
                    idx = next((i for i, r in enumerate(cfg['routes']) if r['pattern'] == pattern), None)
                    if idx is not None and idx < len(cfg['routes'])-1:
                        cfg['routes'][idx+1], cfg['routes'][idx] = cfg['routes'][idx], cfg['routes'][idx+1]
                        save_config(cfg)
                        refresh_list()

            btnf = tk.Frame(win)
            btnf.pack(pady=6)
            tk.Button(btnf, text='添加规则', command=add_rule).pack(side='left')
            tk.Button(btnf, text='删除规则', command=del_rule).pack(side='left')
            tk.Button(btnf, text='上移', command=move_up).pack(side='left')
            tk.Button(btnf, text='下移', command=move_down).pack(side='left')

            def suggest_rules():
                folder = filedialog.askdirectory(title='选择用于分析的文件夹')
                if folder:
                    tokens = []
                    for rootp, dirs, files in os.walk(folder):
                        for f in files:
                            name = os.path.splitext(f)[0]
                            parts = re.split(r'[^\w\u4e00-\u9fff]+', name)
                            for p in parts:
                                p = p.strip()
                                if len(p) >= 2:
                                    tokens.append(p)
                    cnt = Counter(tokens)
                    top = cnt.most_common(30)
                    pick = simpledialog.askstring('建议规则', '出现频率高的词示例:\\n' + '\\n'.join([f"{k} ({c})" for k, c in top[:20]]) + '\\n\\n请输入要采纳的关键词（用 | 分隔），或留空取消：')
                    if pick:
                        target = simpledialog.askstring('目标子文件夹', '为该关键词指定目标子文件夹名称：')
                        if target:
                            cfg['routes'].append({'pattern': pick.strip(), 'target': target.strip()})
                            save_config(cfg)
                            refresh_list()

            tk.Button(btnf, text='建议规则', command=suggest_rules).pack(side='left')

            tk.Button(win, text='关闭', command=win.destroy).pack(pady=6)

        def do_move():
            base = dst_var.get()
            if not base:
                messagebox.showwarning('错误', '请设定目标文件夹')
                return
            copy_mode = bool(copy_var.get())
            cfg['copy_mode'] = copy_mode
            save_config(cfg)
            found = list(files_listbox.get(0, 'end'))
            moved = 0
            for f in found:
                fn = os.path.basename(f)
                matches = match_routes_for_name(fn, cfg.get('routes', []))
                chosen_target = None
                if not matches:
                    chosen_target = base
                elif len(matches) == 1:
                    chosen_target = matches[0][1]
                else:
                    opts = [m[1] for m in matches]
                    prompt = '检测到多个规则匹配:\\n' + '\\n'.join([f"{i+1}) {o}" for i, o in enumerate(opts)]) + '\\n请输入要应用的序号（默认1），或留空跳过：'
                    choice = simpledialog.askstring('选择规则', prompt)
                    if not choice:
                        log(f'跳过: {f} (未选择规则)')
                        continue
                    try:
                        idx = int(choice.strip()) - 1
                        if 0 <= idx < len(opts):
                            chosen_target = opts[idx]
                        else:
                            log(f'无效序号，跳过: {f}')
                            continue
                    except Exception:
                        log(f'解析选择失败，跳过: {f}')
                        continue
                dest = chosen_target if os.path.isabs(chosen_target) else os.path.join(base, chosen_target)
                os.makedirs(dest, exist_ok=True)
                try:
                    if copy_mode:
                        new = safe_copy(f, dest)
                    else:
                        new = safe_move(f, dest)
                    log(f'已处理: {f} -> {new}')
                    moved += 1
                except Exception as e:
                    log(f'处理失败: {f} -> {e}')
            log(f'完成: {moved} 个文件被处理')

        scan_frame = tk.Frame(root)
        scan_frame.pack(padx=8, pady=4)
        tk.Button(scan_frame, text='扫描', command=lambda: scan_files(False)).pack(side='left')
        tk.Button(scan_frame, text='预览', command=lambda: scan_files(True)).pack(side='left')
        tk.Button(scan_frame, text='执行', command=do_move).pack(side='left')

        tk.Button(root, text='打开规则管理器', command=open_rule_manager_tk).pack(pady=6)

        root.mainloop()

# -------------------- 单元测试 --------------------
def run_tests():
    assert normalize_exts('pdf, txt ,.doc') == ['pdf', 'txt', 'doc']
    assert normalize_exts('') == []

    assert parse_keywords('试卷,练习 行测') == ['试卷', '练习', '行测']
    assert parse_keywords('  试卷；练习；测试 ') == ['试卷', '练习', '测试']
    assert parse_keywords('a|b/c,d') == ['a', 'b', 'c', 'd']

    routes = [{'pattern': '试卷|卷子', 'target': '试卷'}, {'pattern': '数量|count', 'target': '数量'}]
    assert match_routes_for_name('数学试卷2025.pdf', routes) == [('试卷|卷子', '试卷')]
    assert match_routes_for_name('数量练习.doc', routes) == [('数量|count', '数量')]
    routes2 = [{'pattern': '试卷|卷子', 'target': '试卷'}, {'pattern': '试卷|样题', 'target': '样题'}]
    m = match_routes_for_name('试卷_样题.pdf', routes2)
    assert len(m) >= 1

    with tempfile.TemporaryDirectory() as srcdir:
        with tempfile.TemporaryDirectory() as dstdir:
            f1 = os.path.join(srcdir, '行测_样题.pdf')
            f2 = os.path.join(srcdir, '数量题.doc')
            with open(f1, 'w', encoding='utf-8') as fh:
                fh.write('x')
            with open(f2, 'w', encoding='utf-8') as fh:
                fh.write('y')
            moved1 = safe_move(f1, os.path.join(dstdir, '行测'))
            assert os.path.exists(moved1)
            with open(f2, 'w', encoding='utf-8') as fh:
                fh.write('z')
            copied = safe_copy(f2, os.path.join(dstdir, '数量'))
            assert os.path.exists(copied)

    print('所有测试通过')

# -------------------- 入口 --------------------
if __name__ == '__main__':
    if '--test' in sys.argv:
        try:
            run_tests()
        except AssertionError as e:
            print('测试断言失败：', e)
            traceback.print_exc()
            sys.exit(2)
        except Exception as e:
            print('运行测试时出错：', e)
            traceback.print_exc()
            sys.exit(3)
        sys.exit(0)

    if use_sg:
        try:
            run_sg_gui()
        except Exception as e:
            print('运行 PySimpleGUI 出错，回退到 Tkinter：', e)
            traceback.print_exc()
            if can_use_tkinter():
                run_tk_gui()
            else:
                print('Tkinter 不可用，无法启动 GUI。')
    else:
        if can_use_tkinter():
            run_tk_gui()
        else:
            print('未检测到 PySimpleGUI 且 Tkinter 不可用，无法启动 GUI。')
            print('可运行: python 文件批量移动器.py --test 来运行单元测试或在有 GUI 的环境运行。')
