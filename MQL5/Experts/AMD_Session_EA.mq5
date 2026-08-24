//+------------------------------------------------------------------+
//|                                              AMD_Session_EA.mq5  |
//|     XAUUSDm AMD bot — M15 / M30 / H1, one setup, scaled lots     |
//+------------------------------------------------------------------+
#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.10"
#property description "XAUUSDm session AMD EA. Scans M15, M30 and H1, takes one confirmed setup, starts at 0.01 lots and scales with balance. Dashboard is readable on white charts."

#include <AMD/AMD_Enums.mqh>
#include <AMD/AMD_Config.mqh>
#include <AMD/AMD_Utils.mqh>
#include <AMD/AMD_Sessions.mqh>
#include <AMD/AMD_Liquidity.mqh>
#include <AMD/AMD_Structure.mqh>
#include <AMD/AMD_Trading.mqh>
#include <AMD/AMD_Visuals.mqh>

#define AMD_TF_COUNT 3

input group "=== General ==="
input string             InpTradeSymbol        = "XAUUSDm";        // Trade this symbol only
input long               InpMagic              = 240824;
input string             InpComment            = "AMD_XAU";
input bool               InpAllowBuy           = true;
input bool               InpAllowSell          = true;
input bool               InpTradeOnBarClose    = true;
input bool               InpDebugLog           = false;

input group "=== Setup timeframes ==="
input bool               InpUseH1              = true;             // Scan H1
input bool               InpUseM30             = true;             // Scan M30
input bool               InpUseM15             = true;             // Scan M15
input ENUM_TF_PRIORITY   InpTfPriority         = TF_PRIORITY_H1;   // Which TF wins if several are ready

input group "=== Sessions (server time) ==="
input int                InpAsiaStartHour      = 0;
input int                InpAsiaStartMinute    = 0;
input int                InpAsiaEndHour        = 8;
input int                InpAsiaEndMinute      = 0;
input int                InpLondonStartHour    = 8;
input int                InpLondonStartMinute  = 0;
input int                InpLondonEndHour      = 12;
input int                InpLondonEndMinute    = 0;
input int                InpNYStartHour        = 12;
input int                InpNYStartMinute      = 0;
input int                InpNYEndHour          = 17;
input int                InpNYEndMinute        = 0;
input bool               InpTradeLondon        = true;
input bool               InpTradeNewYork       = true;
input bool               InpCloseFriday        = true;
input int                InpFridayCloseHour    = 21;
input int                InpFridayCloseMinute  = 0;

input group "=== Timeframes & Structure ==="
input ENUM_TIMEFRAMES    InpHTF                = PERIOD_H4;        // Optional higher-TF bias
input int                InpHtfLookback        = 80;
input int                InpLtfLookback        = 250;
input int                InpSwingStrength      = 2;
input int                InpEqualLookback      = 40;
input double             InpEqualTolPoints     = 30;
input ENUM_HTF_BIAS_MODE InpHtfBiasMode        = BIAS_OFF;

input group "=== Accumulation & Liquidity Sweep ==="
input double             InpMinRangePoints     = 300;              // Gold: min Asia range (points)
input double             InpMaxRangePoints     = 8000;             // Gold: max Asia range (0=off)
input int                InpMinAccBars         = 3;
input double             InpMinSweepPoints     = 20;
input double             InpSweepBufferPoints  = 0;
input ENUM_SWEEP_RETURN  InpSweepReturnMode    = RETURN_INSIDE_RANGE;
input bool               InpRequireRejection   = true;
input ENUM_CONFIRM_MODE  InpConfirmMode        = CONFIRM_BOS;
input bool               InpRequireDisplacement= false;
input double             InpDispAtrMult        = 0.8;
input int                InpAtrPeriod          = 14;

input group "=== Entry ==="
input ENUM_ENTRY_MODE    InpEntryMode          = ENTRY_MARKET;
input int                InpMaxBarsAfterMss    = 12;
input int                InpRetestMaxBars      = 8;
input double             InpFvgMinPoints       = 10;

