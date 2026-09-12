//+------------------------------------------------------------------+
//|                                              SMC_Scalper_EA.mq5  |
//|                 Price-action SMC scalper for MT5                 |
//|  M5 trend -> liquidity sweep -> M1 BOS/MSS -> entry -> manage    |
//+------------------------------------------------------------------+
#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "SMC scalper: M5 bias, liquidity sweep, M1 BOS/MSS, dynamic BE trailing"
#property description "Designed for Volatility 100 (1s), Volatility 75 (1s), and XAUUSD"

#include <Trade/Trade.mqh>

//====================================================================
// Enumerations
//====================================================================
enum ENUM_TREND_DIR
  {
   TREND_NONE = 0,
   TREND_BULL = 1,
   TREND_BEAR = 2
  };

enum ENUM_SETUP_STATE
  {
   STATE_IDLE = 0,
   STATE_WAIT_SWEEP = 1,
   STATE_WAIT_BOS = 2,
   STATE_WAIT_PULLBACK = 3
  };

enum ENUM_ENTRY_MODE
  {
   ENTRY_PULLBACK = 0,     // Wait for a small retracement after BOS/MSS
   ENTRY_IMMEDIATE = 1     // Enter on the confirming M1 close
  };

enum ENUM_TP_MODE
  {
   TP_FIXED_RR = 0,        // Fixed risk:reward (e.g. 1:2)
   TP_NEXT_LIQUIDITY = 1,  // Next opposing M5 swing
   TP_NEAREST = 2          // Whichever of the two is closer
  };

enum ENUM_DISTANCE_MODE
  {
   DIST_ATR = 0,           // Distances scale with ATR (recommended)
   DIST_POINTS = 1         // Raw broker points
  };

enum ENUM_PULLBACK_TIMEOUT
  {
   PB_SKIP = 0,            // Cancel setup if no pullback in time
   PB_MARKET = 1           // Enter at market if setup still valid
  };

//====================================================================
// Inputs
//====================================================================
input group "=== Symbols ==="
input string InpAllowedSymbols      = "XAUUSD,Volatility 100 (1s) Index,Volatility 75 (1s) Index"; // Allowed symbols (empty = any)
input bool   InpRestrictToList      = true;   // Block EA if chart symbol is not in the list

input group "=== Strategy timeframes ==="
input ENUM_TIMEFRAMES InpTrendTF    = PERIOD_M5;  // Trend / liquidity timeframe
input ENUM_TIMEFRAMES InpEntryTF    = PERIOD_M1;  // Confirmation timeframe
input int    InpSwingStrength       = 3;          // Bars on each side to confirm a swing
input int    InpTrendSwings         = 2;          // Swing pairs required for HH/HL or LH/LL
input int    InpMaxSwings           = 30;         // Swings to keep in memory
input int    InpSweepLookback       = 12;         // M1 bars to look back for a sweep
input int    InpSetupExpiryBars     = 24;         // Cancel unconfirmed sweep after N M1 bars

input group "=== Entry ==="
input ENUM_ENTRY_MODE InpEntryMode  = ENTRY_PULLBACK;
input double InpPullbackPercent     = 33.0;       // Retrace % of the BOS impulse (10-70)
input int    InpPullbackMaxBars     = 8;          // Max M1 bars to wait for pullback
input ENUM_PULLBACK_TIMEOUT InpPullbackTimeout = PB_MARKET;
input double InpMinImpulseATR       = 0.20;       // Ignore tiny BOS moves (ATR fraction)

input group "=== Stop loss / take profit ==="
input ENUM_TP_MODE InpTPMode        = TP_NEAREST;
input double InpRiskReward          = 2.0;        // Target R:R when using fixed/nearest
input double InpMinRewardRatio      = 1.2;        // Skip trade if projected R:R is below this
input ENUM_DISTANCE_MODE InpDistMode = DIST_ATR;
input int    InpATRPeriod           = 14;
input double InpSLBufferATR         = 0.15;       // Extra room beyond the invalidation swing
input int    InpSLBufferPoints      = 50;         // Used if Distance mode = Points
input bool   InpRequireSweepWick    = true;       // Sweep must wick through then close back in

input group "=== Dynamic breakeven & lock ==="
input bool   InpUseDynamicBE        = true;
input double InpBETriggerATR        = 0.35;       // Move to BE after this much profit (ATR)
input double InpTrailStepATR        = 0.35;       // Each extra step locks more
input double InpTrailLockATR        = 0.35;       // Profit locked per step
input int    InpBETriggerPoints     = 100;        // Points mode: +N -> breakeven
input int    InpTrailStepPoints     = 100;        // Points mode: step size
input int    InpTrailLockPoints     = 100;        // Points mode: lock size
input int    InpBEOffsetPoints      = 2;          // Extra points beyond entry at BE (cover commission)

input group "=== Risk management ==="
input double InpRiskPercent         = 0.5;        // Risk per trade (% of equity). 0 = use fixed lot
input double InpFixedLot            = 0.01;       // Lot if Risk percent is 0
input int    InpMaxOpenTrades       = 3;          // Across all symbols (this magic)
input int    InpMaxPerSymbol        = 1;          // Open trades per symbol
input int    InpMaxTradesPerDay     = 12;         // 0 = unlimited
input double InpDailyLossPercent    = 3.0;        // Pause new trades after this daily loss (%). 0 = off
input bool   InpCloseOnDailyLoss    = false;      // Also flatten positions at the daily-loss cap
input int    InpMaxSpreadPoints     = 0;          // 0 = do not filter by spread
input ulong  InpMaxSlippagePoints   = 30;
input int    InpCooldownBars        = 5;          // M1 bars after a trade before a new setup
input int    InpMagicNumber         = 100125;
input string InpTradeComment        = "SMC_Scalper";

