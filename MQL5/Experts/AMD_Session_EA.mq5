//+------------------------------------------------------------------+
//|                                              AMD_Session_EA.mq5  |
//|           Session-based Accumulation, Manipulation, Distribution |
//+------------------------------------------------------------------+
#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "ICT/SMC session AMD Expert Advisor. Accumulation range → liquidity sweep → market-structure confirmation → distribution entry."

#include <AMD/AMD_Enums.mqh>
#include <AMD/AMD_Config.mqh>
#include <AMD/AMD_Utils.mqh>
#include <AMD/AMD_Sessions.mqh>
#include <AMD/AMD_Liquidity.mqh>
#include <AMD/AMD_Structure.mqh>
#include <AMD/AMD_Trading.mqh>
#include <AMD/AMD_Visuals.mqh>

//--- General
input group "=== General ==="
input long               InpMagic              = 240824;           // Magic number
input string             InpComment            = "AMD_EA";         // Order comment
input bool               InpAllowBuy           = true;             // Allow BUY trades
input bool               InpAllowSell          = true;             // Allow SELL trades
input bool               InpTradeOnBarClose    = true;             // Evaluate on new LTF bar only
input bool               InpDebugLog           = false;            // Print debug logs

//--- Sessions (broker server time)
input group "=== Sessions (server time) ==="
input int                InpAsiaStartHour      = 0;                // Accumulation start hour
input int                InpAsiaStartMinute    = 0;                // Accumulation start minute
input int                InpAsiaEndHour        = 8;                // Accumulation end hour
input int                InpAsiaEndMinute      = 0;                // Accumulation end minute
input int                InpLondonStartHour    = 8;                // London start hour
input int                InpLondonStartMinute  = 0;                // London start minute
input int                InpLondonEndHour      = 12;               // London end hour
input int                InpLondonEndMinute    = 0;                // London end minute
input int                InpNYStartHour        = 12;               // New York start hour
input int                InpNYStartMinute      = 0;                // New York start minute
input int                InpNYEndHour          = 17;               // New York end hour
input int                InpNYEndMinute        = 0;                // New York end minute
input bool               InpTradeLondon        = true;             // Allow entries during London
input bool               InpTradeNewYork       = true;             // Allow entries during New York
input bool               InpCloseFriday        = true;             // Flatten before weekend
input int                InpFridayCloseHour    = 21;               // Friday flatten hour
input int                InpFridayCloseMinute  = 0;                // Friday flatten minute

//--- Timeframes / structure
input group "=== Timeframes & Structure ==="
input ENUM_TIMEFRAMES    InpHTF                = PERIOD_H1;        // Higher timeframe (bias)
input ENUM_TIMEFRAMES    InpLTF                = PERIOD_M5;        // Lower timeframe (entry)
input int                InpHtfLookback        = 80;               // HTF bars to scan
input int                InpLtfLookback        = 250;              // LTF bars to scan
input int                InpSwingStrength      = 2;                // Fractal swing strength
input int                InpEqualLookback      = 40;               // Bars for equal H/L scan
input double             InpEqualTolPoints     = 20;               // Equal H/L tolerance (points)
input ENUM_HTF_BIAS_MODE InpHtfBiasMode        = BIAS_OFF;         // HTF directional filter

//--- Accumulation / manipulation
input group "=== Accumulation & Liquidity Sweep ==="
input double             InpMinRangePoints     = 50;               // Min accumulation range (points)
input double             InpMaxRangePoints     = 800;              // Max accumulation range (0=off)
input int                InpMinAccBars         = 4;                // Min bars inside accumulation
input double             InpMinSweepPoints     = 5;                // Min pierce beyond the level
input double             InpSweepBufferPoints  = 0;                // Extra buffer beyond high/low
input ENUM_SWEEP_RETURN  InpSweepReturnMode    = RETURN_INSIDE_RANGE; // Sweep return rule
input bool               InpRequireRejection   = true;             // Require LH/HL rejection after sweep
input ENUM_CONFIRM_MODE  InpConfirmMode        = CONFIRM_BOS;      // Structure confirmation mode
input bool               InpRequireDisplacement= false;            // Require displacement candle
input double             InpDispAtrMult        = 0.8;              // Displacement body >= ATR *
input int                InpAtrPeriod          = 14;               // ATR period