input group "=== Risk & Trade Management ==="
input ENUM_LOT_MODE      InpLotMode            = LOT_BALANCE_SCALE;// 0.01 then scale with balance
input double             InpStartLots          = 0.01;             // Starting lot
input double             InpBalancePerLot      = 100.0;            // Add 0.01 lot per this balance
input double             InpFixedLots          = 0.01;
input double             InpRiskPercent        = 0.5;
input double             InpMaxLot             = 2.0;
input double             InpSlBufferPoints     = 80;
input double             InpMaxSlPoints        = 3000;
input double             InpMinSlPoints        = 50;
input ENUM_TP_MODE       InpTpMode             = TP_HYBRID;
input double             InpRiskReward         = 2.0;
input bool               InpUsePartialClose    = true;
input double             InpPartialPercent     = 50;
input double             InpPartialRR          = 2.0;
input bool               InpMoveBeAfterPartial = true;
input double             InpBeOffsetPoints     = 10;
input int                InpMaxTradesPerDay    = 1;
input int                InpMaxOpenPositions   = 1;
input bool               InpOneTradePerCycle   = true;

input group "=== Quality Filters ==="
input double             InpMaxSpreadPoints    = 80;
input double             InpMaxAtrPoints       = 0;
input double             InpMinAtrPoints       = 0;
input bool               InpSkipHighVol        = true;
input double             InpVolAtrMult         = 2.5;

input group "=== Chart Visuals ==="
input bool               InpShowVisuals        = true;
input bool               InpShowDashboard      = true;
input ENUM_DASH_THEME    InpDashTheme          = DASH_LIGHT;       // Light panel for white charts
input bool               InpShowLiqLabels      = true;

struct STfState
  {
   ENUM_TIMEFRAMES   tf;
   bool              enabled;
   datetime          lastBar;
   int               atrHandle;
   ENUM_AMD_PHASE    phase;
   SSessionRange     range;
   SSweepEvent       sweep;
   SStructureShift   mss;
   SPendingSetup     pending;
  };

SAmdConfig         g_cfg;
CSessionManager    g_sessions;
CLiquidityEngine   g_liq;
CStructureEngine   g_structure;
CAmdTrader         g_trader;
CAmdVisuals        g_visuals;

STfState           g_tf[AMD_TF_COUNT];
SHtfBias           g_bias;
datetime           g_cycleStart     = 0;
string             g_lastMsg        = "";
double             g_lastEntry      = 0;
double             g_lastSl         = 0;
double             g_lastTp         = 0;
ENUM_TRADE_DIR     g_lastDir        = DIR_NONE;
datetime           g_lastTradeTime  = 0;

void FillConfig(void)
  {
   g_cfg.magic                 = InpMagic;
   g_cfg.tradeComment          = InpComment;
   g_cfg.tradeSymbol           = InpTradeSymbol;
   g_cfg.allowBuy              = InpAllowBuy;
   g_cfg.allowSell             = InpAllowSell;
   g_cfg.useM15                = InpUseM15;
   g_cfg.useM30                = InpUseM30;
   g_cfg.useH1                 = InpUseH1;
   g_cfg.tfPriority            = InpTfPriority;
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
   g_cfg.ltf                   = PERIOD_M15;
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
   g_cfg.startLots             = InpStartLots;
   g_cfg.balancePerLot         = InpBalancePerLot;
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
   g_cfg.dashTheme             = InpDashTheme;
   g_cfg.debugLog              = InpDebugLog;
   g_cfg.tradeOnBarClose       = InpTradeOnBarClose;
  }

void ResetTf(STfState &st)
  {
   st.phase = PHASE_IDLE;
   ZeroMemory(st.range);
   ZeroMemory(st.sweep);
   ZeroMemory(st.mss);
   ZeroMemory(st.pending);
  }

void ResetCycle(const datetime newStart, const string why)
  {
   for(int i = 0; i < AMD_TF_COUNT; i++)
      ResetTf(g_tf[i]);
   g_cycleStart = newStart;
   g_lastMsg    = why;
   g_trader.ResetCycleFlags();
   DebugPrint(g_cfg, "Cycle reset: " + why);
  }

bool LoadRates(const ENUM_TIMEFRAMES tf, MqlRates &rates[], int &copied)
  {
   ArraySetAsSeries(rates, true);
   copied = CopyRates(_Symbol, tf, 0, g_cfg.ltfLookback, rates);
   return(copied > g_cfg.swingStrength * 4);
  }

double TfAtr(const STfState &st)
  {
   if(st.atrHandle == INVALID_HANDLE)
      return(0.0);
   double buf[];
   if(CopyBuffer(st.atrHandle, 0, 0, 1, buf) < 1)
      return(0.0);
   return(buf[0]);
  }