input group "=== Session filter (server time) ==="
input bool   InpUseSessionFilter    = false;
input int    InpSessionStartHour    = 0;          // Inclusive
input int    InpSessionEndHour      = 24;         // Exclusive. 24 = end of day

input group "=== Display & logging ==="
input bool   InpShowDashboard       = true;
input bool   InpDrawLevels          = true;
input bool   InpLogToExperts        = true;
input int    InpDashboardX          = 12;
input int    InpDashboardY          = 24;

//====================================================================
// Types
//====================================================================
struct SwingPoint
  {
   datetime time;
   double   price;
   bool     isHigh;
   bool     swept;
  };

struct SymbolState
  {
   string            symbol;
   ENUM_TREND_DIR    trend;
   ENUM_SETUP_STATE  state;
   datetime          lastM1Bar;
   datetime          lastTradeBar;
   datetime          lastUsedSwingTime;
   datetime          sweepTime;
   double            sweepPrice;
   bool              sweepIsLow;     // true = SSL grab (buy setup), false = BSL grab (sell)
   datetime          sweepSwingTime;
   double            bosLevel;
   datetime          bosTime;
   double            impulseHigh;
   double            impulseLow;
   double            pendingSL;
   double            pendingTP;
   int               bosBarAge;
   int               dayTrades;
   int               dayKey;
  };

//====================================================================
// Globals
//====================================================================
CTrade         g_trade;
SymbolState    g_state;
int            g_dayKey = -1;
double         g_dayStartEquity = 0.0;
bool           g_dailyLossHit = false;
bool           g_entryInFlight = false;
string         g_prefix;
int            g_atrTrend = INVALID_HANDLE;
int            g_atrEntry = INVALID_HANDLE;

#define MAX_SWINGS 64

//====================================================================
// Logging
//====================================================================
void LogMsg(const string msg)
  {
   if(InpLogToExperts)
      Print(msg);
  }

string TrendText(const ENUM_TREND_DIR t)
  {
   if(t == TREND_BULL)
      return "BUY only (HH + HL)";
   if(t == TREND_BEAR)
      return "SELL only (LH + LL)";
   return "No trade (range)";
  }

string StateText(const ENUM_SETUP_STATE s)
  {
   switch(s)
     {
      case STATE_WAIT_SWEEP:    return "Wait liquidity sweep";
      case STATE_WAIT_BOS:      return "Wait M1 BOS/MSS";
      case STATE_WAIT_PULLBACK: return "Wait pullback";
      default:                  return "Scan market";
     }
  }

//====================================================================
// Symbol / session helpers
//====================================================================
string TrimToken(string s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
  }

bool SymbolIsAllowed(const string sym)
  {
   string list = InpAllowedSymbols;
   if(StringLen(TrimToken(list)) == 0)
      return true;

   string parts[];
   int n = StringSplit(list, ',', parts);
   for(int i = 0; i < n; i++)
     {
      if(TrimToken(parts[i]) == sym)
         return true;
     }
   return false;
  }

bool SessionOpen()
  {
   if(!InpUseSessionFilter)
      return true;
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int h = dt.hour;
   int startH = InpSessionStartHour;
   int endH = InpSessionEndHour;
   if(endH >= 24)
      endH = 24;
   if(startH == endH)
      return true;
   if(startH < endH)
      return (h >= startH && h < endH);
   return (h >= startH || h < endH);
  }

int CurrentDayKey()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return (dt.year * 10000 + dt.mon * 100 + dt.day);
  }

datetime DayStartTime()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;
   return StructToTime(dt);
  }

bool IsNewBar(SymbolState &st)
  {
   datetime t[1];
   if(CopyTime(st.symbol, InpEntryTF, 0, 1, t) < 1)
      return false;
   if(t[0] != st.lastM1Bar)
     {
      st.lastM1Bar = t[0];
      return true;
     }
   return false;
  }

//====================================================================
// Broker distances
//====================================================================
double PointSize(const string sym)
  {
   double p = SymbolInfoDouble(sym, SYMBOL_POINT);
   return (p > 0.0 ? p : _Point);
  }

double ATRFromHandle(const int handle)
  {
   if(handle == INVALID_HANDLE)
      return 0.0;
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, 1, 1, buf) < 1)
      return 0.0;
   return buf[0];
  }

double DistToPrice(const string sym, const double atrMult, const int pointsVal)
  {
   if(InpDistMode == DIST_POINTS)
      return pointsVal * PointSize(sym);
   double atr = ATRFromHandle(g_atrTrend);
   if(atr <= 0.0)
      atr = ATRFromHandle(g_atrEntry);
   if(atr <= 0.0)
      return pointsVal * PointSize(sym);
   return atr * atrMult;
  }

int StopsLevelPoints(const string sym)
  {
   int stops = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
   int freeze = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL);
   int v = MathMax(stops, freeze);
   return (v < 1 ? 1 : v);
  }

double NormalizePrice(const string sym, double price)
  {
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
  }