//--- Entry
input group "=== Entry ==="
input ENUM_ENTRY_MODE    InpEntryMode          = ENTRY_MARKET;     // Entry style
input int                InpMaxBarsAfterMss    = 12;               // Expire setup after N LTF bars
input int                InpRetestMaxBars      = 8;                // Max bars to wait for retest/FVG
input double             InpFvgMinPoints       = 10;               // Ignore tiny FVGs

//--- Risk / money management
input group "=== Risk & Trade Management ==="
input ENUM_LOT_MODE      InpLotMode            = LOT_RISK_PERCENT; // Position sizing
input double             InpFixedLots          = 0.10;             // Fixed lot size
input double             InpRiskPercent        = 0.5;              // Risk percent of balance
input double             InpMaxLot             = 2.0;              // Cap on calculated lots
input double             InpSlBufferPoints     = 30;               // SL buffer beyond sweep extreme
input double             InpMaxSlPoints        = 400;              // Skip if SL wider than this
input double             InpMinSlPoints        = 40;               // Skip if SL tighter than this
input ENUM_TP_MODE       InpTpMode             = TP_HYBRID;        // Take-profit method
input double             InpRiskReward         = 2.0;              // RR multiple (1.5 / 2 / 3 / 4)
input bool               InpUsePartialClose    = true;             // Partial close enabled
input double             InpPartialPercent     = 50;               // Close this % at first target
input double             InpPartialRR          = 2.0;              // First partial at this RR
input bool               InpMoveBeAfterPartial = true;             // Move SL to BE after partial
input double             InpBeOffsetPoints     = 5;                // BE offset (points)
input int                InpMaxTradesPerDay    = 1;                // Daily trade cap
input int                InpMaxOpenPositions   = 1;                // Max concurrent positions
input bool               InpOneTradePerCycle   = true;             // One setup per AMD cycle

//--- Filters
input group "=== Quality Filters ==="
input double             InpMaxSpreadPoints    = 35;               // Max spread (points)
input double             InpMaxAtrPoints       = 0;                // Max ATR in points (0=off)
input double             InpMinAtrPoints       = 0;                // Min ATR in points (0=off)
input bool               InpSkipHighVol        = true;             // Skip abnormally high ATR
input double             InpVolAtrMult         = 2.5;              // High-vol if ATR > avg * this

//--- Visuals
input group "=== Chart Visuals ==="
input bool               InpShowVisuals        = true;             // Draw AMD objects
input bool               InpShowDashboard      = true;             // Show on-chart dashboard
input bool               InpShowLiqLabels      = true;             // Label liquidity levels

SAmdConfig         g_cfg;
CSessionManager    g_sessions;
CLiquidityEngine   g_liq;
CStructureEngine   g_structure;
CAmdTrader         g_trader;
CAmdVisuals        g_visuals;

ENUM_AMD_PHASE     g_phase          = PHASE_IDLE;
SSessionRange      g_range;
SSweepEvent        g_sweep;
SStructureShift    g_mss;
SPendingSetup      g_pending;
SHtfBias           g_bias;
datetime           g_cycleStart     = 0;
datetime           g_lastLtfBar     = 0;
string             g_lastMsg        = "";
double             g_lastEntry      = 0;
double             g_lastSl         = 0;
double             g_lastTp         = 0;
ENUM_TRADE_DIR     g_lastDir        = DIR_NONE;
datetime           g_lastTradeTime  = 0;
int                g_atrHandle      = INVALID_HANDLE;

