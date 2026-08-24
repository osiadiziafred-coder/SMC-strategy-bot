#!/usr/bin/env python3
"""Build the one-file AMD_Session_EA.mq5 from Include/ + Experts/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INC = ROOT / "MQL5" / "Include" / "AMD"
EXPERT = ROOT / "MQL5" / "Experts" / "AMD_Session_EA.mq5"
OUT = ROOT / "AMD_Session_EA.mq5"

MQH_ORDER = [
    "AMD_Enums.mqh",
    "AMD_Config.mqh",
    "AMD_Utils.mqh",
    "AMD_Sessions.mqh",
    "AMD_Liquidity.mqh",
    "AMD_Structure.mqh",
    "AMD_Trading.mqh",
    "AMD_Visuals.mqh",
]


def strip_mqh(text: str, filename: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#include"):
            continue
        if stripped.startswith("#ifndef AMD_") and stripped.endswith("_MQH"):
            continue
        if stripped.startswith("#define AMD_") and stripped.endswith("_MQH"):
            continue
        lines.append(line)
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip() == "#endif":
        lines.pop()
    body = "\n".join(lines).strip() + "\n"
    header = (
        "\n//+------------------------------------------------------------------+\n"
        f"//| {filename}\n"
        "//+------------------------------------------------------------------+\n\n"
    )
    return header + body


def main() -> None:
    expert = EXPERT.read_text()
    marker = "#define AMD_TF_COUNT"
    idx = expert.find(marker)
    if idx < 0:
        raise SystemExit("AMD_TF_COUNT not found in Experts file")
    expert_body = expert[idx:]
    ver = re.search(r'#property version\s+"([^"]+)"', expert)
    desc = re.search(r'#property description\s+"([^"]+)"', expert)
    header = (
        "//+------------------------------------------------------------------+\n"
        "//|                                              AMD_Session_EA.mq5  |\n"
        "//|     FULL standalone bot — copy this ONE file into MQL5/Experts    |\n"
        "//|     XAUUSDm | M15 M30 H1 | 0.01 lots scaling | white-chart dash   |\n"
        "//+------------------------------------------------------------------+\n"
        '#property copyright "SMC Strategy Bot"\n'
        '#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"\n'
        f'#property version   "{ver.group(1) if ver else "1.11"}"\n'
        f'#property description "{desc.group(1) if desc else ""}"\n'
        "\n"
        "#include <Trade/Trade.mqh>\n"
        "\n"
    )
    parts = [header]
    for name in MQH_ORDER:
        parts.append(strip_mqh((INC / name).read_text(), name))
    parts.append(
        "\n//+------------------------------------------------------------------+\n"
        "//| Inputs, multi-TF state machine, OnInit / OnTick\n"
        "//+------------------------------------------------------------------+\n\n"
    )
    parts.append(expert_body)
    if not expert_body.endswith("\n"):
        parts.append("\n")
    OUT.write_text("".join(parts))
    print(f"Wrote {OUT} ({OUT.read_text().count(chr(10)) + 1} lines)")


if __name__ == "__main__":
    main()