//====================================================================
// Filling / volume
//====================================================================
ENUM_ORDER_TYPE_FILLING DetectFilling(const string sym)
  {
   long filling = SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

double NormalizeVolume(const string sym, double lot)
  {
   double minLot  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double step    = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   if(minLot <= 0.0)
      minLot = step;
   lot = MathFloor(lot / step + 1e-8) * step;
   if(lot < minLot)
      lot = minLot;
   if(lot > maxLot)
      lot = maxLot;
   int digits = 2;
   if(step < 0.01)
      digits = 3;
   if(step < 0.001)
      digits = 4;
   return NormalizeDouble(lot, digits);
  }

double CalcLot(const string sym, const double entry, const double sl)
  {
   if(InpRiskPercent <= 0.0)
      return NormalizeVolume(sym, InpFixedLot);

   double slDist = MathAbs(entry - sl);
   if(slDist <= 0.0)
      return NormalizeVolume(sym, InpFixedLot);

   double tickSize  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0)
      tickSize = PointSize(sym);

   double moneyPerLot = 0.0;
   if(tickValue > 0.0)
      moneyPerLot = (slDist / tickSize) * tickValue;
   else
     {
      double contract = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
      if(contract <= 0.0)
         contract = 100000.0;
      moneyPerLot = slDist * contract;
     }

   if(moneyPerLot <= 0.0)
      return NormalizeVolume(sym, InpFixedLot);

   double riskMoney = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double lot = riskMoney / moneyPerLot;
   return NormalizeVolume(sym, lot);
  }

//====================================================================
// Daily P/L and position counts
//====================================================================
double MagicClosedPnLToday()
  {
   double pnl = 0.0;
   if(!HistorySelect(DayStartTime(), TimeCurrent()))
      return 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagicNumber)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
         continue;
      pnl += HistoryDealGetDouble(ticket, DEAL_PROFIT)
             + HistoryDealGetDouble(ticket, DEAL_SWAP)
             + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
     }
   return pnl;
  }

double MagicFloatingPnL()
  {
   double pnl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;
      pnl += PositionGetDouble(POSITION_PROFIT)
             + PositionGetDouble(POSITION_SWAP);
     }
   return pnl;
  }

int CountMagicPositions(const string filterSymbol = "")
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;
      if(filterSymbol != "" && PositionGetString(POSITION_SYMBOL) != filterSymbol)
         continue;
      c++;
     }
   return c;
  }

int CountMagicDealsToday()
  {
   int c = 0;
   if(!HistorySelect(DayStartTime(), TimeCurrent()))
      return 0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagicNumber)
         continue;
      if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      c++;
     }
   return c;
  }

void CloseAllMagicPositions(const string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      g_trade.SetTypeFilling(DetectFilling(sym));
      if(!g_trade.PositionClose(ticket))
         LogMsg("Failed to close #" + IntegerToString((int)ticket) + " (" + reason + "): " + g_trade.ResultRetcodeDescription());
     }
  }

void RefreshDailyGuard()
  {
   int key = CurrentDayKey();
   if(key != g_dayKey)
     {
      g_dayKey = key;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dailyLossHit = false;
      g_state.dayKey = key;
      g_state.dayTrades = 0;
      LogMsg("New trading day. Equity=" + DoubleToString(g_dayStartEquity, 2));
     }

   if(InpDailyLossPercent <= 0.0)
      return;

   double pnl = MagicClosedPnLToday() + MagicFloatingPnL();
   double base = (g_dayStartEquity > 0.0 ? g_dayStartEquity : AccountInfoDouble(ACCOUNT_EQUITY));
   double cap = -MathAbs(base * InpDailyLossPercent / 100.0);

   if(pnl <= cap)
     {
      if(!g_dailyLossHit)
        {
         g_dailyLossHit = true;
         LogMsg("Daily loss cap reached. PnL=" + DoubleToString(pnl, 2) + " cap=" + DoubleToString(cap, 2));
         if(InpCloseOnDailyLoss)
            CloseAllMagicPositions("daily loss cap");
        }
     }
  }

//====================================================================
// Swings
//====================================================================
bool CopyRatesSeries(const string sym, const ENUM_TIMEFRAMES tf, const int count, MqlRates &rates[])
  {
   ArraySetAsSeries(rates, true);
   int n = CopyRates(sym, tf, 0, count, rates);
   return (n >= count / 2 && n > InpSwingStrength * 2 + 5);
  }

bool IsSwingHigh(const MqlRates &rates[], const int i, const int strength)
  {
   int sz = ArraySize(rates);
   if(i < strength + 1 || i + strength >= sz)
      return false;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i].high <= rates[i - k].high)
         return false;
      if(rates[i].high <= rates[i + k].high)
         return false;
     }
   return true;
  }

bool IsSwingLow(const MqlRates &rates[], const int i, const int strength)
  {
   int sz = ArraySize(rates);
   if(i < strength + 1 || i + strength >= sz)
      return false;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i].low >= rates[i - k].low)
         return false;
      if(rates[i].low >= rates[i + k].low)
         return false;
     }
   return true;
  }