//+------------------------------------------------------------------+
void FillConfig(void)
  {
   g_cfg.magic                 = InpMagic;
   g_cfg.tradeComment          = InpComment;
   g_cfg.allowBuy              = InpAllowBuy;
   g_cfg.allowSell             = InpAllowSell;
   g_cfg.asiaStartHour         = InpAsiaStartHour;
   g_cfg.asiaStartMinute       = InpAsiaStartMinute;
   g_cfg.asiaEndHour           = InpAsiaEndHour;
   g_cfg.asiaEndMinute         = InpAsiaEndMinute;
   g_cfg.londonStartHour       = InpLondonStartHour;
   g_cfg.londonStartMinute     = InpLondonStartMinute;
   g_cfg.londonEndHour         = InpLondonEndHour;
   g_cfg.londonEndMinute       = InpLondonEndMinute;
   g_cfg.nyStartHour           = InpNYStartHour;
   g_cfg.nyStartMinute         = InpNYStartMinute;
   g_cfg.nyEndHour             = InpNYEndHour;
   g_cfg.nyEndMinute           = InpNYEndMinute;
   g_cfg.tradeLondon           = InpTradeLondon;
   g_cfg.tradeNewYork          = InpTradeNewYork;
   g_cfg.closeFriday           = InpCloseFriday;
   g_cfg.fridayCloseHour       = InpFridayCloseHour;
   g_cfg.fridayCloseMinute     = InpFridayCloseMinute;
   g_cfg.htf                   = InpHTF;
   g_cfg.ltf                   = InpLTF;
   g_cfg.htfLookback           = InpHtfLookback;
   g_cfg.ltfLookback           = InpLtfLookback;
   g_cfg.swingStrength         = InpSwingStrength;
   g_cfg.equalLookback         = InpEqualLookback;
   g_cfg.equalTolerancePoints  = InpEqualTolPoints;
   g_cfg.htfBiasMode           = InpHtfBiasMode;
   g_cfg.minRangePoints        = InpMinRangePoints;
   g_cfg.maxRangePoints        = InpMaxRangePoints;
   g_cfg.minAccBars            = InpMinAccBars;
   g_cfg.minSweepPoints        = InpMinSweepPoints;
   g_cfg.sweepBufferPoints     = InpSweepBufferPoints;
   g_cfg.sweepReturnMode       = InpSweepReturnMode;
   g_cfg.requireRejection      = InpRequireRejection;
   g_cfg.confirmMode           = InpConfirmMode;
   g_cfg.requireDisplacement   = InpRequireDisplacement;
   g_cfg.displacementAtrMult   = InpDispAtrMult;
   g_cfg.atrPeriod             = InpAtrPeriod;
   g_cfg.entryMode             = InpEntryMode;
   g_cfg.maxBarsAfterMss       = InpMaxBarsAfterMss;
   g_cfg.retestMaxBars         = InpRetestMaxBars;
   g_cfg.fvgMinPoints          = InpFvgMinPoints;
   g_cfg.lotMode               = InpLotMode;
   g_cfg.fixedLots             = InpFixedLots;
   g_cfg.riskPercent           = InpRiskPercent;
   g_cfg.maxLot                = InpMaxLot;
   g_cfg.slBufferPoints        = InpSlBufferPoints;
   g_cfg.maxSlPoints           = InpMaxSlPoints;
   g_cfg.minSlPoints           = InpMinSlPoints;
   g_cfg.tpMode                = InpTpMode;
   g_cfg.riskReward            = InpRiskReward;
   g_cfg.usePartialClose       = InpUsePartialClose;
   g_cfg.partialClosePercent   = InpPartialPercent;
   g_cfg.partialCloseRR        = InpPartialRR;
   g_cfg.moveBeAfterPartial    = InpMoveBeAfterPartial;
   g_cfg.beOffsetPoints        = InpBeOffsetPoints;
   g_cfg.maxTradesPerDay       = InpMaxTradesPerDay;
   g_cfg.maxOpenPositions      = InpMaxOpenPositions;
   g_cfg.oneTradePerCycle      = InpOneTradePerCycle;
   g_cfg.maxSpreadPoints       = InpMaxSpreadPoints;
   g_cfg.maxAtrPoints          = InpMaxAtrPoints;
   g_cfg.minAtrPoints          = InpMinAtrPoints;
   g_cfg.skipHighVolatility    = InpSkipHighVol;
   g_cfg.volatilityAtrMult     = InpVolAtrMult;
   g_cfg.showVisuals           = InpShowVisuals;
   g_cfg.showDashboard         = InpShowDashboard;
   g_cfg.showLiquidityLabels   = InpShowLiqLabels;
   g_cfg.debugLog              = InpDebugLog;
   g_cfg.tradeOnBarClose       = InpTradeOnBarClose;
  }

