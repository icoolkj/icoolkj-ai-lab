#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
icoolkj AI研究实验室
FishAudio TTS + Windows 本地 TTS 图形化工具
官网：https://icoolkj.com
邮箱：icoolkj@163.com
QQ邮箱：594047667@qq.com
版本：v1.1.0

功能：
- FishAudio 在线 TTS（API Key + Voice ID）
- 在线接口失败时降级为 Windows 原生 TTS
- WAV 输出不依赖 FFmpeg；MP3 输出需要可用的 FFmpeg
- 自动检测 PowerShell / FFmpeg，并提供可读错误信息
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

__VERSION__ = "v1.1.0"
APP_NAME = "icoolkj TTS工具"


def app_dir() -> Path:
    """源码运行时返回脚本目录；PyInstaller 运行时返回 EXE 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_ffmpeg_candidates() -> list[Path]:
    """查找随程序发布的 FFmpeg 常见位置。"""
    base = app_dir()
    candidates = [
        base / "ffmpeg.exe",
        base / "bin" / "ffmpeg.exe",
        base / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    if hasattr(sys, "_MEIPASS"):
        bundle = Path(sys._MEIPASS)
        candidates.extend([
            bundle / "ffmpeg.exe",
            bundle / "bin" / "ffmpeg.exe",
            bundle / "ffmpeg" / "bin" / "ffmpeg.exe",
        ])
    return candidates


def find_ffmpeg() -> str | None:
    for candidate in bundled_ffmpeg_candidates():
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg.exe") or shutil.which("ffmpeg")


def find_powershell() -> str | None:
    """优先使用 Windows PowerShell 5.1，其次尝试 PowerShell 7。"""
    candidates = [
        os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
        ),
        shutil.which("powershell.exe"),
        shutil.which("pwsh.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def fish_audio_tts(
    text: str,
    output_path: Path,
    *,
    api_key: str,
    voice_id: str,
    max_retries: int = 3,
) -> Path:
    """请求 FishAudio TTS，并将返回的音频保存到目标路径。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": text,
        "reference_id": voice_id,
        "format": "mp3",
        "normalize": True,
    }
    last_error: Exception | None = None

    for attempt in range(max_retries):
        request = urllib.request.Request(
            "https://api.fish.audio/v1/tts",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "model": "s2.1-pro-free",
                "User-Agent": "icoolkj-tts-gui/1.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                audio_data = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise RuntimeError(
                f"FishAudio HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait_seconds = 2 ** (attempt + 1)
                time.sleep(wait_seconds)
                continue
            break

        # 常见 MP3 文件头为 ID3 或 MPEG frame sync。
        if not audio_data or not (
            audio_data.startswith(b"ID3")
            or audio_data.startswith(b"\xff\xfb")
            or audio_data.startswith(b"\xff\xf3")
            or audio_data.startswith(b"\xff\xf2")
        ):
            preview = audio_data[:300].decode("utf-8", "replace")
            last_error = RuntimeError(
                f"FishAudio 返回的内容不像 MP3 音频：{preview}"
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise last_error

        output_path.write_bytes(audio_data)
        return output_path

    raise RuntimeError(
        f"FishAudio 请求重试 {max_retries} 次后仍然失败：{last_error}"
    )


def windows_tts_wav(text: str, wav_path: Path) -> Path:
    """通过 System.Speech 调用 Windows 本地语音，输出 WAV。"""
    powershell = find_powershell()
    if not powershell:
        raise RuntimeError(
            "找不到 PowerShell。\n"
            "请确认 Windows PowerShell 已安装，或检查系统文件：\n"
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        )

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    # Base64 避免中文、引号、换行等文本破坏 PowerShell 命令。
    text_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    wav_path_ps = str(wav_path.resolve())

    # 将路径编码为 Base64，避免路径中引号等字符影响 PowerShell 语法。
    path_b64 = base64.b64encode(wav_path_ps.encode("utf-8")).decode("ascii")

    script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$t = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__TEXT_B64__'))
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PATH_B64__'))
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = $s.GetInstalledVoices()
    $huihui = $voices | Where-Object { $_.VoiceInfo.Name -match 'Huihui' } | Select-Object -First 1
    if ($huihui) {
        $s.SelectVoice($huihui.VoiceInfo.Name)
    }
    $s.SetOutputToWaveFile($p)
    $s.Speak($t)
    $s.SetOutputToNull()
}
finally {
    $s.Dispose()
}
""".replace("__TEXT_B64__", text_b64).replace("__PATH_B64__", path_b64)

    try:
        completed = subprocess.run(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"无法启动 PowerShell：{powershell}\n系统提示：{exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Windows 本地语音合成超时（180 秒）。") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "PowerShell 执行 Windows 本地 TTS 失败。\n"
            f"程序：{powershell}\n"
            f"退出码：{completed.returncode}\n"
            f"错误详情：{detail or '没有返回错误详情'}"
        )

    if not wav_path.is_file():
        raise RuntimeError(
            "PowerShell 执行结束，但没有找到生成的 WAV 文件：\n"
            f"{wav_path}\n"
            f"PowerShell 输出：{completed.stdout.strip()}"
        )

    if wav_path.stat().st_size < 1000:
        raise RuntimeError(
            f"生成的 WAV 文件为空或不完整：{wav_path}"
        )

    return wav_path


def windows_tts(text: str, output_path: Path) -> Path:
    """Windows 本地降级。根据输出扩展名生成 WAV 或 MP3。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lower()
    if suffix not in (".mp3", ".wav"):
        raise RuntimeError("输出文件扩展名只支持 .mp3 或 .wav。")

    # 直接请求 WAV 时不需要任何外部转码工具。
    wav_path = output_path if suffix == ".wav" else output_path.with_name(
        output_path.stem + ".windows_tmp.wav"
    )

    windows_tts_wav(text, wav_path)

    if suffix == ".wav":
        return wav_path

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        # 保留生成的 WAV，提示用户可以直接播放，避免音频丢失。
        raise RuntimeError(
            "Windows 原生 TTS 已成功生成 WAV，但无法输出 MP3：找不到 FFmpeg。\n\n"
            f"已生成的 WAV 文件：\n{wav_path}\n\n"
            "解决方式：\n"
            "1. 安装 FFmpeg，并将 ffmpeg.exe 所在的 bin 目录加入 PATH；或\n"
            "2. 在输出路径中将文件后缀改为 .wav，即可完全不依赖 FFmpeg；或\n"
            "3. 将 ffmpeg.exe 放在程序同目录或程序目录的 bin 文件夹中。"
        )

    try:
        completed = subprocess.run(
            [
                ffmpeg, "-y",
                "-i", str(wav_path),
                "-vn",
                "-codec:a", "libmp3lame",
                "-q:a", "2",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"找到了 FFmpeg 路径，但无法启动：{ffmpeg}\n{exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("FFmpeg 音频转码超时（180 秒）。") from exc

    if completed.returncode != 0 or not output_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "FFmpeg 转换 WAV 为 MP3 失败。\n"
            f"FFmpeg：{ffmpeg}\n"
            f"退出码：{completed.returncode}\n"
            f"错误详情：{detail or '没有返回错误详情'}\n"
            f"原始 WAV 保留在：{wav_path}"
        )

    try:
        wav_path.unlink(missing_ok=True)
    except OSError:
        pass

    return output_path


def synthesize(
    text: str,
    output_path: Path,
    *,
    api_key: str | None,
    voice_id: str,
    log_callback=None,
) -> tuple[Path, str]:
    """先尝试在线 FishAudio；失败后自动切换 Windows 本地 TTS。"""
    if api_key and api_key.strip() and voice_id and voice_id.strip():
        try:
            if log_callback:
                log_callback("正在使用 FishAudio 在线语音合成……")
            result = fish_audio_tts(
                text,
                output_path,
                api_key=api_key.strip(),
                voice_id=voice_id.strip(),
            )
            return result, "FishAudio 在线 TTS"
        except Exception as exc:
            if log_callback:
                log_callback(
                    f"FishAudio 合成失败，准备降级到 Windows 本地 TTS：{exc}"
                )
    elif log_callback:
        log_callback("未填写完整的 API Key / Voice ID，直接使用 Windows 本地 TTS。")

    if log_callback:
        log_callback("正在调用 Windows 原生语音合成……")
    result = windows_tts(text, output_path)
    return result, "Windows 本地 TTS"


class TTSGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} {__VERSION__} — FishAudio + Windows TTS")
        self.root.geometry("820x700")
        self.root.minsize(700, 600)

        self.var_apikey = tk.StringVar()
        self.var_voiceid = tk.StringVar()
        self.var_outpath = tk.StringVar(value=str(app_dir() / "output" / "tts.mp3"))
        self.var_status = tk.StringVar(value="就绪")

        self._build_ui()
        self.log(f"{APP_NAME} {__VERSION__} 已启动。")
        self.log(f"程序目录：{app_dir()}")
        ffmpeg = find_ffmpeg()
        self.log(f"FFmpeg：{ffmpeg if ffmpeg else '未找到（WAV 模式仍可使用）'}")
        ps = find_powershell()
        self.log(f"PowerShell：{ps if ps else '未找到'}")

    def _build_ui(self):
        frm_cfg = ttk.LabelFrame(self.root, text="FishAudio 接口配置（可选）")
        frm_cfg.pack(fill="x", padx=10, pady=7)
        frm_cfg.columnconfigure(1, weight=1)

        ttk.Label(frm_cfg, text="FishAudio API Key：").grid(
            row=0, column=0, sticky="w", padx=6, pady=5
        )
        ttk.Entry(frm_cfg, textvariable=self.var_apikey, width=60, show="*").grid(
            row=0, column=1, sticky="ew", padx=6, pady=5
        )

        ttk.Label(frm_cfg, text="Voice ID：").grid(
            row=1, column=0, sticky="w", padx=6, pady=5
        )
        ttk.Entry(frm_cfg, textvariable=self.var_voiceid, width=60).grid(
            row=1, column=1, sticky="ew", padx=6, pady=5
        )

        frm_out = ttk.LabelFrame(self.root, text="输出音频文件")
        frm_out.pack(fill="x", padx=10, pady=7)
        frm_out.columnconfigure(0, weight=1)
        ttk.Entry(frm_out, textvariable=self.var_outpath).grid(
            row=0, column=0, sticky="ew", padx=6, pady=6
        )
        ttk.Button(frm_out, text="选择保存位置", command=self.select_output).grid(
            row=0, column=1, padx=6, pady=6
        )
        ttk.Label(
            frm_out,
            text="提示：选择 .wav 可直接使用 Windows 本地 TTS；选择 .mp3 时本地降级需要 FFmpeg。",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        frm_text = ttk.LabelFrame(self.root, text="待合成文本")
        frm_text.pack(fill="both", expand=True, padx=10, pady=7)
        self.txt_input = scrolledtext.ScrolledText(
            frm_text, height=9, wrap="word", undo=True
        )
        self.txt_input.pack(fill="both", expand=True, padx=6, pady=6)

        frm_btn = ttk.Frame(self.root)
        frm_btn.pack(fill="x", padx=10, pady=4)
        self.btn_synthesize = ttk.Button(
            frm_btn, text="开始合成音频", command=self.run_tts
        )
        self.btn_synthesize.pack(side="left")
        ttk.Button(frm_btn, text="清空日志", command=self.clear_log).pack(
            side="left", padx=10
        )
        ttk.Label(frm_btn, textvariable=self.var_status).pack(side="right")

        frm_log = ttk.LabelFrame(self.root, text="运行日志")
        frm_log.pack(fill="both", expand=True, padx=10, pady=7)
        self.txt_log = scrolledtext.ScrolledText(
            frm_log, height=9, wrap="word", state="normal"
        )
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

    def select_output(self):
        current = self.var_outpath.get().strip()
        initial_dir = str(Path(current).parent) if current else str(app_dir())
        initial_file = Path(current).name if current else "tts.mp3"
        fp = filedialog.asksaveasfilename(
            title="选择音频保存位置",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=".mp3",
            filetypes=[
                ("MP3 音频", "*.mp3"),
                ("WAV 音频（Windows 本地 TTS 推荐）", "*.wav"),
                ("所有文件", "*.*"),
            ],
        )
        if fp:
            self.var_outpath.set(fp)

    def log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"{timestamp} | {msg}\n")
        self.txt_log.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.txt_log.delete("1.0", tk.END)

    def run_tts(self):
        text = self.txt_input.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请输入待合成文本！", parent=self.root)
            return

        raw_path = self.var_outpath.get().strip().strip('"')
        if not raw_path:
            messagebox.showwarning("提示", "请设置音频输出路径。", parent=self.root)
            return

        out_path = Path(raw_path).expanduser()
        if out_path.suffix.lower() not in (".mp3", ".wav"):
            messagebox.showwarning(
                "输出格式不支持",
                "输出文件名请使用 .mp3 或 .wav 后缀。",
                parent=self.root,
            )
            return

        self.btn_synthesize.configure(state="disabled")
        self.var_status.set("合成中……")
        self.log("-" * 55)
        self.log("开始执行音频合成……")
        self.log(f"目标文件：{out_path}")

        try:
            audio_file, engine = synthesize(
                text,
                out_path,
                api_key=self.var_apikey.get(),
                voice_id=self.var_voiceid.get(),
                log_callback=self.log,
            )
            self.log(f"合成成功！引擎：{engine}")
            self.log(f"输出文件：{audio_file.resolve()}")
            self.var_status.set("合成成功")
            messagebox.showinfo(
                "合成完成",
                f"音频生成成功！\n\n"
                f"合成引擎：{engine}\n"
                f"输出文件：{audio_file.resolve()}",
                parent=self.root,
            )
        except Exception as exc:
            error_message = str(exc)
            self.log(f"合成失败：{error_message}")
            self.var_status.set("合成失败")
            messagebox.showerror("合成失败", error_message, parent=self.root)
        finally:
            self.btn_synthesize.configure(state="normal")


def main():
    root = tk.Tk()
    TTSGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
