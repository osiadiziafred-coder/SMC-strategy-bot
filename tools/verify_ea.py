#!/usr/bin/env python3
"""Static checks for the MQL5 EA source: required APIs, inputs, and brace balance."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EA_DIR = ROOT / "MQL5" / "Experts" / "XAUUSDm_H1M5_SMC"

REQUIRED_FUNCTIONS = [
    "GetH1Bias",
    "FindSwingHighs",
    "FindSwingLows",
    "DetectLiquiditySweep",
    "FindSupplyZone",
    "FindDemandZone",
    "DetectBullishBOS",
    "DetectBearishBOS",
    "DetectBullishMSS",
    "DetectBearishMSS",
    "ConfirmBuySetup",
    "ConfirmSellSetup",
    "CalculateLotSize",
    "CalculateStopLoss",
    "CalculateTakeProfit",
    "CalculateRiskReward",
    "CheckSpread",
    "CheckRiskLimits",
    "OpenBuy",
    "OpenSell",
    "ManageTrade",
]

REQUIRED_INPUTS = [
    "InpSymbol",
    "StartingLot",
    "FirstIncreaseBalance",
    "BalanceStep",
    "LotIncrease",
    "MaxOpenPositions",
    "MaximumDailyTrades",
    "MaximumDailyLossPercent",
    "MaximumDrawdownPercent",
    "MinimumRiskReward",
    "MaxStopLossPoints",
    "MaxSpreadPoints",
    "UseSpreadFilter",
    "UseTradingSession",
    "StartTradingHour",
    "EndTradingHour",
    "UseNewsFilter",
    "MagicNumber",
    "ShowZones",
    "ShowLiquidity",
    "ShowStructure",
    "ShowEntryLevels",
    "UseLiquiditySweep",
    "UseMarketStructure",
    "UseOrderBlocks",
    "UseM5Confirmation",
    "UseDailyLossProtection",
    "UseMaxDrawdownProtection",
]

FORBIDDEN = [
    "iMA(",
    "iRSI(",
    "iMACD(",
    "martingale",
    "Martingale",
]


def read_all() -> str:
    parts = []
    for path in sorted(EA_DIR.glob("*")):
        if path.suffix.lower() in {".mq5", ".mqh"}:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def check_braces(text: str, name: str) -> list[str]:
    errors = []
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                errors.append(f"{name}: unmatched closing brace near offset {i}")
                return errors
    if depth != 0:
        errors.append(f"{name}: brace imbalance remaining={depth}")
    return errors


def main() -> int:
    if not EA_DIR.exists():
        print(f"ERROR: EA directory missing: {EA_DIR}")
        return 1

    combined = read_all()
    errors: list[str] = []

    for fn in REQUIRED_FUNCTIONS:
        if not re.search(rf"\b{fn}\s*\(", combined):
            errors.append(f"missing function {fn}()")

    for inp in REQUIRED_INPUTS:
        if not re.search(rf"\binput\b[^\n]*\b{inp}\b", combined):
            errors.append(f"missing input {inp}")

    for token in FORBIDDEN:
        if token.lower() in {"martingale"}:
            if re.search(r"\bmartingale\b", combined, re.I):
                errors.append(f"forbidden strategy token {token}")
        elif token in combined:
            errors.append(f"forbidden indicator shortcut {token}")

    if "XAUUSDm" not in combined:
        errors.append("symbol XAUUSDm not referenced")

    for path in sorted(EA_DIR.glob("*")):
        if path.suffix.lower() in {".mq5", ".mqh"}:
            errors.extend(check_braces(path.read_text(encoding="utf-8"), path.name))

    if "iTime(" not in combined and "CopyRates(" not in combined:
        errors.append("no closed-bar data access found")

    if errors:
        print("EA verification FAILED:")
        for e in errors:
            print(" -", e)
        return 1

    print("EA verification passed:")
    print(f" - {len(REQUIRED_FUNCTIONS)} required functions present")
    print(f" - {len(REQUIRED_INPUTS)} required inputs present")
    print(" - brace balance OK")
    print(" - no MA/RSI/MACD/martingale shortcuts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