bool PassesFilters(const STfState &st, string &reason)
  {
   const double spread = CurrentSpreadPoints(_Symbol);
   if(g_cfg.maxSpreadPoints > 0.0 && spread > g_cfg.maxSpreadPoints)
     {
      reason = "Spread too high (" + DoubleToString(spread, 1) + ")";
      return(false);
     }

   const double atr = TfAtr(st);
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
   if(g_cfg.skipHighVolatility && st.atrHandle != INVALID_HANDLE)
     {
      double buf[];
      const int n = 50;
      if(CopyBuffer(st.atrHandle, 0, 0, n, buf) >= n)
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

string TfStatus(const STfState &st)
  {
   if(!st.enabled)
      return("off");
   string s = PhaseToString(st.phase);
   if(st.sweep.active)
      s += " " + DirToString(st.sweep.setupDir);
   if(st.sweep.returned)
      s += " returned";
   if(st.pending.armed)
      s += " ARMED";
   return(s);
  }

void ArmSetup(STfState &st, const MqlRates &rates[])
  {
   st.pending.armed         = true;
   st.pending.dir           = st.mss.dir;
   st.pending.tArmed        = rates[1].time;
   st.pending.barsWaited    = 0;
   st.pending.entryZoneHigh = st.mss.entryZoneHigh;
   st.pending.entryZoneLow  = st.mss.entryZoneLow;
   st.pending.slPrice       = g_trader.SlFromSweep(st.mss.dir, st.sweep);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double entryPx = (st.mss.dir == DIR_BUY ? ask : bid);
   st.pending.liquidityTarget = g_liq.NextLiquidityTarget(st.mss.dir, entryPx, st.range);
   st.pending.tpPrice = g_trader.TpFromMode(st.mss.dir, entryPx, st.pending.slPrice, st.pending.liquidityTarget);
   st.phase = PHASE_CONFIRMATION;
   g_lastMsg = TfToString(st.tf) + " structure confirmed (" + DirToString(st.mss.dir) + ")";
   DebugPrint(g_cfg, g_lastMsg);
  }

bool TryEnter(STfState &st, const MqlRates &rates[])
  {
   if(!st.pending.armed)
      return(false);
   if(g_cfg.oneTradePerCycle && g_trader.HasOpenPosition())
      return(false);

   string reason;
   if(!PassesFilters(st, reason))
     {
      g_lastMsg = TfToString(st.tf) + " " + reason;
      return(false);
     }
   if(!g_structure.DirectionAllowed(st.pending.dir, g_bias))
     {
      g_lastMsg = TfToString(st.tf) + " HTF bias blocked " + DirToString(st.pending.dir);
      return(false);
     }

   bool fire = false;
   if(g_cfg.entryMode == ENTRY_MARKET)
      fire = true;
   else
     {
      if(PriceTouchesZone(rates[1], st.pending.entryZoneHigh, st.pending.entryZoneLow) ||
         PriceTouchesZone(rates[0], st.pending.entryZoneHigh, st.pending.entryZoneLow))
         fire = true;
      st.pending.barsWaited++;
      if(!fire && st.pending.barsWaited > g_cfg.retestMaxBars)
        {
         g_lastMsg = TfToString(st.tf) + " retest timeout";
         st.pending.armed = false;
         st.phase = PHASE_RANGE_SET;
         ZeroMemory(st.sweep);
         ZeroMemory(st.mss);
         return(false);
        }
     }

   if(g_cfg.maxBarsAfterMss > 0 && st.pending.barsWaited > g_cfg.maxBarsAfterMss)
     {
      g_lastMsg = TfToString(st.tf) + " confirmation expired";
      st.pending.armed = false;
      return(false);
     }

   if(!fire)
      return(false);

   const string cmt = g_cfg.tradeComment + " " + TfToString(st.tf) + " " + DirToString(st.pending.dir);
   if(!g_trader.OpenTrade(st.pending.dir, st.pending.slPrice, st.pending.tpPrice, cmt, reason))
     {
      g_lastMsg = TfToString(st.tf) + " skipped: " + reason;
      DebugPrint(g_cfg, g_lastMsg);
      if(StringFind(reason, "SL ") >= 0 || StringFind(reason, "Lot size") >= 0)
        {
         st.pending.armed = false;
         st.phase = PHASE_CYCLE_COMPLETE;
        }
      return(false);
     }

   g_lastDir       = st.pending.dir;
   g_lastEntry     = (st.pending.dir == DIR_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                                : SymbolInfoDouble(_Symbol, SYMBOL_BID));
   g_lastSl        = st.pending.slPrice;
   g_lastTp        = st.pending.tpPrice;
   g_lastTradeTime = TimeCurrent();
   st.pending.armed = false;
   st.phase         = PHASE_CYCLE_COMPLETE;
   if(g_cfg.oneTradePerCycle)
     {
      for(int i = 0; i < AMD_TF_COUNT; i++)
        {
         g_tf[i].pending.armed = false;
         g_tf[i].phase = PHASE_CYCLE_COMPLETE;
        }
     }
   g_lastMsg = "DISTRIBUTION " + TfToString(st.tf) + " " + DirToString(g_lastDir) +
               " lot " + DoubleToString(g_trader.PreviewLot(), 2);
   g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
   DebugPrint(g_cfg, g_lastMsg);
   return(true);
  }

void ProcessTf(STfState &st)
  {
   if(!st.enabled)
      return;

   const datetime now = TimeCurrent();
   MqlRates rates[];
   int copied = 0;
   if(!LoadRates(st.tf, rates, copied))
      return;

   g_sessions.BuildRange(now, st.range, st.tf);
   const ENUM_SESSION_KIND session = g_sessions.CurrentSession(now);

   if(g_trader.HasOpenPosition() && st.phase != PHASE_CYCLE_COMPLETE)
      st.phase = PHASE_IN_TRADE;
   else if(st.phase == PHASE_IN_TRADE && !g_cfg.oneTradePerCycle)
      st.phase = PHASE_RANGE_SET;

   if(session == SESSION_ASIA)
     {
      if(st.phase == PHASE_IDLE || st.phase == PHASE_RANGE_INVALID || st.phase == PHASE_RANGE_SET)
         st.phase = PHASE_ACCUMULATION;
     }
   else
     {
      if(st.range.valid && (st.phase == PHASE_IDLE || st.phase == PHASE_ACCUMULATION))
         st.phase = PHASE_RANGE_SET;
      else if(!st.range.valid && st.range.complete &&
              (st.phase == PHASE_IDLE || st.phase == PHASE_ACCUMULATION))
        {
         st.phase = PHASE_RANGE_INVALID;
        }
     }

   if(st.range.valid)
      g_liq.BuildFromRange(st.range, rates, copied);

   if(st.range.valid &&
      st.phase != PHASE_CYCLE_COMPLETE &&
      st.phase != PHASE_RANGE_INVALID &&
      st.phase != PHASE_ACCUMULATION)
     {
      const MqlRates bar = rates[g_cfg.tradeOnBarClose ? 1 : 0];

      if(!st.sweep.active)
        {
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, st.range, ev))
           {
            st.sweep = ev;
            st.phase = PHASE_MANIPULATION;
            g_lastMsg = TfToString(st.tf) + " liquidity sweep (" + DirToString(st.sweep.setupDir) + ")";
            ZeroMemory(st.mss);
            ZeroMemory(st.pending);
           }
        }
      else
        {
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, st.range, ev) &&
            ev.setupDir != st.sweep.setupDir &&
            !st.sweep.returned)
           {
            st.sweep = ev;
            st.phase = PHASE_MANIPULATION;
            g_lastMsg = TfToString(st.tf) + " opposite sweep -> " + DirToString(st.sweep.setupDir);
            ZeroMemory(st.mss);
            ZeroMemory(st.pending);
           }
         else
           {
            if(st.sweep.setupDir == DIR_SELL && bar.high > st.sweep.extreme)
               st.sweep.extreme = bar.high;
            if(st.sweep.setupDir == DIR_BUY && bar.low < st.sweep.extreme)
               st.sweep.extreme = bar.low;
            g_liq.UpdateReturn(bar, st.range, st.sweep);
           }
        }

      if(st.sweep.active && st.sweep.returned && !st.mss.confirmed && !st.pending.armed)
        {
         const double atr = TfAtr(st);
         if(g_structure.ConfirmShift(rates, copied, st.sweep, st.range, atr, st.mss))
            ArmSetup(st, rates);
         else
            g_lastMsg = TfToString(st.tf) + " waiting for market-structure confirmation";
        }
     }

   const color fill = (st.tf == PERIOD_H1 ? C'30,90,160' : (st.tf == PERIOD_M30 ? C'20,120,110' : C'90,90,140'));
   g_visuals.DrawRange(st.range, TfToString(st.tf), fill);
   g_visuals.DrawSweep(st.sweep, st.range, TfToString(st.tf));
   g_visuals.DrawMss(st.mss, TfToString(st.tf));
  }

