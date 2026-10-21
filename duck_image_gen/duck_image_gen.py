
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
icoolkj DuckAI 生图 GUI
依赖：pip install requests pillow

说明：
1. 使用 Duck.ai 非公开接口，接口可能随时变化。
2. HTTP 418 时读取并显示服务端错误，不尝试绕过访问限制。
3. 支持 SSE 解析、图片校验、后台线程和 GUI 预览。
"""

import base64
import json
import queue
import threading
import uuid
import sys
from pathlib import Path
from io import BytesIO
import tkinter as tk
from tkinter import ttk, messagebox

import requests
from PIL import Image, ImageTk


API_URL = "https://duck.ai/duckchat/v1/chat"

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
        "ddg_auth_session_id": "",
        "x_vqd_hash_1": ""
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


def save_config(config):
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def build_payload(prompt):
    """
    这里使用你原先抓包得到的请求结构。
    如果 Duck.ai 改变了协议，需要通过正常网页使用过程
    重新确认当前请求格式；此函数本身不能解除 HTTP 418。
    """
    return {
        "model": "gpt-6-luna",
        "metadata": {},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "canUseTools": True,
        "reasoningEffort": "none",
        "canUseApproxLocation": None,
        "canDelegateImageGeneration": None,
        "canShowGreeting": True,
        "durableStream": {
            "messageId": str(uuid.uuid4()),
            "conversationId": str(uuid.uuid4()),
            "publicKey": {
                "alg": "RSA-OAEP-256",
                "e": "AQAB",
                "ext": True,
                "key_ops": ["encrypt"],
                "kty": "RSA",
                "n": (
                    "vSJJsjz4lmFk3qbOjCe9uScBT5_CYSMEq0RoHq5HjIA"
                    "iabvkR08ZDzDiZ7tWV-dIkWfmOHt1qZj2-ij4Dot5aBAX"
                    "M8SBRBTW298n7xbQ0QpLdwxgZFkqNeczYSKKgzkMzxxpyh"
                    "RzHH4bsyERqv-g3Iavu08aZQ8StTTCwcDx38Nace1MvHOx"
                    "Wd2VBllUhekLw5Q0gG08-qOrGzGokC-uFZomr4IYE22fkFa"
                    "HfVL0BP12-i5GsIkzZBKgWYNjnivfc8KtvjoDSH2l0aQTz"
                    "-JTlT1D7Y2NrD5NnvpUGmX_qmcc5IVawH6L_AcBFwqjG-N"
                    "bm4Ey3HFoXMPfmOYYzarF5w"
                ),
                "use": "enc"
            }
        }
    }


def call_duck_generate(prompt, session_id, vqd_hash):
    payload = build_payload(prompt)

    headers = {
        "Content-Type": "application/json",
        "Cookie": f"ddg_auth_session_id={session_id}",
        "x-vqd-hash-1": vqd_hash,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        ),
        "Accept": "text/event-stream",
    }

    candidates = []

    try:
        with requests.post(
            API_URL,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(15, 180)
        ) as response:

            print("HTTP 状态码:", response.status_code)
            print(
                "Content-Type:",
                response.headers.get("Content-Type", "")
            )

            if response.status_code == 418:
                # 不打印 Cookie、验证令牌或完整请求头。
                body = response.text[:1500]
                raise RuntimeError(
                    "Duck.ai 返回 HTTP 418。\n\n"
                    "服务端拒绝了此次请求。这不是图片解析错误，"
                    "不能靠修改 Base64 处理代码解决。\n\n"
                    "请查看下面的响应正文，判断是否包含 "
                    "ERR_BN_LIMIT、访问限制或其他错误信息。\n\n"
                    f"响应正文（最多 1500 字符）：\n{body}"
                )

            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"HTTP {response.status_code}："
                    "服务端拒绝授权。请在正常网页中确认登录状态，"
                    "并检查会话参数是否仍有效。"
                )

            if response.status_code == 429:
                raise RuntimeError(
                    "HTTP 429：请求受到频率限制。"
                    "请停止重复请求，并遵循服务端提示。"
                )

            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode(
                    "utf-8", errors="replace"
                ).strip()

                if not line.startswith("data:"):
                    continue

                raw = line[len("data:"):].strip()

                if raw == "[DONE]":
                    break

                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if (
                    event.get("action") == "error"
                    or event.get("error")
                ):
                    raise RuntimeError(
                        "服务端事件错误："
                        + str(
                            event.get(
                                "error",
                                event.get("message", "未知错误")
                            )
                        )
                    )

                data = event.get("data")

                if not isinstance(data, dict):
                    continue

                if data.get("type") != "image-partial":
                    continue

                image_data = data.get("b64Image")

                if isinstance(image_data, str) and image_data:
                    candidates.append(image_data)

    except requests.Timeout as exc:
        raise RuntimeError(
            "请求超时。请检查网络连接及服务端状态。"
        ) from exc

    except requests.ConnectionError as exc:
        raise RuntimeError(
            "网络连接失败，请检查网络或服务地址。"
        ) from exc

    if not candidates:
        raise RuntimeError(
            "请求结束，但没有找到图片数据。"
            "请检查 SSE 事件及服务端返回信息。"
        )

    # 逐个验证图片候选；不直接假设最后一个事件是最终图片。
    candidates.sort(key=len, reverse=True)
    errors = []

    for candidate in candidates:
        try:
            image_bytes = base64.b64decode(
                candidate, validate=True
            )

            with Image.open(BytesIO(image_bytes)) as img:
                img.verify()

            # 确认数据可以再次解码，并取得图片格式。
            with Image.open(BytesIO(image_bytes)) as img:
                image_format = img.format

            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise RuntimeError(
                    f"不支持的图片格式：{image_format}"
                )

            return image_bytes, image_format

        except Exception as exc:
            errors.append(str(exc))

    raise RuntimeError(
        "已收到图片数据，但图片校验未通过："
        + "；".join(errors[:3])
    )


class DuckGenGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("icoolkj DuckAI 生图工具")
        self.root.geometry("760x780")
        self.root.minsize(600, 650)

        self.cfg = load_config()
        self.events = queue.Queue()
        self.img_tk = None

        self._build_ui()
        self.root.after(100, self._poll_events)

    def _build_ui(self):
        cfg_frame = ttk.LabelFrame(
            self.root, text="连接配置"
        )
        cfg_frame.pack(fill=tk.X, padx=10, pady=8)

        ttk.Label(
            cfg_frame, text="ddg_auth_session_id:"
        ).pack(anchor="w", padx=8, pady=(6, 0))

        self.var_session = tk.StringVar(
            value=self.cfg.get("ddg_auth_session_id", "")
        )
        ttk.Entry(
            cfg_frame, textvariable=self.var_session,
            show="*"
        ).pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(
            cfg_frame, text="x-vqd-hash-1:"
        ).pack(anchor="w", padx=8)

        self.var_vqd = tk.StringVar(
            value=self.cfg.get("x_vqd_hash_1", "")
        )
        ttk.Entry(
            cfg_frame, textvariable=self.var_vqd,
            show="*"
        ).pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(
            cfg_frame, text="保存配置",
            command=self.on_save_config
        ).pack(pady=6)

        ttk.Label(
            self.root, text="Prompt 提示词："
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self.prompt_text = tk.Text(
            self.root, height=7, wrap=tk.WORD
        )
        self.prompt_text.pack(
            fill=tk.X, padx=10
        )

        self.prompt_text.insert(
            "1.0",
            "为品牌 icoolkj 设计一张古典美学海报。"
            "采用米白宣纸、朱砂红、墨黑与少量古金，"
            "结合东方山水和现代品牌视觉，留白充足。"
        )

        self.gen_btn = ttk.Button(
            self.root,
            text="开始生成",
            command=self.on_generate
        )
        self.gen_btn.pack(pady=10)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(
            self.root, textvariable=self.status_var
        ).pack(pady=4)

        self.preview_label = ttk.Label(
            self.root, text="图片预览区域"
        )
        self.preview_label.pack(
            fill=tk.BOTH, expand=True, padx=10, pady=10
        )

    def on_save_config(self):
        self.cfg = {
            "ddg_auth_session_id": (
                self.var_session.get().strip()
            ),
            "x_vqd_hash_1": self.var_vqd.get().strip()
        }

        try:
            save_config(self.cfg)
            messagebox.showinfo("提示", "配置已保存。")
        except OSError as exc:
            messagebox.showerror(
                "保存失败", str(exc)
            )

    def on_generate(self):
        prompt = self.prompt_text.get(
            "1.0", tk.END
        ).strip()

        session_id = self.var_session.get().strip()
        vqd_hash = self.var_vqd.get().strip()

        if not prompt:
            messagebox.showwarning(
                "提示", "请输入提示词。"
            )
            return

        if not session_id or not vqd_hash:
            messagebox.showwarning(
                "提示", "请填写连接配置。"
            )
            return

        self.gen_btn.config(state=tk.DISABLED)
        self.status_var.set("正在请求服务端……")

        threading.Thread(
            target=self._generate_worker,
            args=(prompt, session_id, vqd_hash),
            daemon=True
        ).start()

    def _generate_worker(self, prompt, session_id, vqd_hash):
        try:
            image_bytes, image_format = call_duck_generate(
                prompt, session_id, vqd_hash
            )

            ext = {
                "JPEG": ".jpg",
                "PNG": ".png",
                "WEBP": ".webp"
            }[image_format]

            # 使用唯一文件名，避免覆盖已有图片。
            save_path = OUTPUT_DIR / (
                f"duck_gen_{uuid.uuid4().hex[:8]}{ext}"
            )

            save_path.write_bytes(image_bytes)

            with Image.open(BytesIO(image_bytes)) as img:
                img.load()
                img.thumbnail((680, 500))
                preview = img.copy()

            self.events.put(
                ("success", save_path, preview)
            )

        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self):
        try:
            while True:
                item = self.events.get_nowait()

                if item[0] == "success":
                    _, save_path, preview = item

                    self.img_tk = ImageTk.PhotoImage(
                        preview
                    )
                    self.preview_label.config(
                        image=self.img_tk, text=""
                    )
                    self.status_var.set(
                        f"生成完成：{save_path.name}"
                    )

                    messagebox.showinfo(
                        "完成",
                        f"图片已保存：\n{save_path}"
                    )

                elif item[0] == "error":
                    error_text = item[1]
                    self.status_var.set("生成失败")
                    messagebox.showerror(
                        "生成失败", error_text
                    )

                self.gen_btn.config(state=tk.NORMAL)

        except queue.Empty:
            pass

        self.root.after(100, self._poll_events)


if __name__ == "__main__":
    root = tk.Tk()
    app = DuckGenGUI(root)
    root.mainloop()