void ResetCycle(const datetime newStart, const string why)
  {
   g_phase       = PHASE_IDLE;
   ZeroMemory(g_range);
   ZeroMemory(g_sweep);
   ZeroMemory(g_mss);
   ZeroMemory(g_pending);
   g_cycleStart  = newStart;
   g_lastMsg     = why;
   g_trader.ResetCycleFlags();
   DebugPrint(g_cfg, "Cycle reset: " + why);
  }

bool LoadLtf(MqlRates &rates[], int &copied)
  {
   ArraySetAsSeries(rates, true);
   copied = CopyRates(_Symbol, g_cfg.ltf, 0, g_cfg.ltfLookback, rates);
   return(copied > g_cfg.swingStrength * 4);
  }

double LtfAtr(void)
  {
   if(g_atrHandle == INVALID_HANDLE)
      return(0.0);
   double buf[];
   if(CopyBuffer(g_atrHandle, 0, 0, 1, buf) < 1)
      return(0.0);
   return(buf[0]);
  }

bool PassesFilters(string &reason)
  {
   const double spread = CurrentSpreadPoints(_Symbol);
   if(g_cfg.maxSpreadPoints > 0.0 && spread > g_cfg.maxSpreadPoints)
     {
      reason = "Spread too high (" + DoubleToString(spread, 1) + ")";
      return(false);
     }

   const double atr = LtfAtr();
   const double atrPts = PriceToPoints(_Symbol, atr);
   if(g_cfg.maxAtrPoints > 0.0 && atrPts > g_cfg.maxAtrPoints)
     {
      reason = "ATR too high";
      return(false);
     }
   if(g_cfg.minAtrPoints > 0.0 && atrPts < g_cfg.minAtrPoints)
     {
      reason = "ATR too low";
      return(false);
     }
   if(g_cfg.skipHighVolatility && g_atrHandle != INVALID_HANDLE)
     {
      double buf[];
      const int n = 50;
      if(CopyBuffer(g_atrHandle, 0, 0, n, buf) >= n)
        {
         double sum = 0.0;
         for(int i = 0; i < n; i++)
            sum += buf[i];
         const double avg = sum / n;
         if(avg > 0.0 && atr > avg * g_cfg.volatilityAtrMult)
           {
            reason = "Abnormal volatility";
            return(false);
           }
        }
     }
   if(!g_sessions.InTradeWindow(TimeCurrent()))
     {
      reason = "Outside permitted trading session";
      return(false);
     }
   if(g_trader.CountTodayDeals(TimeCurrent()) >= g_cfg.maxTradesPerDay)
     {
      reason = "Max trades already reached";
      return(false);
     }
   reason = "";
   return(true);
  }

bool PriceTouchesZone(const MqlRates &bar, const double zHigh, const double zLow)
  {
   return(!(bar.low > zHigh || bar.high < zLow));
  }

void ArmSetup(const MqlRates &ltf[])
  {
   g_pending.armed         = true;
   g_pending.dir           = g_mss.dir;
   g_pending.tArmed        = ltf[1].time;
   g_pending.barsWaited    = 0;
   g_pending.entryZoneHigh = g_mss.entryZoneHigh;
   g_pending.entryZoneLow  = g_mss.entryZoneLow;
   g_pending.slPrice       = g_trader.SlFromSweep(g_mss.dir, g_sweep);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double entryPx = (g_mss.dir == DIR_BUY ? ask : bid);
   g_pending.liquidityTarget = g_liq.NextLiquidityTarget(g_mss.dir, entryPx, g_range);
   g_pending.tpPrice = g_trader.TpFromMode(g_mss.dir, entryPx, g_pending.slPrice, g_pending.liquidityTarget);
   g_phase = PHASE_CONFIRMATION;
   g_lastMsg = "Structure confirmed. Setup armed (" + DirToString(g_mss.dir) + ")";
   DebugPrint(g_cfg, g_lastMsg);
  }

