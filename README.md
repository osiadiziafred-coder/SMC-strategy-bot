# SMC XAUUSDm Trading Robot

Python automated trading robot for **XAUUSDm** (Gold) using **Smart Money Concepts (SMC)** with MetaTrader 5.

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

## Project structure

```
├── main.py              # Robot entry point & main loop
├── config.py            # All settings (symbol, timeframes, R:R, lots)
├── broker.py            # MetaTrader 5 connection & orders
├── risk_manager.py      # Lot sizing, SL/TP, breakeven logic
├── strategy.py          # Multi-TF SMC confluence engine
├── smc/
│   ├── swing.py         # Swing high/low detection
│   ├── liquidity.py     # Liquidity sweep detection
│   ├── structure.py     # MSS / CHoCH & H1 bias
│   └── fvg.py           # Fair Value Gap detection
└── requirements.txt
```

## Setup

### Prerequisites

- **Windows** with [MetaTrader 5](https://www.metatrader5.com/) installed
- Python 3.10+
- An MT5 account with XAUUSDm available (e.g. Exness, IC Markets)

### Install

```bash
pip install -r requirements.txt
```

### Configure

Edit `config.py` or set environment variables:

```python
# config.py
symbol = "XAUUSDm"
mt5_login = 12345678        # your MT5 account number
mt5_password = "your_password"
mt5_server = "Exness-MT5Trial"
mt5_path = "C:/Program Files/MetaTrader 5/terminal64.exe"
```

### Run

```bash
python main.py
```

The robot will:
1. Connect to MT5
2. Scan H1 → M15 → M5 every 10 seconds
3. Open **one position** when all SMC conditions align
4. Move SL to **breakeven** when price reaches +1R
5. Close at TP (2R) or SL
6. Repeat — multiple trades per day allowed

## Lot sizing examples

| Balance | Lot size |
|---------|----------|
| $100 | 0.01 |
| $500 | 0.05 |
| $1,000 | 0.10 |
| $10,000 | 1.00 |

## Risk disclaimer

This software is for educational purposes. Trading forex and CFDs involves substantial risk of loss. Always backtest thoroughly before live trading. Past performance does not guarantee future results.