int CollectSwings(const MqlRates &rates[], SwingPoint &swings[], const bool highs)
  {
   int sz = ArraySize(rates);
   int strength = MathMax(2, InpSwingStrength);
   int count = 0;
   int cap = MathMin(InpMaxSwings, MAX_SWINGS);
   ArrayResize(swings, cap);

   for(int i = strength + 1; i < sz - strength && count < cap; i++)
     {
      bool hit = highs ? IsSwingHigh(rates, i, strength) : IsSwingLow(rates, i, strength);
      if(!hit)
         continue;
      swings[count].time   = rates[i].time;
      swings[count].price  = highs ? rates[i].high : rates[i].low;
      swings[count].isHigh = highs;
      swings[count].swept  = false;
      count++;
     }
   ArrayResize(swings, count);
   return count;
  }

ENUM_TREND_DIR DetectTrend(const SwingPoint &highs[], const SwingPoint &lows[])
  {
   int need = MathMax(2, InpTrendSwings);
   if(ArraySize(highs) < need || ArraySize(lows) < need)
      return TREND_NONE;

   bool hh = true;
   bool hl = true;
   bool lh = true;
   bool ll = true;
   for(int i = 0; i < need - 1; i++)
     {
      if(!(highs[i].price > highs[i + 1].price))
         hh = false;
      if(!(lows[i].price > lows[i + 1].price))
         hl = false;
      if(!(highs[i].price < highs[i + 1].price))
         lh = false;
      if(!(lows[i].price < lows[i + 1].price))
         ll = false;
     }

   if(hh && hl)
      return TREND_BULL;
   if(lh && ll)
      return TREND_BEAR;
   return TREND_NONE;
  }

int FindNearestSwing(const SwingPoint &swings[], const datetime beforeTime)
  {
   for(int i = 0; i < ArraySize(swings); i++)
     {
      if(beforeTime <= 0 || swings[i].time < beforeTime)
         return i;
     }
   return -1;
  }

//====================================================================
// Liquidity sweep + BOS/MSS
//====================================================================
bool DetectSweep(const MqlRates &m1[],
                 const SwingPoint &zones[],
                 const bool seekLowSweep,
                 const datetime skipSwingTime,
                 int &outZoneIndex,
                 int &outSweepBar)
  {
   outZoneIndex = -1;
   outSweepBar = -1;
   int look = MathMin(InpSweepLookback, ArraySize(m1) - 2);
   if(look < 3 || ArraySize(zones) == 0)
      return false;

   for(int z = 0; z < ArraySize(zones); z++)
     {
      if(skipSwingTime > 0 && zones[z].time == skipSwingTime)
         continue;

      double level = zones[z].price;
      for(int i = 1; i <= look; i++)
        {
         if(m1[i].time <= zones[z].time)
            continue;

         bool pierced = seekLowSweep ? (m1[i].low < level) : (m1[i].high > level);
         if(!pierced)
            continue;

         bool closedBack = true;
         if(InpRequireSweepWick)
            closedBack = seekLowSweep ? (m1[i].close > level) : (m1[i].close < level);
         else
           {
            closedBack = false;
            for(int j = i; j >= 1; j--)
              {
               if(seekLowSweep && m1[j].close > level)
                 { closedBack = true; break; }
               if(!seekLowSweep && m1[j].close < level)
                 { closedBack = true; break; }
              }
           }

         if(!closedBack)
            continue;

         // Only arm a setup when the sweep just confirmed on the last closed bar.
         int confirmBar = i;
         if(!InpRequireSweepWick)
           {
            confirmBar = 1;
            if(!(seekLowSweep ? (m1[1].close > level) : (m1[1].close < level)))
               continue;
           }
         else
            if(i != 1)
               continue;

         outZoneIndex = z;
         outSweepBar = confirmBar;
         return true;
        }
     }
   return false;
  }

bool DetectBOS(const MqlRates &m1[],
               const SwingPoint &oppSwings[],
               const datetime sweepTime,
               const bool bullish,
               double &bosLevel)
  {
   int idx = FindNearestSwing(oppSwings, sweepTime);
   if(idx < 0)
     {
      // Fallback: extreme of a few M1 bars just before / at the sweep
      double ext = bullish ? -DBL_MAX : DBL_MAX;
      int used = 0;
      for(int i = 1; i < ArraySize(m1) && used < 8; i++)
        {
         if(m1[i].time > sweepTime)
            continue;
         used++;
         if(bullish)
            ext = MathMax(ext, m1[i].high);
         else
            ext = MathMin(ext, m1[i].low);
        }
      if(used == 0)
         return false;
      bosLevel = ext;
     }
   else
      bosLevel = oppSwings[idx].price;

   if(m1[1].time <= sweepTime)
      return false;

   bool broke = bullish ? (m1[1].close > bosLevel) : (m1[1].close < bosLevel);
   if(!broke)
      return false;

   // Act on the breaking candle only — do not chase a BOS that already happened.
   if(ArraySize(m1) > 2 && m1[2].time > sweepTime)
     {
      bool alreadyBroke = bullish ? (m1[2].close > bosLevel) : (m1[2].close < bosLevel);
      if(alreadyBroke)
         return false;
     }
   return true;
  }

double NextLiquidityPrice(const SwingPoint &swings[], const double entry, const bool buy)
  {
   double best = 0.0;
   double bestDist = 0.0;
   bool have = false;
   for(int i = 0; i < ArraySize(swings); i++)
     {
      if(buy && swings[i].price <= entry)
         continue;
      if(!buy && swings[i].price >= entry)
         continue;
      double dist = MathAbs(swings[i].price - entry);
      if(!have || dist < bestDist)
        {
         have = true;
         bestDist = dist;
         best = swings[i].price;
        }
     }
   return best;
  }

