# SMC XAUUSDm Trading Robot

Automated trading robot for **XAUUSDm** (Gold) using **Smart Money Concepts (SMC)**. Available as a native **MQL5 Expert Advisor** (recommended) and a Python script.

## Strategy

Multi-timeframe SMC confluence:

| Timeframe | Role |
|-----------|------|
| **H1** | Directional bias (HH/HL or LH/LL) |
| **M15** | Liquidity sweep + MSS/CHoCH confirmation |
| **M5** | Fair Value Gap (FVG) retest entry |

### Entry conditions

1. **H1 bias** — bullish (higher highs + higher lows) or bearish (lower highs + lower lows)
2. **M15 liquidity sweep** — price takes out a swing high/low then reverses
3. **M15 CHoCH** — market structure shifts in the sweep direction
4. **M5 FVG retest** — price enters a fair value gap zone for precise entry

## Trade rules

| Parameter | Value |
|-----------|-------|
| Symbol | XAUUSDm |
| Risk : Reward | 1 : 2 |
| Breakeven | SL moves to entry at +1R |
| Max positions | 1 |
| Lot sizing | $100 balance = 0.01 lot |
| News trading | Enabled |

---

## MQL5 Expert Advisor (recommended)

Runs natively inside MetaTrader 5 — no Python required.

### Project structure

```
mql5/
├── Experts/
│   └── SMC_Robot/
│       └── SMC_Robot.mq5       # Main Expert Advisor
└── Include/
    └── SMC/
        ├── SMC_Types.mqh        # Enums and structs
        ├── SMC_Swing.mqh        # Swing high/low detection
        ├── SMC_Liquidity.mqh    # Liquidity sweep detection
        ├── SMC_Structure.mqh    # MSS/CHoCH + H1 bias
        ├── SMC_FVG.mqh          # Fair Value Gap detection
        ├── SMC_Strategy.mqh     # Multi-TF confluence engine
        └── SMC_Risk.mqh         # Lot sizing, breakeven
```

### Install in MetaTrader 5

1. Open MT5 → **File → Open Data Folder**
2. Copy the contents of `mql5/` into your MT5 data folder:
   - `mql5/Experts/SMC_Robot/` → `MQL5/Experts/SMC_Robot/`
   - `mql5/Include/SMC/` → `MQL5/Include/SMC/`
3. In MT5, open **MetaEditor** (F4)
4. Open `Experts/SMC_Robot/SMC_Robot.mq5` and click **Compile** (F7)
5. In MT5, drag **SMC_Robot** onto the **XAUUSDm M5** chart
6. Enable **AutoTrading** (toolbar button)

### EA input parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| InpSymbol | XAUUSDm | Trading symbol |
| InpRiskReward | 2.0 | Risk : Reward ratio (1:2) |
| InpBreakevenAtR | 1.0 | Move SL to breakeven at +1R |
| InpBalancePer001Lot | 100.0 | $100 = 0.01 lot |
| InpSwingLookback | 5 | Swing detection lookback |
| InpSweepTolerancePips | 2.0 | Liquidity sweep tolerance |
| InpFvgMinGapPips | 1.0 | Minimum FVG gap size |
| InpPipSize | 0.1 | Pip size for gold |
| InpMagicNumber | 20260820 | EA magic number |

### How it works

1. On each new **M5 bar**, scans H1 → M15 → M5 for SMC confluence
2. Opens **one position** when all conditions align
3. Sets SL below/above sweep wick, TP at **2R**
4. On every tick, moves SL to **breakeven** when price hits +1R
5. Repeats — multiple trades per day allowed (including news)

---

## Python version (alternative)

Requires Python + MT5 terminal running on Windows.

```bash
pip install -r requirements.txt
# Edit config.py with MT5 credentials
python main.py
```

See `config.py`, `main.py`, and `smc/` for the Python implementation.

---

## Lot sizing examples

| Balance | Lot size |
|---------|----------|
| $100 | 0.01 |
| $500 | 0.05 |
| $1,000 | 0.10 |
| $10,000 | 1.00 |

## Risk disclaimer

This software is for educational purposes. Trading forex and CFDs involves substantial risk of loss. Always backtest thoroughly in the MT5 Strategy Tester before live trading. Past performance does not guarantee future results.
