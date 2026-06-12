from __future__ import annotations

import platform
import shutil
import subprocess
import os
from pathlib import Path

from automation_common import get_pipeline_paths, load_config, now_text, write_json


def run_command(command: list[str], timeout_seconds: int = 10) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=timeout_seconds,
        )
        return result.returncode, (result.stdout or result.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, f"命令超时：{' '.join(command)}"
    except Exception as exc:
        return 1, str(exc)


def query_gpu() -> dict:
    code, output = run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if code != 0 or not output:
        return {"available": False, "raw": output}

    first_line = output.splitlines()[0]
    parts = [part.strip() for part in first_line.split(",")]
    return {
        "available": True,
        "name": parts[0] if len(parts) > 0 else "",
        "memory_total_mb": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None,
        "driver_version": parts[2] if len(parts) > 2 else "",
    }


def query_memory_gb() -> float | None:
    code, output = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)",
        ]
    )
    if code != 0 or not output:
        return None
    try:
        return float(output.splitlines()[-1].strip())
    except Exception:
        return None


def query_cpu() -> str:
    code, output = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
        ]
    )
    return output.strip() if code == 0 else platform.processor()


def parse_ollama_models() -> list[dict]:
    code, output = run_command(["ollama", "list"], timeout_seconds=5)
    if code != 0 or not output:
        return []

    models: list[dict] = []
    lines = [line for line in output.splitlines() if line.strip()]
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 3:
            models.append(
                {
                    "name": parts[0],
                    "id": parts[1],
                    "size": parts[2],
                    "source": "ollama",
                }
            )
    return models


def parse_hf_cache_models() -> list[dict]:
    if os.environ.get("ENABLE_HF_CACHE_SCAN", "0") != "1":
        return []

    candidate_roots = [
        Path("F:/MediaPipe Pose_ChineseCLIP_Qwen2-VL/models/hf_cache"),
        Path("F:/MediaPipe Pose_ChineseCLIP_Qwen2-VL/hf_cache"),
        Path.home() / ".cache" / "huggingface" / "hub",
    ]

    seen: dict[str, dict] = {}
    for root in candidate_roots:
        if not root.exists():
            continue
        scanned = 0
        for config_path in root.rglob("config.json"):
            scanned += 1
            if scanned > 200:
                break
            model_dir = config_path.parent
            name = model_dir.name
            if "snapshots" in config_path.parts:
                snapshot_index = config_path.parts.index("snapshots")
                if snapshot_index >= 1:
                    name = config_path.parts[snapshot_index - 1]
            if name.startswith("models--"):
                name = name.replace("models--", "").replace("--", "/")

            total_size = 0
            try:
                for file_path in model_dir.rglob("*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
            except Exception:
                pass

            if name not in seen or total_size > seen[name]["size_bytes"]:
                seen[name] = {
                    "name": name,
                    "path": str(model_dir),
                    "size_bytes": total_size,
                    "size_gb": round(total_size / (1024**3), 3),
                    "source": "huggingface_cache",
                }
    return sorted(seen.values(), key=lambda x: x["size_bytes"], reverse=True)


def build_recommendation(gpu_info: dict, memory_gb: float | None) -> dict:
    gpu_mem = gpu_info.get("memory_total_mb") or 0
    ram = memory_gb or 0

    if gpu_mem >= 10000 and ram >= 32:
        default_model = "qwen3:8b"
        optional_upgrade = "qwen3:14b"
        note = "显存和内存较充足，可将 qwen3:8b 作为默认，14b 作为升级方案。"
    elif gpu_mem >= 6000 and ram >= 15.5:
        default_model = "qwen3:4b"
        optional_upgrade = "qwen3:8b"
        note = "6GB 显存和 16GB 内存更适合 qwen3:4b 常驻；8b 仅建议在你接受更慢推理速度时升级。"
    else:
        default_model = "qwen3:1.7b"
        optional_upgrade = "qwen3:4b"
        note = "当前资源偏紧，应优先使用 1.7b 或更小尺寸模型。"

    return {
        "recommended_default_model": default_model,
        "optional_upgrade_model": optional_upgrade,
        "not_recommended_default_models": ["qwen3:14b", "qwen3:30b"],
        "reason": note,
    }


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)

    gpu_info = query_gpu()
    memory_gb = query_memory_gb()
    cpu_name = query_cpu()
    ollama_models = parse_ollama_models()
    hf_models = parse_hf_cache_models()

    inventory = {
        "generated_at": now_text(),
        "host": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu": cpu_name,
            "memory_gb": memory_gb,
            "gpu": gpu_info,
            "disk_free_gb": round(shutil.disk_usage(paths.root_dir.drive or "E:/").free / (1024**3), 2),
        },
        "local_services": {
            "ollama_installed": shutil.which("ollama") is not None,
            "lmstudio_installed": shutil.which("lmstudio") is not None,
        },
        "ollama_models": ollama_models,
        "huggingface_cached_models": hf_models[:20],
        "recommendation": build_recommendation(gpu_info, memory_gb),
    }

    write_json(paths.current_dir / "local_model_inventory.json", inventory)
    print(paths.current_dir / "local_model_inventory.json")


if __name__ == "__main__":
    main()