//====================================================================
// Chart drawings
//====================================================================
void ClearDrawings()
  {
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, g_prefix) == 0)
         ObjectDelete(0, name);
     }
  }

void DrawHLine(const string tag, const double price, const color clr, const ENUM_LINE_STYLE style)
  {
   if(!InpDrawLevels)
      return;
   string name = g_prefix + tag;
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(0, name, OBJPROP_STYLE, style);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
     }
   else
      ObjectSetDouble(0, name, OBJPROP_PRICE, price);
  }

void UpdateDashboard()
  {
   if(!InpShowDashboard)
      return;

   double spreadPts = (double)SymbolInfoInteger(g_state.symbol, SYMBOL_SPREAD);
   double pnl = MagicClosedPnLToday() + MagicFloatingPnL();
   string lines =
      "SMC Scalper  |  " + g_state.symbol + "\n" +
      "M5 trend: " + TrendText(g_state.trend) + "\n" +
      "State: " + StateText(g_state.state) + "\n" +
      "Spread: " + DoubleToString(spreadPts, 0) + " pts\n" +
      "Daily P/L: " + DoubleToString(pnl, 2) +
      (g_dailyLossHit ? "  [DAILY STOP]" : "") + "\n" +
      "Open trades: " + IntegerToString(CountMagicPositions()) +
      "  Today: " + IntegerToString(CountMagicDealsToday());

   if(g_state.state == STATE_WAIT_BOS || g_state.state == STATE_WAIT_PULLBACK)
     {
      string side = g_state.sweepIsLow ? "BUY SSL sweep" : "SELL BSL sweep";
      lines += "\n" + side + " @ " + DoubleToString(g_state.sweepPrice, (int)SymbolInfoInteger(g_state.symbol, SYMBOL_DIGITS));
     }
   if(g_state.state == STATE_WAIT_PULLBACK)
      lines += "\nBOS @ " + DoubleToString(g_state.bosLevel, (int)SymbolInfoInteger(g_state.symbol, SYMBOL_DIGITS));

   Comment(lines);
  }

//====================================================================
// Trade execution
//====================================================================
bool SpreadOK(const string sym)
  {
   if(InpMaxSpreadPoints <= 0)
      return true;
   int sp = (int)SymbolInfoInteger(sym, SYMBOL_SPREAD);
   return (sp <= InpMaxSpreadPoints);
  }

bool RiskAllowsNewTrade(const string sym)
  {
   if(g_dailyLossHit)
      return false;
   if(!SessionOpen())
      return false;
   if(!SpreadOK(sym))
      return false;
   if(CountMagicPositions() >= InpMaxOpenTrades)
      return false;
   if(CountMagicPositions(sym) >= InpMaxPerSymbol)
      return false;
   if(InpMaxTradesPerDay > 0 && CountMagicDealsToday() >= InpMaxTradesPerDay)
      return false;
   return true;
  }

bool CooldownActive(const SymbolState &st)
  {
   if(st.lastTradeBar <= 0 || InpCooldownBars <= 0)
      return false;
   int bars = iBarShift(st.symbol, InpEntryTF, st.lastTradeBar, true);
   if(bars < 0)
      return false;
   return (bars < InpCooldownBars);
  }

bool SendMarket(const string sym, const bool buy, const double lot, const double sl, const double tp)
  {
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((uint)InpMaxSlippagePoints);
   g_trade.SetTypeFilling(DetectFilling(sym));
   g_trade.SetAsyncMode(false);

   double slN = NormalizePrice(sym, sl);
   double tpN = (tp > 0.0 ? NormalizePrice(sym, tp) : 0.0);

   bool ok = buy ? g_trade.Buy(lot, sym, 0.0, slN, tpN, InpTradeComment)
                 : g_trade.Sell(lot, sym, 0.0, slN, tpN, InpTradeComment);
   if(!ok)
     {
      LogMsg("Order failed: " + g_trade.ResultRetcodeDescription() +
             " retcode=" + IntegerToString((int)g_trade.ResultRetcode()));
      return false;
     }
   LogMsg((buy ? "BUY " : "SELL ") + sym +
          " lot=" + DoubleToString(lot, 3) +
          " sl=" + DoubleToString(slN, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)) +
          " tp=" + DoubleToString(tpN, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS)));
   return true;
  }

