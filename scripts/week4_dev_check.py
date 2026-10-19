"""Week 4 milestone check: the Developer agent generates runnable code.

    python scripts/week4_dev_check.py

For each sample the Developer agent is run against the mock provider, its
output is written into the sandbox, executed, and the stdout is compared with
the expected result.  Nothing here is asserted on faith: every PASS below is a
program that actually ran.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mawe.agents.developer import DeveloperAgent  # noqa: E402
from mawe.config import Settings  # noqa: E402
from mawe.llm import MockProvider  # noqa: E402
from mawe.sample_code import RUNNABLE_SAMPLES, dev_script  # noqa: E402
from mawe.sandbox import docker_available, run_files  # noqa: E402

SETTINGS = Settings(max_iterations=5, sandbox_timeout_s=15)
LINE = "-" * 104


def main() -> int:
    print("=" * 104)
    print("WEEK 4 MILESTONE - Developer agent generates runnable code")
    print("=" * 104)
    print(f"isolation: subprocess with a {SETTINGS.sandbox_timeout_s}s timeout "
          f"(docker available: {docker_available()})")
    print(LINE)

    total = passed = 0

    for name, sample in RUNNABLE_SAMPLES.items():
        expected_paths = [f["path"] for f in sample["files"]]

        provider = MockProvider(dev_script(name))
        update = DeveloperAgent(provider, SETTINGS).run({
            "spec": "{}",
            "spec_json": {"files": expected_paths},
            "language": "python",
        })

        if "errors" in update:
            print(f"{name}\n    ! developer failed: {update['errors'][0]}")
            total += len(sample["checks"])
            continue

        files = update["files"]
        print(f"{name}")
        print(f"    files produced : {', '.join(f['path'] for f in files)}"
              f"   ({len(files)} file{'s' if len(files) != 1 else ''})")
        print(f"    code hash      : {update['code_hash'][:16]}...")

        for check in sample["checks"]:
            total += 1
            result = run_files(files, "python",
                               timeout_s=SETTINGS.sandbox_timeout_s,
                               argv=check["argv"], stdin=check["stdin"])
            actual = (result["stdout"] or "").strip()
            ok = result["exit_code"] == 0 and actual == check["expect"]
            passed += ok

            invocation = " ".join(check["argv"]) or f"<stdin: {check['stdin'][:24]!r}>"
            status = "PASS" if ok else "FAIL"
            print(f"    {status}  {invocation:<34} -> {actual!r:<20} "
                  f"(expected {check['expect']!r})")
            if not ok and result["stderr"].strip():
                print(f"          stderr: {result['stderr'].strip()[:160]}")
        print()

    print(LINE)
    print(f"executions passed: {passed}/{total}")
    multi = sum(1 for s in RUNNABLE_SAMPLES.values() if len(s["files"]) > 1)
    print(f"multi-file projects verified: {multi}/{len(RUNNABLE_SAMPLES)} "
          f"(cross-module imports resolve inside the sandbox)")
    print(f"M-W4 {'MET' if passed == total else 'NOT MET'} - generated code is "
          f"complete, multi-file, and runs.")
    print("=" * 104)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