int PriorityIndex(const int slot)
  {
   // slot 0 = first to try
   if(g_cfg.tfPriority == TF_PRIORITY_M30)
     {
      if(slot == 0) return(1);
      if(slot == 1) return(0);
      return(2);
     }
   if(g_cfg.tfPriority == TF_PRIORITY_M15)
     {
      if(slot == 0) return(2);
      if(slot == 1) return(1);
      return(0);
     }
   return(slot); // H1, M30, M15 stored in that order
  }

void RefreshDashboard(void)
  {
   SSessionRange shown = g_tf[0].range;
   if(!shown.valid)
      shown = g_tf[1].range;
   if(!shown.valid)
      shown = g_tf[2].range;
   g_visuals.DrawDashboard(g_sessions.CurrentSession(TimeCurrent()),
                           TfStatus(g_tf[0]), TfStatus(g_tf[1]), TfStatus(g_tf[2]),
                           shown, g_bias, g_trader.PreviewLot(), g_lastMsg);
   if(g_lastDir != DIR_NONE)
      g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
  }

void ProcessLogic(void)
  {
   const datetime now = TimeCurrent();
   datetime accStart = 0, accEnd = 0;
   g_sessions.AccumulationBounds(now, accStart, accEnd);
   if(accStart != 0 && accStart != g_cycleStart)
      ResetCycle(accStart, "New accumulation session");

   g_bias = g_structure.ComputeHtfBias();

   for(int i = 0; i < AMD_TF_COUNT; i++)
     {
      if(!g_tf[i].enabled)
         continue;
      bool run = true;
      if(g_cfg.tradeOnBarClose)
         run = IsNewBar(_Symbol, g_tf[i].tf, g_tf[i].lastBar);
      if(run || g_sessions.CurrentSession(now) == SESSION_ASIA)
         ProcessTf(g_tf[i]);
     }

   if(!g_trader.HasOpenPosition())
     {
      for(int slot = 0; slot < AMD_TF_COUNT; slot++)
        {
         const int i = (g_cfg.tfPriority == TF_PRIORITY_FIRST_READY ? slot : PriorityIndex(slot));
         if(!g_tf[i].enabled || !g_tf[i].pending.armed)
            continue;
         MqlRates rates[];
         int copied = 0;
         if(!LoadRates(g_tf[i].tf, rates, copied))
            continue;
         if(TryEnter(g_tf[i], rates))
            break;
        }
     }

   RefreshDashboard();
  }