bool BuildTargets(const string sym,
                  const bool buy,
                  const double entry,
                  const double invalidation,
                  const SwingPoint &oppZones[],
                  double &sl,
                  double &tp)
  {
   double buffer = DistToPrice(sym, InpSLBufferATR, InpSLBufferPoints);
   if(buy)
      sl = invalidation - buffer;
   else
      sl = invalidation + buffer;

   sl = NormalizePrice(sym, sl);

   double minDist = StopsLevelPoints(sym) * PointSize(sym);
   if(MathAbs(entry - sl) < minDist)
     {
      if(buy)
         sl = entry - minDist;
      else
         sl = entry + minDist;
      sl = NormalizePrice(sym, sl);
     }

   double risk = MathAbs(entry - sl);
   if(risk <= 0.0)
      return false;

   double rrTP = buy ? (entry + risk * InpRiskReward) : (entry - risk * InpRiskReward);
   double liqTP = NextLiquidityPrice(oppZones, entry, buy);
   if(liqTP > 0.0)
     {
      double liqBuf = DistToPrice(sym, InpSLBufferATR, InpSLBufferPoints) * 0.5;
      if(buy)
         liqTP -= liqBuf;
      else
         liqTP += liqBuf;
      if((buy && liqTP <= entry) || (!buy && liqTP >= entry))
         liqTP = 0.0;
     }

   tp = 0.0;
   if(InpTPMode == TP_FIXED_RR)
      tp = rrTP;
   else
      if(InpTPMode == TP_NEXT_LIQUIDITY)
         tp = (liqTP > 0.0 ? liqTP : rrTP);
      else
        {
         if(liqTP <= 0.0)
            tp = rrTP;
         else
           {
            double dRR  = MathAbs(rrTP - entry);
            double dLiq = MathAbs(liqTP - entry);
            tp = (dLiq <= dRR ? liqTP : rrTP);
           }
        }

   tp = NormalizePrice(sym, tp);
   if(tp > 0.0 && MathAbs(tp - entry) < minDist)
      tp = NormalizePrice(sym, rrTP);

   double rr = (tp > 0.0 ? MathAbs(tp - entry) / risk : InpRiskReward);
   if(tp > 0.0 && rr < InpMinRewardRatio)
     {
      tp = NormalizePrice(sym, rrTP);
      rr = InpRiskReward;
     }
   if(InpMinRewardRatio > 0.0 && rr + 1e-8 < InpMinRewardRatio)
      return false;

   return true;
  }

//====================================================================
// Dynamic breakeven / lock-in trailing
//====================================================================
void ManageOpenPositions()
  {
   if(!InpUseDynamicBE)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      long type = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      double pt = PointSize(sym);

      bool buy = (type == POSITION_TYPE_BUY);
      double price = buy ? bid : ask;
      double profitDist = buy ? (price - open) : (open - price);
      if(profitDist <= 0.0)
         continue;

      double beTrig = DistToPrice(sym, InpBETriggerATR, InpBETriggerPoints);
      double step   = DistToPrice(sym, InpTrailStepATR, InpTrailStepPoints);
      double lock   = DistToPrice(sym, InpTrailLockATR, InpTrailLockPoints);
      if(beTrig <= 0.0)
         continue;

      double newSL = sl;
      double beOffset = InpBEOffsetPoints * pt;
      if(profitDist >= beTrig)
        {
         // Entry -> +BE -> breakeven; each extra step locks more profit
         newSL = buy ? (open + beOffset) : (open - beOffset);
         if(step > 0.0 && profitDist > beTrig)
           {
            int steps = (int)MathFloor((profitDist - beTrig) / step + 1e-8);
            if(steps > 0)
              {
               double locked = steps * lock;
               newSL = buy ? (open + locked) : (open - locked);
              }
           }
        }

      newSL = NormalizePrice(sym, newSL);

      double minDist = StopsLevelPoints(sym) * pt;
      if(buy)
        {
         if(newSL >= bid - minDist)
            newSL = NormalizePrice(sym, bid - minDist);
         bool better = (sl == 0.0 || newSL > sl + pt * 0.5);
         if(!better)
            continue;
        }
      else
        {
         if(newSL <= ask + minDist)
            newSL = NormalizePrice(sym, ask + minDist);
         bool better = (sl == 0.0 || newSL < sl - pt * 0.5);
         if(!better)
            continue;
        }

      g_trade.SetExpertMagicNumber(InpMagicNumber);
      g_trade.SetTypeFilling(DetectFilling(sym));
      if(!g_trade.PositionModify(ticket, newSL, tp))
        {
         // Silent retry next tick — freeze-level / requote is common
        }
     }
  }

//====================================================================
// Core per-bar strategy
//====================================================================
void ResetSetup(SymbolState &st)
  {
   st.state = STATE_WAIT_SWEEP;
   st.sweepTime = 0;
   st.sweepPrice = 0.0;
   st.bosLevel = 0.0;
   st.bosTime = 0;
   st.impulseHigh = 0.0;
   st.impulseLow = 0.0;
   st.pendingSL = 0.0;
   st.pendingTP = 0.0;
   st.bosBarAge = 0;
  }

void TryEnter(SymbolState &st, const bool buy, const double slInvalidation,
              const SwingPoint &oppZones[], const MqlRates &m1[])
  {
   if(g_entryInFlight)
      return;
   if(!RiskAllowsNewTrade(st.symbol))
      return;

   MqlTick tick;
   if(!SymbolInfoTick(st.symbol, tick))
      return;

   double entry = buy ? tick.ask : tick.bid;
   double sl = 0.0, tp = 0.0;
   if(!BuildTargets(st.symbol, buy, entry, slInvalidation, oppZones, sl, tp))
     {
      LogMsg("Skip entry: R:R or stop distance invalid");
      ResetSetup(st);
      return;
     }

   // Impulse filter: avoid micro-structure noise
   double impulse = st.impulseHigh - st.impulseLow;
   double minImp = DistToPrice(st.symbol, InpMinImpulseATR, InpSLBufferPoints);
   if(minImp > 0.0 && impulse < minImp)
     {
      LogMsg("Skip entry: impulse too small vs ATR");
      ResetSetup(st);
      return;
     }

   double lot = CalcLot(st.symbol, entry, sl);
   if(lot <= 0.0)
     {
      ResetSetup(st);
      return;
     }

   g_entryInFlight = true;
   bool sent = SendMarket(st.symbol, buy, lot, sl, tp);
   g_entryInFlight = false;
   if(sent)
     {
      st.lastTradeBar = m1[0].time;
      st.lastUsedSwingTime = st.sweepSwingTime;
      st.dayTrades++;
      ResetSetup(st);
     }
  }

