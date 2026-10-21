#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
icoolkj Pollinations 生图 GUI
模式：GET 请求，支持 Bearer Key
填入Key：Header携带Authorization: Bearer xxx，中文友好
空Key：普通免费GET
"""
import json
import queue
import threading
import uuid
import sys
from pathlib import Path
from io import BytesIO
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import requests
from PIL import Image, ImageTk

BASE_URL = "https://gen.pollinations.ai/image"

APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

OUTPUT_DIR = APP_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_ROOT / "config.json"


def load_config():
    default = {
        "api_key": "",
        "model": "z-image-turbo",
        "width": 1024,
        "height": 1024,
        "seed": "0",
        "safe": True,
        "quality": "medium"
    }
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                default.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
    return default


def save_config(cfg):
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(cfg, ensure_ascii=False, indent=2, fp=f)


def call_pollinations_generate(prompt: str, api_key: str, model: str, width: int, height: int, seed: str, safe: bool, quality: str, log_queue):
    clean_prompt = " ".join(prompt.split())
    encoded_prompt = requests.utils.quote(clean_prompt, safe='')
    url = f"{BASE_URL}/{encoded_prompt}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "image/jpeg, image/png, image/svg+xml"
    }
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
        log_queue.put(f"[INFO] GET + Bearer Auth, model={model}, size={width}x{height}")
    else:
        log_queue.put(f"[INFO] 免费GET无密钥模式, model={model}, size={width}x{height}")

    params = {
        "model": model,
        "width": width,
        "height": height,
        "seed": seed,
        "safe": safe,
        "quality": quality
    }

    resp = requests.get(url, params=params, headers=headers, stream=True, timeout=(15, 180))
    log_queue.put(f"[HTTP] status_code: {resp.status_code}")

    if resp.status_code == 429:
        raise RuntimeError("HTTP 429：接口限流，请稍后重试。")
    if resp.status_code == 400:
        if api_key.strip():
            raise RuntimeError("HTTP 400：请求拒绝，检查密钥、参数或提示词。")
        else:
            raise RuntimeError("HTTP 400：免费模式触发风控，中文容易拦截，建议填入API Key。")
    resp.raise_for_status()

    img_bytes = resp.content
    if len(img_bytes) < 8000:
        raise RuntimeError("返回图片数据过小，生成失败。")
    with Image.open(BytesIO(img_bytes)) as img:
        img.verify()
    with Image.open(BytesIO(img_bytes)) as img:
        fmt = img.format
    if fmt not in ("JPEG", "PNG", "WEBP"):
        raise RuntimeError(f"不支持图片格式：{fmt}")
    log_queue.put(f"[SUCC] 图片校验成功，格式：{fmt}")
    return img_bytes, fmt


class PollinationsGenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("icoolkj Pollinations 生图工具 (GET+Bearer)")
        self.root.geometry("880x1000")
        self.root.minsize(680, 780)
        self.cfg = load_config()
        self.events = queue.Queue()
        self.log_queue = queue.Queue()
        self.img_tk = None
        self._build_ui()
        self.root.after(100, self._poll_events)
        self.root.after(100, self._poll_log)

    def _build_ui(self):
        # API Key
        key_frame = ttk.Frame(self.root)
        key_frame.pack(fill=tk.X, padx=10, pady=(6,0))
        ttk.Label(key_frame, text="API Key(pk_/sk_)：").grid(row=0, column=0, sticky="w")
        self.var_apikey = tk.StringVar(value=self.cfg["api_key"])
        ttk.Entry(key_frame, textvariable=self.var_apikey).grid(row=0, column=1, sticky="ew", padx=6)
        key_frame.columnconfigure(1, weight=1)

        cfg_frame = ttk.LabelFrame(self.root, text="生成参数")
        cfg_frame.pack(fill=tk.X, padx=10, pady=6)

        row = 0
        ttk.Label(cfg_frame, text="模型:").grid(row=row, column=0, padx=4, pady=4, sticky="w")
        self.var_model = tk.StringVar(value=self.cfg["model"])
        model_list = ["flux", "flux-realism", "z-image-turbo", "turbo"]
        cb_model = ttk.Combobox(cfg_frame, textvariable=self.var_model, values=model_list, state="readonly")
        cb_model.grid(row=row, column=1, padx=4, pady=4, sticky="ew")

        ttk.Label(cfg_frame, text="宽:").grid(row=row, column=2, padx=4, pady=4, sticky="w")
        self.var_w = tk.StringVar(value=str(self.cfg["width"]))
        ttk.Entry(cfg_frame, textvariable=self.var_w, width=8).grid(row=row, column=3, padx=4, pady=4)

        ttk.Label(cfg_frame, text="高:").grid(row=row, column=4, padx=4, pady=4, sticky="w")
        self.var_h = tk.StringVar(value=str(self.cfg["height"]))
        ttk.Entry(cfg_frame, textvariable=self.var_h, width=8).grid(row=row, column=5, padx=4, pady=4)

        row += 1
        ttk.Label(cfg_frame, text="Seed种子:").grid(row=row, column=0, padx=4, pady=4, sticky="w")
        self.var_seed = tk.StringVar(value=self.cfg["seed"])
        ttk.Entry(cfg_frame, textvariable=self.var_seed).grid(row=row, column=1, padx=4, pady=4, sticky="ew")

        ttk.Label(cfg_frame, text="质量:").grid(row=row, column=2, padx=4, pady=4, sticky="w")
        self.var_quality = tk.StringVar(value=self.cfg["quality"])
        quality_list = ["low", "medium", "high"]
        cb_quality = ttk.Combobox(cfg_frame, textvariable=self.var_quality, values=quality_list, state="readonly")
        cb_quality.grid(row=row, column=3, padx=4, pady=4)

        self.var_safe = tk.BooleanVar(value=self.cfg["safe"])
        ttk.Checkbutton(cfg_frame, text="safe", variable=self.var_safe).grid(row=row, column=4, padx=4, pady=4, sticky="w")

        ttk.Button(cfg_frame, text="保存参数", command=self.on_save_config).grid(row=row, column=5, padx=4, pady=4)
        cfg_frame.columnconfigure(1, weight=1)

        ttk.Label(self.root, text="Prompt 提示词（填入Key后支持中文，GET方式）").pack(anchor="w", padx=10, pady=(8, 2))
        self.prompt_text = tk.Text(self.root, height=6, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.X, padx=10)
        self.prompt_text.insert("1.0", "群山间美丽的日落")

        self.gen_btn = ttk.Button(self.root, text="开始生成", command=self.on_generate)
        self.gen_btn.pack(pady=6)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var).pack(pady=2)

        # 日志面板
        log_frame = ttk.LabelFrame(self.root, text="运行日志")
        log_frame.pack(fill=tk.X, padx=10, pady=4)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, wrap=tk.WORD)
        self.log_text.pack(fill=tk.X, padx=4, pady=4)
        self.log_text.configure(state=tk.DISABLED)

        self.preview_label = ttk.Label(self.root, text="图片预览区域")
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _add_log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _poll_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._add_log(line)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def on_save_config(self):
        try:
            w = int(self.var_w.get())
            h = int(self.var_h.get())
        except ValueError:
            messagebox.showerror("错误", "宽高必须是数字！")
            return
        self.cfg = {
            "api_key": self.var_apikey.get().strip(),
            "model": self.var_model.get(),
            "width": w,
            "height": h,
            "seed": self.var_seed.get().strip(),
            "safe": self.var_safe.get(),
            "quality": self.var_quality.get()
        }
        save_config(self.cfg)
        messagebox.showinfo("提示", "参数已保存。")

    def on_generate(self):
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入提示词！")
            return
        try:
            w = int(self.var_w.get())
            h = int(self.var_h.get())
        except ValueError:
            messagebox.showerror("参数错误", "宽、高必须是整数")
            return
        api_key = self.var_apikey.get().strip()
        model = self.var_model.get()
        seed = self.var_seed.get().strip()
        safe = self.var_safe.get()
        quality = self.var_quality.get()

        self.gen_btn.config(state=tk.DISABLED)
        self.status_var.set("正在请求 Pollinations 服务端……")
        self.log_queue.put(f"[USER] 提交prompt: {prompt[:80]}...")
        threading.Thread(
            target=self._worker,
            args=(prompt, api_key, model, w, h, seed, safe, quality),
            daemon=True
        ).start()

    def _worker(self, prompt, api_key, model, w, h, seed, safe, quality):
        try:
            img_bytes, fmt = call_pollinations_generate(prompt, api_key, model, w, h, seed, safe, quality, self.log_queue)
            ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
            save_path = OUTPUT_DIR / f"pollinations_gen_{uuid.uuid4().hex[:8]}{ext}"
            save_path.write_bytes(img_bytes)
            self.log_queue.put(f"[FILE] 文件已保存：{save_path.name}")
            with Image.open(BytesIO(img_bytes)) as im:
                im.load()
                im.thumbnail((680, 520))
                preview = im.copy()
            self.events.put(("ok", save_path, preview))
        except Exception as e:
            self.log_queue.put(f"[ERR] {str(e)}")
            self.events.put(("err", str(e)))

    def _poll_events(self):
        try:
            while True:
                item = self.events.get_nowait()
                if item[0] == "ok":
                    _, path, preview = item
                    self.img_tk = ImageTk.PhotoImage(preview)
                    self.preview_label.config(image=self.img_tk, text="")
                    self.status_var.set(f"✅ 完成：{path.name}")
                    messagebox.showinfo("完成", f"图片已保存：\n{path}")
                else:
                    err = item[1]
                    self.status_var.set("生成失败")
                    messagebox.showerror("生成失败", err)
                self.gen_btn.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


if __name__ == "__main__":
    root = tk.Tk()
    app = PollinationsGenGUI(root)
    root.mainloop()
