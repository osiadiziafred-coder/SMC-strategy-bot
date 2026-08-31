"""End-to-end verification of the 17 required system checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from smc_robot.backtest import run_backtest
from smc_robot.bridge import FileBridge, Mql5PaperExecutor
from smc_robot.broker.paper import PaperBroker
from smc_robot.config import Settings
from smc_robot.data.setups import bullish_structure_candles, m15_buy_setup, m15_sell_setup
from smc_robot.engine import SmcEngine
from smc_robot.journal import DecisionJournal
from smc_robot.manager import PositionManager
from smc_robot.models import Direction, ScoreBreakdown, SetupGrade, Signal, TradePlan, Trend
from smc_robot.risk.daily import DailyGuard
from smc_robot.risk.protection import Quote
from smc_robot.risk.sizing import SymbolSpec
from smc_robot.robot import SmcRobot
from smc_robot.scoring import FEATURE_NAMES, SetupScorer
from smc_robot.scoring.train import train_model


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _mql5_static(path: Path) -> tuple[bool, str]:
    text = path.read_text(encoding="utf-8")
    banned = ("def ", "from __future__", '"""', "import numpy")
    if any(token in text for token in banned):
        return False, "python_tokens_in_mq5"
    need = (
        "#property",
        "#include <Trade/Trade.mqh>",
        "int OnInit()",
        "void OnTick()",
        "CTrade",
        "g_trailOn",
        "g_trailOn && fav >= g_trailR * risk",
        "trail_enabled",
    )
    missing = [item for item in need if item not in text]
    if missing:
        return False, "missing:" + ",".join(missing)
    return True, "mql5_looks_valid"


def _signal(direction: Direction, entry: float, sl: float, tp: float, sid: str) -> Signal:
    plan = TradePlan(direction=direction, entry=entry, sl=sl, tp=tp, risk=abs(entry - sl), lots=0.02, sl_source="test")
    score = ScoreBreakdown(total=80, rule_score=80, ml_probability=0.72, grade=SetupGrade.A)
    trend = Trend.BULLISH if direction == Direction.BUY else Trend.BEARISH
    return Signal(
        signal_id=sid,
        direction=direction,
        plan=plan,
        score=score,
        h1_trend=trend,
        m30_trend=trend,
        m15_trend=trend,
        reason="verify",
        grade=SetupGrade.A,
    )


