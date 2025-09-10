#!/usr/bin/env python3
"""
Arifi-01 Protocol Runner (AI-enabled)

Features:
- detects target language (python/js)
- invokes AI backend to generate code
- runs static analysis (flake8/mypy/radon) for Python, placeholder for JS
- performs feedback loop: repair via AI until analysis passes or max iterations reached
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from .ai_backend import AIBackend

BASE_DIR = Path(__file__).parent.parent.resolve()
OUTPUT_DIR = Path(BASE_DIR) / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# configurable
MAX_EVOLVE_ITER = 3  # max repair iterations with AI
AI_MODEL = "gpt-4o-mini"  # change if desired

def detect_language_from_prompt(prompt: str) -> str:
    lower = prompt.lower()
    if "javascript" in lower or "js" in lower or ".js" in lower:
        return "javascript"
    if "typescript" in lower or "ts " in lower:
        return "typescript"
    return "python"

def run_cmd(cmd: list, timeout: int = 20) -> Dict:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as e:
        return {"rc": 2, "stdout": "", "stderr": str(e)}

def analyze_file(path: Path) -> Dict:
    """Run language-appropriate analysis. Returns report dict."""
    lang = path.suffix.lstrip(".")
    report = {}
    if lang == "py":
        # flake8
        report["flake8"] = run_cmd(["flake8", str(path)])
        # mypy
        report["mypy"] = run_cmd(["mypy", str(path)])
        # radon
        report["radon"] = run_cmd(["radon", "cc", "-s", str(path)])
    elif lang in ("js", "ts"):
        # placeholder for eslint/prettier; try to run eslint if present
        report["eslint"] = run_cmd(["eslint", str(path)])
    else:
        report["note"] = f"no analyzer for .{lang}"
    return report

def metrics_ok(report: Dict) -> bool:
    """
    Heuristic: decide if report is 'clean' and no urgent errors.
    For Python: flake8 rc==0 and mypy rc==0
    For JS: eslint rc==0 if present
    """
    if "flake8" in report and report["flake8"]["rc"] != 0:
        return False
    if "mypy" in report and report["mypy"]["rc"] != 0:
        return False
    if "eslint" in report and report["eslint"]["rc"] != 0:
        return False
    # else assume ok
    return True

def save_artifacts(code: str, prompt: str, lang: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    ext = "py" if lang == "python" else ("js" if lang == "javascript" else "txt")
    out = OUTPUT_DIR / f"generated_{ts}.{ext}"
    out.write_text(code, encoding="utf-8")
    meta = {"prompt": prompt, "language": lang, "generated_at": ts}
    (out.with_suffix(out.suffix + ".meta.json")).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out

def prompt_from_file(prompt_path: str) -> str:
    p = Path(prompt_path)
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text(encoding="utf-8").strip()

def generate_with_ai(prompt: str, backend: AIBackend, language: str) -> Dict:
    return backend.generate_code(prompt=prompt, language=language)

def attempt_evolve(out_path: Path, backend: AIBackend, prompt: str) -> Path:
    """
    Iterative repair:
    - analyze file
    - if issues, call backend.repair_code with analysis
    - save repaired file, re-analyze
    - stop when metrics_ok or reach MAX_EVOLVE_ITER
    """
    current_path = out_path
    for iteration in range(0, MAX_EVOLVE_ITER):
        report = analyze_file(current_path)
        ok = metrics_ok(report)
        print(f"[evolve] iteration={iteration} ok={ok}")
        if ok:
            break
        code_text = current_path.read_text(encoding="utf-8")
        # ask AI to repair
        print("[evolve] Requesting AI repair...")
        res = backend.repair_code(code_text, analysis_report=report, language="python" if current_path.suffix == ".py" else "javascript")
        if not res.get("success"):
            print("[evolve] AI repair failed:", res.get("error"))
            break
        repaired_code = res["code"]
        # save as new file
        new_path = current_path.with_name(current_path.stem + f"_r{iteration+1}" + current_path.suffix)
        new_path.write_text(repaired_code, encoding="utf-8")
        (new_path.with_suffix(new_path.suffix + ".meta.json")).write_text(json.dumps({"repaired_by_ai": True, "iter": iteration+1}), encoding="utf-8")
        current_path = new_path
    return current_path

def main(prompt_file: Optional[str] = None):
    if prompt_file is None and len(sys.argv) > 1:
        prompt_file = sys.argv[1]
    if not prompt_file:
        print("Usage: python -m arifi_protocol_runner.arifi_protocol_runner <prompt-file>")
        sys.exit(1)

    print("🔮 Arifi-01 Protocol Runner (AI-enabled)")
    prompt = prompt_from_file(prompt_file)
    lang = detect_language_from_prompt(prompt)
    print(f"[info] prompt language detected: {lang}")

    backend = AIBackend(model=AI_MODEL)

    # 1) Generate initial code (AI or stub)
    gen = generate_with_ai(prompt, backend=backend, language=lang)
    if not gen.get("success"):
        print("[error] generation failed:", gen.get("error"))
        sys.exit(1)

    code = gen["code"]
    out_path = save_artifacts(code, prompt, lang)
    print(f"✅ Kode berhasil dibuat: {out_path}")

    # 2) Analyze and iteratively repair
    final_path = attempt_evolve(out_path, backend=backend, prompt=prompt)

    # 3) Final analysis
    final_report = analyze_file(final_path)
    print("📊 Final analysis:")
    print(json.dumps(final_report, indent=2))

    print("✨ Done. Artifacts in:", OUTPUT_DIR)

if __name__ == "__main__":
    main()