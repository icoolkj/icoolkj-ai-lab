#!/usr/bin/env python3
"""
icoolkj AI研究实验室
FishAudio TTS + Windows本地TTS 图形化工具
官网：icoolkj.com
邮箱：icoolkj@163.com
QQ邮箱：594047667@qq.com
版本：v1.0.0
"""
from __future__ import annotations

__VERSION__ = "v1.0.0"

import base64
import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox


def fish_audio_tts(text: str, output_path: Path, *, api_key: str, voice_id: str, max_retries: int = 3) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": text,
        "reference_id": voice_id,
        "format": "mp3",
        "normalize": True,
    }
    last_error = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            "https://api.fish.audio/v1/tts",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "model": "s2.1-pro-free",
                "User-Agent": "tts_gui_tool/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            raise RuntimeError(f"Fish Audio HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"[RETRY] Fish Audio attempt {attempt+1} failed ({exc}), retrying in {wait}s...")
                time.sleep(wait)
            continue
        if not data.startswith(b"ID3") and not data.startswith(b"\xff\xfb"):
            last_error = RuntimeError(f"Fish Audio返回非音频数据: {data[:200].decode('utf-8', 'ignore')}")
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise last_error
        output_path.write_bytes(data)
        return output_path
    raise RuntimeError(f"Fish Audio {max_retries}次重试全部失败: {last_error}")


def windows_tts(text: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wav_path = output_path.with_suffix(".wav")
    safe_text = text.replace("'", "''")
    text_b64 = base64.b64encode(safe_text.encode("utf-8")).decode("ascii")

    # 优先尝试 Huihui；找不到则使用系统默认语音，全部使用英文半角减号
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$voices = $s.GetInstalledVoices(); "
        "$huihui = $voices | Where-Object {$_.VoiceInfo.Name -match 'Huihui'}; "
        "if($huihui) { $s.SelectVoice($huihui.VoiceInfo.Name) }; "
        f"$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{text_b64}')); "
        f"$s.SetOutputToWaveFile('{wav_path.as_posix()}'); "
        "$s.Speak($t); $s.Dispose()"
    )

    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(f"PowerShell执行异常:\n{completed.stderr}")

    if not wav_path.exists() or wav_path.stat().st_size < 1000:
        raise RuntimeError(f"未生成有效wav文件。stderr:\n{completed.stderr}")

    if output_path.suffix.lower() == ".wav":
        return wav_path

    completed = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame", str(output_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"ffmpeg转码失败:\n{completed.stderr}")

    wav_path.unlink(missing_ok=True)
    return output_path


def synthesize(text: str, output_path: Path, *, api_key: str | None, voice_id: str) -> tuple[Path, str]:
    if api_key and api_key.strip():
        try:
            return fish_audio_tts(text, output_path, api_key=api_key.strip(), voice_id=voice_id.strip()), "fish_audio"
        except Exception as exc:
            print(f"[WARN] Fish Audio TTS失败，自动降级使用Windows本地TTS: {exc}")
    return windows_tts(text, output_path), "windows_tts"


# ---------------- GUI界面 ----------------
class TTSGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"icoolkj TTS工具 {__VERSION__} — FishAudio + Windows TTS")
        self.root.geometry("780x620")

        # 配置区域
        frm_cfg = ttk.LabelFrame(root, text="接口配置")
        frm_cfg.pack(fill="x", padx=10, pady=6)

        ttk.Label(frm_cfg, text="Fish Audio API Key:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self.var_apikey = tk.StringVar()
        ttk.Entry(frm_cfg, textvariable=self.var_apikey, width=68).grid(row=0, column=1, padx=5, pady=4)

        ttk.Label(frm_cfg, text="Voice ID:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self.var_voiceid = tk.StringVar()
        ttk.Entry(frm_cfg, textvariable=self.var_voiceid, width=68).grid(row=1, column=1, padx=5, pady=4)

        # 输出路径
        frm_out = ttk.LabelFrame(root, text="输出MP3文件路径")
        frm_out.pack(fill="x", padx=10, pady=6)
        self.var_outpath = tk.StringVar(value="output/tts.mp3")
        ttk.Entry(frm_out, textvariable=self.var_outpath, width=65).pack(side="left", fill="x", expand=True, padx=5, pady=4)
        ttk.Button(frm_out, text="选择保存位置", command=self.select_output).pack(side="right", padx=5)

        # 文本输入
        frm_text = ttk.LabelFrame(root, text="待合成文本")
        frm_text.pack(fill="both", expand=True, padx=10, pady=6)
        self.txt_input = scrolledtext.ScrolledText(frm_text, height=10)
        self.txt_input.pack(fill="both", expand=True, padx=5, pady=5)

        # 操作按钮
        frm_btn = ttk.Frame(root)
        frm_btn.pack(fill="x", padx=10, pady=4)
        ttk.Button(frm_btn, text="开始合成音频", command=self.run_tts).pack(side="left")
        ttk.Button(frm_btn, text="清空日志", command=self.clear_log).pack(side="left", padx=10)

        # 运行日志
        frm_log = ttk.LabelFrame(root, text="运行日志")
        frm_log.pack(fill="both", expand=True, padx=10, pady=6)
        self.txt_log = scrolledtext.ScrolledText(frm_log, height=8)
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)

    def select_output(self):
        fp = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3音频", "*.mp3"), ("所有文件", "*.*")]
        )
        if fp:
            self.var_outpath.set(fp)

    def log(self, msg: str):
        self.txt_log.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {msg}\n")
        self.txt_log.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.txt_log.delete(1.0, tk.END)

    def run_tts(self):
        text = self.txt_input.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请输入待合成文本！")
            return
        out_path = Path(self.var_outpath.get())
        api_key = self.var_apikey.get()
        voice_id = self.var_voiceid.get()

        try:
            self.log("开始执行音频合成...")
            audio_file, engine = synthesize(text, out_path, api_key=api_key, voice_id=voice_id)
            self.log(f"✅ 合成成功！引擎：{engine}，输出文件：{audio_file.resolve()}")
            messagebox.showinfo("完成", f"音频生成成功！\n合成引擎: {engine}\n{audio_file}")
        except Exception as e:
            err_msg = str(e)
            self.log(f"❌ 合成失败：{err_msg}")
            messagebox.showerror("合成失败", err_msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = TTSGui(root)
    root.mainloop()