void TryEnter(const MqlRates &ltf[])
  {
   if(!g_pending.armed)
      return;
   if(g_cfg.oneTradePerCycle && g_phase == PHASE_CYCLE_COMPLETE)
      return;

   string reason;
   if(!PassesFilters(reason))
     {
      g_lastMsg = reason;
      return;
     }
   if(!g_structure.DirectionAllowed(g_pending.dir, g_bias))
     {
      g_lastMsg = "HTF bias filter blocked " + DirToString(g_pending.dir);
      return;
     }

   bool fire = false;
   if(g_cfg.entryMode == ENTRY_MARKET)
      fire = true;
   else
     {
      if(PriceTouchesZone(ltf[1], g_pending.entryZoneHigh, g_pending.entryZoneLow) ||
         PriceTouchesZone(ltf[0], g_pending.entryZoneHigh, g_pending.entryZoneLow))
         fire = true;
      g_pending.barsWaited++;
      if(!fire && g_pending.barsWaited > g_cfg.retestMaxBars)
        {
         g_lastMsg = "Retest/FVG timeout — setup cancelled";
         g_pending.armed = false;
         g_phase = PHASE_RANGE_SET;
         ZeroMemory(g_sweep);
         ZeroMemory(g_mss);
         return;
        }
     }

   if(g_cfg.maxBarsAfterMss > 0 && g_pending.barsWaited > g_cfg.maxBarsAfterMss)
     {
      g_lastMsg = "Confirmation expired";
      g_pending.armed = false;
      return;
     }

   if(!fire)
      return;

   const string cmt = g_cfg.tradeComment + " " + DirToString(g_pending.dir);
   if(!g_trader.OpenTrade(g_pending.dir, g_pending.slPrice, g_pending.tpPrice, cmt, reason))
     {
      g_lastMsg = "Entry skipped: " + reason;
      DebugPrint(g_cfg, g_lastMsg);
      // Permanent skip only when SL/risk is invalid; keep waiting on spread blips
      if(StringFind(reason, "SL ") >= 0 || StringFind(reason, "Lot size") >= 0)
        {
         g_pending.armed = false;
         g_phase = PHASE_CYCLE_COMPLETE;
        }
      return;
     }

   g_lastDir       = g_pending.dir;
   g_lastEntry     = (g_pending.dir == DIR_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                               : SymbolInfoDouble(_Symbol, SYMBOL_BID));
   g_lastSl        = g_pending.slPrice;
   g_lastTp        = g_pending.tpPrice;
   g_lastTradeTime = TimeCurrent();
   g_pending.armed = false;
   g_phase         = (g_cfg.oneTradePerCycle ? PHASE_CYCLE_COMPLETE : PHASE_IN_TRADE);
   g_lastMsg       = "DISTRIBUTION entry " + DirToString(g_lastDir);
   g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
   DebugPrint(g_cfg, g_lastMsg);
  }

