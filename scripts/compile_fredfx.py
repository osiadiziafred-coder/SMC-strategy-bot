#!/usr/bin/env python3
"""Compile-check FredFx V1 m5 (Python bytecode + MQL5 static checks)."""

from __future__ import annotations

import compileall
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EA = ROOT / "MQL5" / "Experts" / "FredFx_V1_m5.mq5"
NAME = "FredFx V1 m5"


def fail(msg: str) -> None:
    print(f"COMPILE FAIL: {msg}")
    sys.exit(1)


def check_python() -> None:
    ok = compileall.compile_dir(str(ROOT / "smc_robot"), quiet=1)
    ok = compileall.compile_dir(str(ROOT / "tests"), quiet=1) and ok
    if not ok:
        fail("Python bytecode compile failed")


def check_mq5() -> None:
    if not EA.is_file():
        fail(f"missing {EA}")
    src = EA.read_text(encoding="utf-8")
    if NAME not in src:
        fail(f"EA must be named {NAME}")
    if "#property strict" in src:
        fail("MQL5 EA must not use #property strict (that is MQL4)")
    if "#include <Trade/Trade.mqh>" not in src:
        fail("missing Trade.mqh include")
    for token in ("OnInit", "OnTick", "OnDeinit", "XAUUSDM", "PERIOD_M5", "PERIOD_M15", "PERIOD_H1"):
        if token not in src:
            fail(f"missing required token {token}")

    # Strip line comments for brace counting.
    code = re.sub(r"//.*?$", "", src, flags=re.M)
    if code.count("{") != code.count("}"):
        fail(f"unbalanced braces {{ {code.count('{')} }} {code.count('}')}")
    if code.count("(") != code.count(")"):
        fail(f"unbalanced parentheses ( {code.count('(')} ) {code.count(')')}")
    if code.count("[") != code.count("]"):
        fail("unbalanced square brackets")

    strings = re.findall(r'"([^"\\]|\\.)*"', code)
    if code.count('"') % 2 != 0:
        fail("unbalanced double quotes")
    del strings

    if "ArrayInitialize(used_high" in src or "ArrayInitialize(used_low" in src:
        fail("ArrayInitialize cannot be used on bool arrays")


def main() -> int:
    check_python()
    check_mq5()
    print(f"COMPILE OK: {NAME}")
    print(f"  Python package compiled")
    print(f"  MQL5 source checked: {EA.relative_to(ROOT)}")
    print("  Attach FredFx_V1_m5.mq5 in MetaEditor (F7) to produce FredFx_V1_m5.ex5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