def run_verification(tmp: Path | None = None) -> dict:
    root = Path(__file__).resolve().parent.parent
    work = tmp or (root / "logs" / "verify")
    work.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    try:
        import smc_robot  # noqa: F401

        checks.append(_check("1_python_runs", True, "import_ok"))
    except Exception as exc:
        checks.append(_check("1_python_runs", False, str(exc)))

    try:
        import python_smc_ml_robot.main  # noqa: F401
        from python_smc_ml_robot.config import MIN_ML_SCORE

        checks.append(_check("1b_spec_package", MIN_ML_SCORE == 0.70, "python_smc_ml_robot"))
    except Exception as exc:
        checks.append(_check("1b_spec_package", False, str(exc)))

    for name in ("pyhonAI_SMC.mq5", "PythonAI_SMC.mq5", "PythonML_SMC_Bridge.mq5"):
        ok, detail = _mql5_static(root / name)
        checks.append(_check(f"2_mql5_static_{name}", ok, detail))

    settings = Settings()
    settings.bridge.directory = str(work / "bridge")
    settings.robot.log_dir = str(work / "logs")
    settings.robot.analyze_on_closed_bar_only = False
    settings.scoring.model_path = str(work / "smc_scorer.joblib")
    settings.scoring.use_ml = True
    settings.scoring.require_ml = False
    settings.scoring.ml_min_probability = 0.0
    rng = np.random.default_rng(3)
    X = rng.normal(size=(120, len(FEATURE_NAMES)))
    y = ((X[:, 3] + X[:, 11] + X[:, 10]) > 0.1).astype(int)
    y[0], y[1] = 0, 1
    train_model(X, y, settings.scoring.model_path)
    scorer = SetupScorer(settings)
    checks.append(_check("14_ml_model_loads", scorer._model is not None, settings.scoring.model_path))

    bridge = FileBridge(settings)
    executor = Mql5PaperExecutor(settings, bid=1999.5, ask=2000.0)
    stale = FileBridge(settings)
    stale.send_signal(_signal(Direction.BUY, 2000.0, 1990.0, 2020.0, "sig-stale-1"))
    stale_res = executor.process_once()["last_result"]
    checks.append(
        _check(
            "18_heartbeat_stale_rejects_buy",
            stale_res.get("error") == "python_disconnected",
            json.dumps(stale_res),
        )
    )

    bridge.heartbeat()
    executor.process_once()
    buy = _signal(Direction.BUY, 2000.0, 1990.0, 2020.0, "sig-buy-1")
    bridge.send_signal(buy)
    result = executor.process_once()
    last = result.get("last_result") or {}
    waited = bridge.wait_for_result("sig-buy-1", timeout=0.5)
    checks.append(_check("19_wait_for_fill", waited.get("error") == "filled", json.dumps(waited)))
    checks.append(_check("3_python_writes_mt5_command", bridge.command_path.exists(), str(bridge.command_path)))
    checks.append(_check("4_mql5_receives_signal", last.get("id") == "sig-buy-1", json.dumps(last)))
    checks.append(_check("5_buy_execution", last.get("ok") is True and last.get("error") == "filled", json.dumps(last)))
    checks.append(_check("7_sl_set", abs(float(last.get("sl") or 0) - 1990.0) < 1e-9, str(last.get("sl"))))
    checks.append(_check("8_tp_set", abs(float(last.get("tp") or 0) - 2020.0) < 1e-9, str(last.get("tp"))))

    sell_bridge_settings = Settings()
    sell_bridge_settings.bridge.directory = str(work / "bridge_sell")
    sell_bridge = FileBridge(sell_bridge_settings)
    sell_exec = Mql5PaperExecutor(sell_bridge_settings, bid=2000.0, ask=2000.4)
    sell_bridge.heartbeat()
    sell_exec.process_once()
    sell = _signal(Direction.SELL, 2000.0, 2010.0, 1980.0, "sig-sell-1")
    sell_bridge.send_signal(sell)
    sell_res = sell_exec.process_once()["last_result"]
    checks.append(_check("6_sell_execution", sell_res.get("ok") is True, json.dumps(sell_res)))

    paper = PaperBroker(balance=2000.0, bid=2000.0, ask=2000.2)
    manager = PositionManager(paper, settings)
    pos = paper.market_order("XAUUSDm", Direction.BUY, 0.02, 1990.0, 2020.0, 40, settings.risk.magic, "v")
    paper.set_quote(pos.entry + pos.initial_risk, pos.entry + pos.initial_risk + 0.2)
    manager.manage("XAUUSDm", paper.quote("XAUUSDm"))
    be_ok = abs(paper.positions[0].sl - pos.entry) < 1e-9
    checks.append(_check("9_breakeven", be_ok, str(paper.positions[0].sl)))
    paper.set_quote(pos.entry + 1.6 * pos.initial_risk, pos.entry + 1.6 * pos.initial_risk + 0.2)
    manager.manage("XAUUSDm", paper.quote("XAUUSDm"), structure_sl=pos.entry + 2.0)
    trail_ok = paper.positions[0].sl >= pos.entry + 1.9
    checks.append(_check("10_structure_trail", trail_ok, str(paper.positions[0].sl)))
    loosened = paper.positions[0].sl
    manager.manage("XAUUSDm", paper.quote("XAUUSDm"), structure_sl=pos.entry - 5.0)
    checks.append(
        _check(
            "20_trail_never_loosens",
            paper.positions[0].sl >= loosened,
            str(paper.positions[0].sl),
        )
    )

    h1 = bullish_structure_candles(n=96, minutes=60)
    m30 = bullish_structure_candles(n=96, minutes=30)
    m15 = m15_buy_setup()
    last_c = m15[-1]
    broker = PaperBroker(
        balance=2000.0,
        candles_by_tf={"H1": h1, "M30": m30, "M15": m15},
        bid=last_c.close - 0.1,
        ask=last_c.close,
        quote_time=datetime.now(timezone.utc),
    )
    live_settings = settings.model_copy(deep=True)
    live_settings.scoring.use_ml = False
    robot = SmcRobot(broker, live_settings, dry_run=False)
    first = robot.step()
    second = robot.step()
    checks.append(_check("11_one_position", first == "order_sent" and second == "manage_open_position", f"{first}->{second}"))

    daily = DailyGuard(settings)
    daily.settings.daily_risk.max_daily_loss_percent = 1.0
    daily.roll(datetime.now(timezone.utc), 1000.0)
    daily.record_close(-12.0, 4)
    allowed, reason = daily.allow(988.0)
    checks.append(_check("12_daily_risk_stop", allowed is False and reason == "max_daily_loss", reason))

    dup = FileBridge(settings)
    dup.heartbeat()
    executor.process_once()
    dup.send_signal(buy)
    again = executor.process_once()
    checks.append(_check("13_duplicate_blocked", again["last_result"].get("error") in {"duplicate", "duplicate_or_empty", "max_positions"}, json.dumps(again["last_result"])))

    from smc_robot.backtest import demo_series

    dh1, dm30, dm15 = demo_series()
    report = run_backtest(dh1, dm30, dm15, settings, start_index=90)
    payload = report.as_dict()
    checks.append(_check("15_backtest_metrics", "win_rate" in payload and "expectancy" in payload, json.dumps({k: payload[k] for k in ("total_trades", "win_rate", "expectancy")})))

    journal = DecisionJournal(str(work / "logs"))
    engine = SmcEngine(settings, scorer=scorer)
    decision = engine.evaluate(
        h1,
        m30,
        m15,
        Quote(bid=last_c.close - 0.1, ask=last_c.close, time=datetime.now(timezone.utc), spread_points=20),
        SymbolSpec(name="XAUUSDm"),
        2000.0,
        [20, 20, 21],
    )
    journal.write("XAUUSDm", decision, 20)
    log_ok = journal.file.exists() and journal.file.read_text(encoding="utf-8").strip()
    checks.append(_check("16_trade_logging", bool(log_ok), str(journal.file)))

    settings.robot.fail_closed = True
    empty = Settings()
    empty.bridge.directory = str(work / "dead_bridge")
    empty.robot.fail_closed = True
    dead = SmcRobot(PaperBroker(), empty, use_bridge=True)
    dead.bridge = FileBridge(empty)
    fail = dead.step()
    checks.append(_check("17_fail_closed_no_bridge", fail == "bridge_disconnected", fail))

    missing = engine.evaluate([], [], [], Quote(2000, 2000.2, datetime.now(timezone.utc), 20), SymbolSpec(name="XAUUSDm"), 1000)
    checks.append(_check("17b_fail_closed_missing_data", missing.action == "skip", missing.reason))

    from smc_robot.data.setups import bearish_structure_candles

    _ = bearish_structure_candles(n=96, minutes=60), m15_sell_setup()

    failed = [c for c in checks if not c["ok"]]
    return {
        "passed": len(failed) == 0,
        "passed_count": sum(1 for c in checks if c["ok"]),
        "failed_count": len(failed),
        "checks": checks,
        "note": "Linux cannot compile MetaEditor binaries. Check 2 is a static MQL5 guard. Live MT5 needs Windows.",
    }