void OnNewM1Bar(SymbolState &st)
  {
   MqlRates m5[], m1[];
   if(!CopyRatesSeries(st.symbol, InpTrendTF, 80, m5))
      return;
   if(!CopyRatesSeries(st.symbol, InpEntryTF, 120, m1))
      return;

   SwingPoint m5Highs[], m5Lows[], m1Highs[], m1Lows[];
   CollectSwings(m5, m5Highs, true);
   CollectSwings(m5, m5Lows, false);
   CollectSwings(m1, m1Highs, true);
   CollectSwings(m1, m1Lows, false);

   st.trend = DetectTrend(m5Highs, m5Lows);

   if(InpDrawLevels)
     {
      if(ArraySize(m5Highs) > 0)
         DrawHLine("liq_high", m5Highs[0].price, clrOrangeRed, STYLE_DOT);
      if(ArraySize(m5Lows) > 0)
         DrawHLine("liq_low", m5Lows[0].price, clrDodgerBlue, STYLE_DOT);
     }

   if(CountMagicPositions(st.symbol) >= InpMaxPerSymbol)
     {
      st.state = STATE_IDLE;
      return;
     }

   if(st.trend == TREND_NONE)
     {
      ResetSetup(st);
      st.state = STATE_IDLE;
      return;
     }

   if(CooldownActive(st))
      return;

   // Expire stale sweeps
   if(st.state == STATE_WAIT_BOS || st.state == STATE_WAIT_PULLBACK)
     {
      int age = iBarShift(st.symbol, InpEntryTF, st.sweepTime, true);
      if(age < 0 || age > InpSetupExpiryBars)
        {
         LogMsg("Setup expired");
         ResetSetup(st);
        }
     }

   // Direction is locked to M5 structure: buys only in HH/HL, sells only in LH/LL
   bool wantBuy = (st.trend == TREND_BULL);

   if(st.state == STATE_IDLE)
      st.state = STATE_WAIT_SWEEP;

   if(st.state == STATE_WAIT_SWEEP)
     {
      int z = -1, bar = -1;
      bool found = false;
      if(wantBuy)
         found = DetectSweep(m1, m5Lows, true, st.lastUsedSwingTime, z, bar);
      else
         found = DetectSweep(m1, m5Highs, false, st.lastUsedSwingTime, z, bar);

      if(found)
        {
         st.sweepIsLow = wantBuy;
         st.sweepPrice = wantBuy ? m5Lows[z].price : m5Highs[z].price;
         st.sweepSwingTime = wantBuy ? m5Lows[z].time : m5Highs[z].time;
         st.lastUsedSwingTime = st.sweepSwingTime;
         st.sweepTime = m1[bar].time;
         st.state = STATE_WAIT_BOS;
         DrawHLine("sweep", st.sweepPrice, clrGold, STYLE_DASH);
         LogMsg("Liquidity sweep " + (wantBuy ? "SSL (buy setup) @ " : "BSL (sell setup) @ ") +
                DoubleToString(st.sweepPrice, (int)SymbolInfoInteger(st.symbol, SYMBOL_DIGITS)));
        }
     }
   else
   if(st.state == STATE_WAIT_BOS)
     {
      double bos = 0.0;
      bool ok = DetectBOS(m1, wantBuy ? m1Highs : m1Lows, st.sweepTime, wantBuy, bos);
      if(ok)
        {
         st.bosLevel = bos;
         st.bosTime = m1[1].time;
         st.bosBarAge = 0;
         st.impulseHigh = wantBuy ? m1[1].high : MathMax(st.sweepPrice, m1[1].high);
         st.impulseLow  = wantBuy ? MathMin(st.sweepPrice, m1[1].low) : m1[1].low;
         // Capture impulse range from sweep bar through BOS bar
         int sweepShift = iBarShift(st.symbol, InpEntryTF, st.sweepTime, true);
         if(sweepShift > 1)
           {
            for(int i = 1; i <= sweepShift && i < ArraySize(m1); i++)
              {
               st.impulseHigh = MathMax(st.impulseHigh, m1[i].high);
               st.impulseLow  = MathMin(st.impulseLow, m1[i].low);
              }
           }
         DrawHLine("bos", st.bosLevel, clrLime, STYLE_DASH);
         LogMsg("M1 BOS/MSS confirmed @ " + DoubleToString(st.bosLevel, (int)SymbolInfoInteger(st.symbol, SYMBOL_DIGITS)));

         if(InpEntryMode == ENTRY_IMMEDIATE)
           {
            TryEnter(st, wantBuy, st.sweepPrice, wantBuy ? m5Highs : m5Lows, m1);
            return;
           }
         st.state = STATE_WAIT_PULLBACK;
        }
     }
   else
   if(st.state == STATE_WAIT_PULLBACK)
     {
      st.bosBarAge++;
      double range = st.impulseHigh - st.impulseLow;
      if(range <= 0.0)
        {
         ResetSetup(st);
         return;
        }

      double pb = MathMax(10.0, MathMin(70.0, InpPullbackPercent)) / 100.0;
      double trigger = wantBuy ? (st.impulseHigh - range * pb)
                               : (st.impulseLow + range * pb);

      MqlTick tick;
      if(!SymbolInfoTick(st.symbol, tick))
         return;

      bool pulled = wantBuy ? (tick.ask <= trigger) : (tick.bid >= trigger);
      bool stillValid = wantBuy ? (tick.bid > st.sweepPrice) : (tick.ask < st.sweepPrice);

      if(pulled && stillValid)
        {
         TryEnter(st, wantBuy, st.sweepPrice, wantBuy ? m5Highs : m5Lows, m1);
         return;
        }

      if(st.bosBarAge >= InpPullbackMaxBars)
        {
         if(InpPullbackTimeout == PB_MARKET && stillValid)
           {
            LogMsg("Pullback timeout — entering at market");
            TryEnter(st, wantBuy, st.sweepPrice, wantBuy ? m5Highs : m5Lows, m1);
           }
         else
           {
            LogMsg("Pullback timeout — setup cancelled");
            ResetSetup(st);
           }
        }
     }
  }