void ProcessLogic(void)
  {
   const datetime now = TimeCurrent();
   datetime accStart = 0, accEnd = 0;
   g_sessions.AccumulationBounds(now, accStart, accEnd);
   if(accStart != 0 && accStart != g_cycleStart)
      ResetCycle(accStart, "New accumulation session");

   MqlRates ltf[];
   int copied = 0;
   if(!LoadLtf(ltf, copied))
     {
      g_lastMsg = "Not enough LTF bars";
      return;
     }

   g_bias = g_structure.ComputeHtfBias();
   g_sessions.BuildRange(now, g_range);

   const ENUM_SESSION_KIND session = g_sessions.CurrentSession(now);

   if(g_trader.HasOpenPosition())
     {
      if(g_phase != PHASE_CYCLE_COMPLETE)
         g_phase = PHASE_IN_TRADE;
     }
   else if(g_phase == PHASE_IN_TRADE && !g_cfg.oneTradePerCycle)
      g_phase = PHASE_RANGE_SET;

   // --- Phase machine ---
   if(session == SESSION_ASIA)
     {
      if(g_phase == PHASE_IDLE || g_phase == PHASE_RANGE_INVALID || g_phase == PHASE_RANGE_SET)
         g_phase = PHASE_ACCUMULATION;
     }
   else
     {
      if(g_range.valid && (g_phase == PHASE_IDLE || g_phase == PHASE_ACCUMULATION))
         g_phase = PHASE_RANGE_SET;
      else if(!g_range.valid && g_range.complete &&
              (g_phase == PHASE_IDLE || g_phase == PHASE_ACCUMULATION))
        {
         g_phase = PHASE_RANGE_INVALID;
         g_lastMsg = "Accumulation range rejected by size/bar filters";
        }
     }

   if(g_range.valid)
      g_liq.BuildFromRange(g_range, ltf, copied);

   // Never assume a sweep. Wait for actual price action on closed (or current) bars.
   if(g_range.valid &&
      g_phase != PHASE_CYCLE_COMPLETE &&
      g_phase != PHASE_RANGE_INVALID &&
      g_phase != PHASE_ACCUMULATION)
     {
      const MqlRates bar = ltf[g_cfg.tradeOnBarClose ? 1 : 0];

      if(!g_sweep.active)
        {
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, g_range, ev))
           {
            g_sweep = ev;
            g_phase = PHASE_MANIPULATION;
            g_lastMsg = "Liquidity sweep detected (" + DirToString(g_sweep.setupDir) + ")";
            DebugPrint(g_cfg, g_lastMsg);
            ZeroMemory(g_mss);
            ZeroMemory(g_pending);
           }
        }
      else
        {
         // Opposite sweep replaces the working idea only if the first
         // sweep never rejected. A later take of the other side after
         // a rejection is distribution toward liquidity, not a new Judas.
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, g_range, ev) &&
            ev.setupDir != g_sweep.setupDir &&
            !g_sweep.returned)
           {
            g_sweep = ev;
            g_phase = PHASE_MANIPULATION;
            g_lastMsg = "Opposite sweep — working direction flipped to " + DirToString(g_sweep.setupDir);
            ZeroMemory(g_mss);
            ZeroMemory(g_pending);
           }
         else
           {
            if(g_sweep.setupDir == DIR_SELL && bar.high > g_sweep.extreme)
               g_sweep.extreme = bar.high;
            if(g_sweep.setupDir == DIR_BUY && bar.low < g_sweep.extreme)
               g_sweep.extreme = bar.low;
            g_liq.UpdateReturn(bar, g_range, g_sweep);
           }
        }

      if(g_sweep.active && g_sweep.returned && !g_mss.confirmed && !g_pending.armed)
        {
         const double atr = LtfAtr();
         if(g_structure.ConfirmShift(ltf, copied, g_sweep, g_range, atr, g_mss))
            ArmSetup(ltf);
         else
            g_lastMsg = "Sweep returned — waiting for market-structure confirmation";
        }
     }

   if(g_pending.armed)
      TryEnter(ltf);

   g_visuals.DrawRange(g_range);
   g_visuals.DrawSweep(g_sweep, g_range);
   g_visuals.DrawMss(g_mss);
   if(g_lastDir != DIR_NONE)
      g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
   g_visuals.DrawDashboard(session, g_phase, g_range, g_bias, g_sweep, g_lastMsg);
  }

int OnInit()
  {
   FillConfig();
   g_sessions.Init(g_cfg, _Symbol, InpLTF);
   g_liq.Init(g_cfg, _Symbol);
   g_structure.Init(g_cfg, _Symbol);
   g_trader.Init(g_cfg, _Symbol);
   g_visuals.Init(g_cfg, _Symbol);

   g_atrHandle = iATR(_Symbol, InpLTF, InpAtrPeriod);
   if(g_atrHandle == INVALID_HANDLE)
     {
      Print("Failed to create ATR handle");
      return(INIT_FAILED);
     }

   ResetCycle(0, "Init");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   g_visuals.DeleteAll();
   Comment("");
  }

void OnTick()
  {
   g_trader.ManageOpenTrades();

   bool run = true;
   if(g_cfg.tradeOnBarClose)
      run = IsNewBar(_Symbol, g_cfg.ltf, g_lastLtfBar);

   // Always refresh the dashboard / live range while accumulating
   if(!run)
     {
      const datetime now = TimeCurrent();
      if(g_sessions.CurrentSession(now) == SESSION_ASIA)
        {
         g_sessions.BuildRange(now, g_range);
         g_phase = PHASE_ACCUMULATION;
         g_visuals.DrawRange(g_range);
         g_visuals.DrawDashboard(SESSION_ASIA, g_phase, g_range, g_bias, g_sweep, g_lastMsg);
        }
      return;
     }

   ProcessLogic();
  }

void OnTimer()
  {
  }