int OnInit()
  {
   FillConfig();

   if(StringCompare(_Symbol, InpTradeSymbol, false) != 0)
     {
      Print("AMD EA trades ", InpTradeSymbol, " only. Chart symbol is ", _Symbol,
            ". Open an ", InpTradeSymbol, " chart and attach the EA there.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_sessions.Init(g_cfg, _Symbol, PERIOD_M15);
   g_liq.Init(g_cfg, _Symbol);
   g_structure.Init(g_cfg, _Symbol);
   g_trader.Init(g_cfg, _Symbol);
   g_visuals.Init(g_cfg, _Symbol);

   g_tf[0].tf = PERIOD_H1;
   g_tf[0].enabled = InpUseH1;
   g_tf[1].tf = PERIOD_M30;
   g_tf[1].enabled = InpUseM30;
   g_tf[2].tf = PERIOD_M15;
   g_tf[2].enabled = InpUseM15;

   for(int i = 0; i < AMD_TF_COUNT; i++)
     {
      g_tf[i].lastBar   = 0;
      g_tf[i].atrHandle = INVALID_HANDLE;
      ResetTf(g_tf[i]);
      if(!g_tf[i].enabled)
         continue;
      g_tf[i].atrHandle = iATR(_Symbol, g_tf[i].tf, InpAtrPeriod);
      if(g_tf[i].atrHandle == INVALID_HANDLE)
        {
         Print("Failed to create ATR handle for ", TfToString(g_tf[i].tf));
         return(INIT_FAILED);
        }
     }

   ResetCycle(0, "Init");
   g_lastMsg = "Ready on " + _Symbol + "  lots start " + DoubleToString(InpStartLots, 2);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   for(int i = 0; i < AMD_TF_COUNT; i++)
     {
      if(g_tf[i].atrHandle != INVALID_HANDLE)
         IndicatorRelease(g_tf[i].atrHandle);
     }
   g_visuals.DeleteAll();
   Comment("");
  }

void OnTick()
  {
   g_trader.ManageOpenTrades();
   ProcessLogic();
  }