//====================================================================
// Event handlers
//====================================================================
int OnInit()
  {
   g_prefix = "SMC_" + IntegerToString(InpMagicNumber) + "_";

   if(InpRestrictToList && !SymbolIsAllowed(_Symbol))
     {
      Print("Symbol ", _Symbol, " is not in the allowed list: ", InpAllowedSymbols);
      Print("Attach this EA to XAUUSD, Volatility 100 (1s) Index, or Volatility 75 (1s) Index, or disable RestrictToList.");
      return INIT_FAILED;
     }

   if(!SymbolSelect(_Symbol, true))
     {
      Print("Cannot select symbol ", _Symbol);
      return INIT_FAILED;
     }

   ZeroMemory(g_state);
   g_state.symbol = _Symbol;
   g_state.state = STATE_IDLE;
   g_state.trend = TREND_NONE;

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints((uint)InpMaxSlippagePoints);
   g_trade.SetTypeFilling(DetectFilling(_Symbol));
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   g_atrTrend = iATR(_Symbol, InpTrendTF, InpATRPeriod);
   g_atrEntry = iATR(_Symbol, InpEntryTF, InpATRPeriod);
   if(g_atrTrend == INVALID_HANDLE || g_atrEntry == INVALID_HANDLE)
     {
      Print("Failed to create ATR handles");
      return INIT_FAILED;
     }

   if(InpSwingStrength < 2)
     {
      Print("Swing strength must be at least 2");
      return INIT_FAILED;
     }
   if(InpRiskReward <= 0.0)
     {
      Print("Risk:reward must be positive");
      return INIT_FAILED;
     }
   if(InpRiskPercent < 0.0)
     {
      Print("Risk percent cannot be negative");
      return INIT_FAILED;
     }

   g_dayKey = -1;
   g_entryInFlight = false;
   RefreshDailyGuard();

   if(InpShowDashboard)
      UpdateDashboard();

   LogMsg("SMC Scalper initialized on " + _Symbol +
          " | Trend TF=" + EnumToString(InpTrendTF) +
          " Entry TF=" + EnumToString(InpEntryTF) +
          " Magic=" + IntegerToString(InpMagicNumber));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   Comment("");
   ClearDrawings();
   if(g_atrTrend != INVALID_HANDLE)
      IndicatorRelease(g_atrTrend);
   if(g_atrEntry != INVALID_HANDLE)
      IndicatorRelease(g_atrEntry);
   g_atrTrend = INVALID_HANDLE;
   g_atrEntry = INVALID_HANDLE;
  }

void OnTick()
  {
   RefreshDailyGuard();
   ManageOpenPositions();

   if(IsNewBar(g_state))
      OnNewM1Bar(g_state);
   else
      if(g_state.state == STATE_WAIT_PULLBACK)
        {
         // Pullback can complete intra-bar
         MqlRates m5[], m1[];
         if(CopyRatesSeries(g_state.symbol, InpTrendTF, 80, m5) &&
            CopyRatesSeries(g_state.symbol, InpEntryTF, 120, m1))
           {
            SwingPoint m5Highs[], m5Lows[];
            CollectSwings(m5, m5Highs, true);
            CollectSwings(m5, m5Lows, false);
            bool wantBuy = (g_state.trend == TREND_BULL);
            double range = g_state.impulseHigh - g_state.impulseLow;
            if(range > 0.0)
              {
               double pb = MathMax(10.0, MathMin(70.0, InpPullbackPercent)) / 100.0;
               double trigger = wantBuy ? (g_state.impulseHigh - range * pb)
                                        : (g_state.impulseLow + range * pb);
               MqlTick tick;
               if(SymbolInfoTick(g_state.symbol, tick))
                 {
                  bool pulled = wantBuy ? (tick.ask <= trigger) : (tick.bid >= trigger);
                  bool stillValid = wantBuy ? (tick.bid > g_state.sweepPrice)
                                            : (tick.ask < g_state.sweepPrice);
                  if(pulled && stillValid)
                     TryEnter(g_state, wantBuy, g_state.sweepPrice, wantBuy ? m5Highs : m5Lows, m1);
                 }
              }
           }
        }

   static datetime lastDash = 0;
   if(TimeCurrent() != lastDash)
     {
      lastDash = TimeCurrent();
      UpdateDashboard();
     }
  }
//+------------------------------------------------------------------+
