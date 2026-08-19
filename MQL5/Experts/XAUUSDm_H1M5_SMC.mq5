#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "XAUUSDm H1/M5 market-structure EA: H1 bias, liquidity, order blocks, M5 confirmation, structural SL/TP, balance-tier lots."

#include <Trade/Trade.mqh>

input group "=== Symbol & Timeframes ==="
input string            InpSymbol              = "XAUUSDm";
input ENUM_TIMEFRAMES   InpAnalysisTF          = PERIOD_H1;
input ENUM_TIMEFRAMES   InpEntryTF             = PERIOD_M5;

input group "=== Lot Size / Balance Tiers ==="
input double            StartingLot            = 0.01;
input double            FirstIncreaseBalance   = 150.00;
input double            BalanceStep            = 100.00;
input double            LotIncrease            = 0.01;

input group "=== Strategy Filters ==="
input bool              UseMarketStructure     = true;
input bool              UseLiquiditySweep      = true;
input bool              UseOrderBlocks         = true;
input bool              UseM5Confirmation      = true;
input bool              RequireM5Retest        = true;
input bool              RequireDiscountPremium = true;

input group "=== Structure Parameters ==="
input int               InpH1LookbackBars      = 220;
input int               InpM5LookbackBars      = 180;
input int               InpH1SwingStrength     = 3;
input int               InpM5SwingStrength     = 2;
input int               InpM5ConfirmMaxBars    = 18;
input double            InpDisplacementFactor  = 1.60;
input int               EqualLevelPoints       = 180;
input int               SweepMaxAgeM5Bars      = 36;
input int               SweepMinPiercePoints   = 30;
input int               ZoneMaxTests           = 2;
input int               ZoneApproachPoints     = 250;

input group "=== Risk Protection ==="
input int               MaxOpenPositions       = 1;
input int               MaximumDailyTrades     = 6;
input double            MaximumDailyLossPercent = 5.0;
input double            MaximumDrawdownPercent = 20.0;
input double            MinimumRiskReward      = 2.0;
input int               MaxStopLossPoints      = 5000;
input int               SLBufferPoints         = 80;
input bool              UseSpreadFilter        = true;
input int               MaxSpreadPoints        = 350;
input bool              UseDailyLossProtection = true;
input bool              UseMaxDrawdownProtection = true;
input int               SlippagePoints         = 40;
input int               FailedOrderWaitSeconds = 60;

input group "=== Session & News ==="
input bool              UseTradingSession      = false;
input int               StartTradingHour       = 7;
input int               EndTradingHour         = 21;
input bool              UseNewsFilter          = false;

input group "=== Identification ==="
input long              MagicNumber            = 19052601;
input string            TradeComment           = "XAUUSDm-H1M5";

input group "=== Visualization ==="
input bool              ShowDashboard          = true;
input bool              ShowZones              = true;
input bool              ShowLiquidity          = true;
input bool              ShowStructure          = true;
input bool              ShowEntryLevels        = true;

//+------------------------------------------------------------------+
//| Types
//+------------------------------------------------------------------+
#define SMC_PREFIX          "XAU_SMC_"
#define SMC_MAX_SWINGS      48
#define SMC_MAX_LIQ         48
#define SMC_MAX_ZONES       12
#define SMC_MAX_USED        128
#define SMC_RATES_H1        260
#define SMC_RATES_M5        240

enum ENUM_MARKET_BIAS
  {
   BIAS_NONE    = 0,
   BIAS_BULLISH = 1,
   BIAS_BEARISH = -1
  };

enum ENUM_EA_STATUS
  {
   EA_STATUS_INIT = 0,
   EA_STATUS_SYMBOL_ERROR,
   EA_STATUS_WAITING_SETUP,
   EA_STATUS_WAITING_M5,
   EA_STATUS_WAITING_RETEST,
   EA_STATUS_TRADE_OPEN,
   EA_STATUS_DAILY_LIMIT,
   EA_STATUS_DRAWDOWN_LIMIT,
   EA_STATUS_SESSION_CLOSED,
   EA_STATUS_SPREAD_HIGH,
   EA_STATUS_NEWS_DISABLED,
   EA_STATUS_MARKET_CLOSED,
   EA_STATUS_ERROR
  };

enum ENUM_SWEEP_DIR
  {
   SWEEP_NONE    = 0,
   SWEEP_BULLISH = 1,
   SWEEP_BEARISH = -1
  };

struct SwingPoint
  {
   datetime time;
   double   price;
   int      bar_index;
   bool     is_high;
   bool     broken;
   bool     valid;
  };

struct Zone
  {
   datetime time;
   int      bar_index;
   double   top;
   double   bottom;
   bool     is_demand;
   int      tests;
   bool     mitigated;
   bool     valid;
   bool     from_displacement;
  };

struct LiquidityLevel
  {
   datetime time;
   double   price;
   bool     is_high;
   bool     equal_level;
   bool     major_level;
   bool     swept;
   datetime sweep_time;
   double   sweep_extreme;
   int      bar_index;
   bool     valid;
  };

struct TradePlan
  {
   bool     valid;
   int      direction;
   ulong    setup_id;
   double   entry;
   double   sl;
   double   tp;
   double   rr;
   double   lots;
   double   zone_top;
   double   zone_bottom;
   double   sweep_extreme;
   datetime sweep_time;
   datetime confirmation_time;
   string   reason;
  };

struct PendingSetup
  {
   bool     active;
   bool     waiting_retest;
   bool     used;
   int      direction;
   ulong    setup_id;
   datetime created_time;
   datetime bos_time;
   datetime mss_time;
   datetime sweep_time;
   datetime liq_time;
   double   liq_price;
   double   sweep_extreme;
   double   ob_top;
   double   ob_bottom;
   double   bos_level;
   bool     had_displacement;
   bool     had_bos;
   bool     had_mss;
   bool     had_rejection;
  };

struct DailyState
  {
   datetime day_start;
   double   day_start_balance;
   double   peak_equity;
   int      trades_today;
   double   closed_pnl_today;
  };

//+------------------------------------------------------------------+
//| Symbol, lots, rates
//+------------------------------------------------------------------+
string            g_symbol          = "";
int               g_digits          = 2;
double            g_point           = 0.01;
double            g_tick_size       = 0.01;
double            g_volume_min      = 0.01;
double            g_volume_max      = 100.0;
double            g_volume_step     = 0.01;
int               g_stops_level     = 0;
int               g_freeze_level    = 0;
datetime          g_last_m5_bar     = 0;
datetime          g_last_h1_bar     = 0;
datetime          g_last_fail_time  = 0;
string            g_last_reason     = "";
datetime          g_last_reason_bar = 0;
string            g_status_text     = "INIT";
ENUM_EA_STATUS    g_ea_status       = EA_STATUS_INIT;
ENUM_MARKET_BIAS  g_h1_bias         = BIAS_NONE;
ENUM_MARKET_BIAS  g_m5_bias         = BIAS_NONE;
bool              g_news_warned     = false;
ulong             g_used_setups[];
int               g_used_setups_count = 0;
MqlRates          g_h1[];
MqlRates          g_m5[];
int               g_h1_copied       = 0;
int               g_m5_copied       = 0;
PendingSetup      g_pending;
DailyState        g_daily;
TradePlan         g_last_plan;
double            g_last_rr         = 0.0;

string CompactSymbol(const string name)
  {
   string n = name;
   StringToUpper(n);
   string compact = "";
   int len = StringLen(n);
   for(int i = 0; i < len; i++)
     {
      ushort c = StringGetCharacter(n, i);
      if((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))
         compact += ShortToString(c);
     }
   return compact;
  }

bool IsXAUUSDmName(const string name)
  {
   string compact = CompactSymbol(name);
   return (StringFind(compact, "XAUUSDM") >= 0);
  }

bool SymbolIsTradable(const string name)
  {
   if(!SymbolSelect(name, true))
      return false;
   long trade_mode = SymbolInfoInteger(name, SYMBOL_TRADE_MODE);
   if(trade_mode == SYMBOL_TRADE_MODE_DISABLED)
      return false;
   return true;
  }

string DetectXAUUSDm()
  {
   string requested = InpSymbol;
   StringTrimLeft(requested);
   StringTrimRight(requested);

   if(requested != "" && IsXAUUSDmName(requested))
     {
      if(SymbolSelect(requested, true))
         return requested;
     }

   if(IsXAUUSDmName(_Symbol) && SymbolSelect(_Symbol, true))
      return _Symbol;

   string exact = "";
   string fallback = "";
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string name = SymbolName(i, false);
      if(!IsXAUUSDmName(name))
         continue;
      if(fallback == "")
         fallback = name;
      string compact = CompactSymbol(name);
      if(compact == "XAUUSDM")
        {
         exact = name;
         break;
        }
     }

   string chosen = (exact != "" ? exact : fallback);
   if(chosen == "")
      return "";
   if(!SymbolSelect(chosen, true))
      return "";
   return chosen;
  }

bool LoadSymbolContract(const string name)
  {
   g_digits       = (int)SymbolInfoInteger(name, SYMBOL_DIGITS);
   g_point        = SymbolInfoDouble(name, SYMBOL_POINT);
   g_tick_size    = SymbolInfoDouble(name, SYMBOL_TRADE_TICK_SIZE);
   g_volume_min   = SymbolInfoDouble(name, SYMBOL_VOLUME_MIN);
   g_volume_max   = SymbolInfoDouble(name, SYMBOL_VOLUME_MAX);
   g_volume_step  = SymbolInfoDouble(name, SYMBOL_VOLUME_STEP);
   g_stops_level  = (int)SymbolInfoInteger(name, SYMBOL_TRADE_STOPS_LEVEL);
   g_freeze_level = (int)SymbolInfoInteger(name, SYMBOL_TRADE_FREEZE_LEVEL);

   if(g_point <= 0.0)
      return false;
   if(g_tick_size <= 0.0)
      g_tick_size = g_point;
   if(g_volume_min <= 0.0)
      g_volume_min = 0.01;
   if(g_volume_max <= 0.0)
      g_volume_max = 100.0;
   if(g_volume_step <= 0.0)
      g_volume_step = 0.01;
   return true;
  }

int VolumeDigits(const double step)
  {
   if(step >= 1.0)
      return 0;
   if(step >= 0.1)
      return 1;
   if(step >= 0.01)
      return 2;
   if(step >= 0.001)
      return 3;
   return 4;
  }

double NormalizeVolume(double lots)
  {
   double minlot = g_volume_min;
   double maxlot = g_volume_max;
   double step   = g_volume_step;
   if(step <= 0.0)
      step = 0.01;
   lots = MathFloor(lots / step + 1.0e-8) * step;
   if(lots < minlot)
      lots = minlot;
   if(lots > maxlot)
      lots = maxlot;
   return NormalizeDouble(lots, VolumeDigits(step));
  }

double CalculateLotSizeFromBalance(const double balance)
  {
   double lots = StartingLot;
   if(balance + 1.0e-8 >= FirstIncreaseBalance)
     {
      double extra = MathFloor((balance - FirstIncreaseBalance) / BalanceStep + 1.0e-10) + 1.0;
      lots = StartingLot + extra * LotIncrease;
     }
   if(lots < 0.0)
      lots = 0.0;
   return NormalizeVolume(lots);
  }

double CalculateLotSize()
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double lots = CalculateLotSizeFromBalance(balance);
   PrintFormat("Lot size calculated: %.2f", lots);
   return lots;
  }

double NormalizePrice(const double price)
  {
   double tick = g_tick_size;
   if(tick <= 0.0)
      tick = g_point;
   return NormalizeDouble(MathRound(price / tick) * tick, g_digits);
  }

bool LoadRates(const string symbol, const ENUM_TIMEFRAMES tf, const int count, MqlRates &rates[], int &copied)
  {
   copied = CopyRates(symbol, tf, 0, count, rates);
   if(copied <= 0)
      return false;
   ArraySetAsSeries(rates, true);
   return (copied >= 20);
  }

bool RefreshRates(const bool force = false)
  {
   datetime m5_now = iTime(g_symbol, InpEntryTF, 0);
   datetime h1_now = iTime(g_symbol, InpAnalysisTF, 0);
   if(!force && m5_now == g_last_m5_bar && h1_now == g_last_h1_bar && g_m5_copied > 0 && g_h1_copied > 0)
      return true;

   if(!LoadRates(g_symbol, InpAnalysisTF, InpH1LookbackBars, g_h1, g_h1_copied))
      return false;
   if(!LoadRates(g_symbol, InpEntryTF, InpM5LookbackBars, g_m5, g_m5_copied))
      return false;

   g_last_m5_bar = m5_now;
   g_last_h1_bar = h1_now;
   return true;
  }

bool IsNewM5Bar()
  {
   datetime t = iTime(g_symbol, InpEntryTF, 0);
   if(t <= 0)
      return false;
   static datetime s_last = 0;
   if(s_last == 0)
     {
      s_last = t;
      return true;
     }
   if(t != s_last)
     {
      s_last = t;
      return true;
     }
   return false;
  }

double CandleBody(const MqlRates &r)
  {
   return MathAbs(r.close - r.open);
  }

double CandleRange(const MqlRates &r)
  {
   return (r.high - r.low);
  }

bool IsBullishCandle(const MqlRates &r)
  {
   return (r.close > r.open);
  }

bool IsBearishCandle(const MqlRates &r)
  {
   return (r.close < r.open);
  }

double AverageBody(const MqlRates &rates[], const int start, const int count)
  {
   int n = ArraySize(rates);
   int used = 0;
   double sum = 0.0;
   for(int i = start; i < n && used < count; i++)
     {
      sum += CandleBody(rates[i]);
      used++;
     }
   if(used <= 0)
      return 0.0;
   return sum / used;
  }

double CalcATR(const MqlRates &rates[], const int period, const int shift)
  {
   int n = ArraySize(rates);
   if(n <= shift + period)
      return 0.0;
   double sum = 0.0;
   int used = 0;
   for(int i = shift; i < shift + period && i + 1 < n; i++)
     {
      double tr = rates[i].high - rates[i].low;
      double prev_close = rates[i + 1].close;
      tr = MathMax(tr, MathAbs(rates[i].high - prev_close));
      tr = MathMax(tr, MathAbs(rates[i].low - prev_close));
      sum += tr;
      used++;
     }
   if(used <= 0)
      return 0.0;
   return sum / used;
  }

double CurrentBid()
  {
   return SymbolInfoDouble(g_symbol, SYMBOL_BID);
  }

double CurrentAsk()
  {
   return SymbolInfoDouble(g_symbol, SYMBOL_ASK);
  }

double CurrentMid()
  {
   return (CurrentBid() + CurrentAsk()) * 0.5;
  }

int CurrentSpreadPoints()
  {
   long sp = SymbolInfoInteger(g_symbol, SYMBOL_SPREAD);
   if(sp > 0)
      return (int)sp;
   if(g_point <= 0.0)
      return 0;
   return (int)MathRound((CurrentAsk() - CurrentBid()) / g_point);
  }

bool CheckSpread()
  {
   if(!UseSpreadFilter)
      return true;
   int spread = CurrentSpreadPoints();
   if(spread > MaxSpreadPoints)
     {
      g_ea_status = EA_STATUS_SPREAD_HIGH;
      return false;
     }
   return true;
  }

datetime BeginningOfDay(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.hour = 0;
   dt.min = 0;
   dt.sec = 0;
   return StructToTime(dt);
  }

bool IsWithinTradingSession(const datetime t)
  {
   if(!UseTradingSession)
      return true;
   MqlDateTime dt;
   TimeToStruct(t, dt);
   int hour = dt.hour;
   int start_h = StartTradingHour;
   int end_h = EndTradingHour;
   if(start_h == end_h)
      return true;
   if(start_h < end_h)
      return (hour >= start_h && hour < end_h);
   return (hour >= start_h || hour < end_h);
  }

bool MarketIsOpen()
  {
   MqlTick tick;
   if(!SymbolInfoTick(g_symbol, tick))
      return false;
   datetime now = TimeCurrent();
   if(tick.time > 0 && (now - tick.time) > 300 && !MQLInfoInteger(MQL_TESTER))
      return false;
   long trade_mode = SymbolInfoInteger(g_symbol, SYMBOL_TRADE_MODE);
   if(trade_mode == SYMBOL_TRADE_MODE_DISABLED)
      return false;
   return true;
  }

bool TradingAllowed()
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return false;
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return false;
   return true;
  }

string BiasToText(const ENUM_MARKET_BIAS bias)
  {
   if(bias == BIAS_BULLISH)
      return "BULLISH";
   if(bias == BIAS_BEARISH)
      return "BEARISH";
   return "NONE";
  }

string StatusToText(const ENUM_EA_STATUS st)
  {
   switch(st)
     {
      case EA_STATUS_INIT:             return "INITIALIZING";
      case EA_STATUS_SYMBOL_ERROR:     return "XAUUSDm UNAVAILABLE";
      case EA_STATUS_WAITING_SETUP:    return "WAITING FOR SETUP";
      case EA_STATUS_WAITING_M5:       return "WAITING M5 CONFIRMATION";
      case EA_STATUS_WAITING_RETEST:   return "WAITING M5 RETEST";
      case EA_STATUS_TRADE_OPEN:       return "TRADE OPEN";
      case EA_STATUS_DAILY_LIMIT:      return "DAILY LIMIT REACHED";
      case EA_STATUS_DRAWDOWN_LIMIT:   return "DRAWDOWN LIMIT";
      case EA_STATUS_SESSION_CLOSED:   return "OUTSIDE SESSION";
      case EA_STATUS_SPREAD_HIGH:      return "SPREAD TOO HIGH";
      case EA_STATUS_NEWS_DISABLED:    return "NEWS FILTER NO-OP";
      case EA_STATUS_MARKET_CLOSED:    return "MARKET CLOSED";
      case EA_STATUS_ERROR:            return "ERROR";
     }
   return "UNKNOWN";
  }

void LogReason(const string msg)
  {
   datetime bar = iTime(g_symbol, InpEntryTF, 0);
   if(msg == g_last_reason && bar == g_last_reason_bar)
      return;
   g_last_reason = msg;
   g_last_reason_bar = bar;
   g_status_text = msg;
   Print(msg);
  }

bool SetupAlreadyUsed(const ulong id)
  {
   for(int i = 0; i < g_used_setups_count; i++)
     {
      if(g_used_setups[i] == id)
         return true;
     }
   return false;
  }

void MarkSetupUsed(const ulong id)
  {
   if(id == 0)
      return;
   if(SetupAlreadyUsed(id))
      return;
   if(g_used_setups_count >= SMC_MAX_USED)
     {
      for(int i = 1; i < g_used_setups_count; i++)
         g_used_setups[i - 1] = g_used_setups[i];
      g_used_setups_count--;
     }
   ArrayResize(g_used_setups, g_used_setups_count + 1);
   g_used_setups[g_used_setups_count] = id;
   g_used_setups_count++;
  }

ulong BuildSetupId(const int direction, const datetime liq_time, const double liq_price)
  {
   long price_key = (long)MathRound(liq_price / g_point);
   ulong id = ((ulong)liq_time) ^ (((ulong)price_key) << 5) ^ (ulong)(direction + 3);
   if(id == 0)
      id = 1;
   return id;
  }

void ResetPending()
  {
   ZeroMemory(g_pending);
  }

double PointsToPrice(const int points)
  {
   return points * g_point;
  }

//+------------------------------------------------------------------+
//| Market structure
//+------------------------------------------------------------------+
SwingPoint g_h1_highs[];
SwingPoint g_h1_lows[];
SwingPoint g_m5_highs[];
SwingPoint g_m5_lows[];
int        g_h1_high_count = 0;
int        g_h1_low_count  = 0;
int        g_m5_high_count = 0;
int        g_m5_low_count  = 0;
bool       g_h1_bullish_bos = false;
bool       g_h1_bearish_bos = false;
bool       g_h1_bullish_mss = false;
bool       g_h1_bearish_mss = false;
bool       g_m5_bullish_bos = false;
bool       g_m5_bearish_bos = false;
bool       g_m5_bullish_mss = false;
bool       g_m5_bearish_mss = false;
bool       g_m5_bullish_disp = false;
bool       g_m5_bearish_disp = false;
int        g_m5_bos_bar = -1;
int        g_m5_mss_bar = -1;
int        g_m5_disp_bar = -1;
double     g_m5_bos_level = 0.0;
double     g_h1_range_high = 0.0;
double     g_h1_range_low  = 0.0;
double     g_atr_h1 = 0.0;
double     g_atr_m5 = 0.0;
datetime   g_h1_bos_time = 0;
datetime   g_h1_mss_time = 0;
datetime   g_m5_bos_time = 0;
datetime   g_m5_mss_time = 0;

bool IsSwingHigh(const MqlRates &rates[], const int i, const int strength)
  {
   int n = ArraySize(rates);
   if(strength < 1)
      return false;
   if(i - strength < 1)
      return false;
   if(i + strength >= n)
      return false;
   double h = rates[i].high;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i - k].high >= h)
         return false;
      if(rates[i + k].high > h)
         return false;
     }
   return true;
  }

bool IsSwingLow(const MqlRates &rates[], const int i, const int strength)
  {
   int n = ArraySize(rates);
   if(strength < 1)
      return false;
   if(i - strength < 1)
      return false;
   if(i + strength >= n)
      return false;
   double l = rates[i].low;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i - k].low <= l)
         return false;
      if(rates[i + k].low < l)
         return false;
     }
   return true;
  }

int FindSwingHighs(const MqlRates &rates[], const int strength, SwingPoint &out[], const int max_count)
  {
   ArrayResize(out, 0);
   int n = ArraySize(rates);
   int count = 0;
   int start = strength + 1;
   int end = n - 1 - strength;
   for(int i = start; i <= end; i++)
     {
      if(!IsSwingHigh(rates, i, strength))
         continue;
      int idx = count;
      ArrayResize(out, count + 1);
      out[idx].time = rates[i].time;
      out[idx].price = rates[i].high;
      out[idx].bar_index = i;
      out[idx].is_high = true;
      out[idx].broken = false;
      out[idx].valid = true;
      count++;
      if(count >= max_count)
         break;
     }
   return count;
  }

int FindSwingLows(const MqlRates &rates[], const int strength, SwingPoint &out[], const int max_count)
  {
   ArrayResize(out, 0);
   int n = ArraySize(rates);
   int count = 0;
   int start = strength + 1;
   int end = n - 1 - strength;
   for(int i = start; i <= end; i++)
     {
      if(!IsSwingLow(rates, i, strength))
         continue;
      int idx = count;
      ArrayResize(out, count + 1);
      out[idx].time = rates[i].time;
      out[idx].price = rates[i].low;
      out[idx].bar_index = i;
      out[idx].is_high = false;
      out[idx].broken = false;
      out[idx].valid = true;
      count++;
      if(count >= max_count)
         break;
     }
   return count;
  }

void MarkBrokenSwings(const MqlRates &rates[], SwingPoint &highs[], const int high_count, SwingPoint &lows[], const int low_count)
  {
   int n = ArraySize(rates);
   for(int i = 0; i < high_count; i++)
     {
      highs[i].broken = false;
      int bar = highs[i].bar_index;
      for(int j = 1; j < bar && j < n; j++)
        {
         if(rates[j].close > highs[i].price)
           {
            highs[i].broken = true;
            break;
           }
        }
     }
   for(int i = 0; i < low_count; i++)
     {
      lows[i].broken = false;
      int bar = lows[i].bar_index;
      for(int j = 1; j < bar && j < n; j++)
        {
         if(rates[j].close < lows[i].price)
           {
            lows[i].broken = true;
            break;
           }
        }
     }
  }

ENUM_MARKET_BIAS ClassifyHHHL(const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count, const datetime before_time)
  {
   double recent_highs[3];
   double recent_lows[3];
   int hc = 0;
   int lc = 0;
   for(int i = 0; i < high_count && hc < 3; i++)
     {
      if(before_time > 0 && highs[i].time > before_time)
         continue;
      recent_highs[hc++] = highs[i].price;
     }
   for(int i = 0; i < low_count && lc < 3; i++)
     {
      if(before_time > 0 && lows[i].time > before_time)
         continue;
      recent_lows[lc++] = lows[i].price;
     }
   if(hc < 2 || lc < 2)
      return BIAS_NONE;

   bool hh = (recent_highs[0] > recent_highs[1]);
   bool lh = (recent_highs[0] < recent_highs[1]);
   bool hl = (recent_lows[0] > recent_lows[1]);
   bool ll = (recent_lows[0] < recent_lows[1]);

   if(hh && hl)
      return BIAS_BULLISH;
   if(lh && ll)
      return BIAS_BEARISH;
   return BIAS_NONE;
  }

bool FindMostRecentUnbrokenHigh(const SwingPoint &highs[], const int high_count, const int max_bar, SwingPoint &out)
  {
   for(int i = 0; i < high_count; i++)
     {
      if(highs[i].bar_index <= max_bar)
         continue;
      if(highs[i].broken)
         continue;
      out = highs[i];
      return true;
     }
   for(int i = 0; i < high_count; i++)
     {
      if(highs[i].bar_index <= max_bar)
         continue;
      out = highs[i];
      return true;
     }
   return false;
  }

bool FindMostRecentUnbrokenLow(const SwingPoint &lows[], const int low_count, const int max_bar, SwingPoint &out)
  {
   for(int i = 0; i < low_count; i++)
     {
      if(lows[i].bar_index <= max_bar)
         continue;
      if(lows[i].broken)
         continue;
      out = lows[i];
      return true;
     }
   for(int i = 0; i < low_count; i++)
     {
      if(lows[i].bar_index <= max_bar)
         continue;
      out = lows[i];
      return true;
     }
   return false;
  }

bool DetectClosedBreak(const MqlRates &rates[], const double level, const int direction, const int after_older_than_bar, int &break_bar)
  {
   int n = ArraySize(rates);
   int newest = 1;
   int oldest = after_older_than_bar - 1;
   if(oldest < newest)
      return false;
   if(oldest >= n)
      oldest = n - 1;
   for(int i = oldest; i >= newest; i--)
     {
      if(direction > 0 && rates[i].close > level)
        {
         break_bar = i;
         return true;
        }
      if(direction < 0 && rates[i].close < level)
        {
         break_bar = i;
         return true;
        }
     }
   return false;
  }

bool DetectBullishBOSOn(const MqlRates &rates[], const SwingPoint &highs[], const int high_count, const int fresh_bars, int &break_bar, double &level, datetime &break_time)
  {
   break_bar = -1;
   level = 0.0;
   break_time = 0;
   SwingPoint sh;
   ZeroMemory(sh);
   if(!FindMostRecentUnbrokenHigh(highs, high_count, 1, sh) && high_count > 0)
      sh = highs[0];
   else
     if(high_count <= 0)
        return false;
   int bar = -1;
   if(!DetectClosedBreak(rates, sh.price, 1, sh.bar_index, bar))
      return false;
   if(fresh_bars > 0 && bar > fresh_bars)
      return false;
   break_bar = bar;
   level = sh.price;
   break_time = rates[bar].time;
   return true;
  }

bool DetectBearishBOSOn(const MqlRates &rates[], const SwingPoint &lows[], const int low_count, const int fresh_bars, int &break_bar, double &level, datetime &break_time)
  {
   break_bar = -1;
   level = 0.0;
   break_time = 0;
   SwingPoint sl;
   ZeroMemory(sl);
   if(!FindMostRecentUnbrokenLow(lows, low_count, 1, sl) && low_count > 0)
      sl = lows[0];
   else
     if(low_count <= 0)
        return false;
   int bar = -1;
   if(!DetectClosedBreak(rates, sl.price, -1, sl.bar_index, bar))
      return false;
   if(fresh_bars > 0 && bar > fresh_bars)
      return false;
   break_bar = bar;
   level = sl.price;
   break_time = rates[bar].time;
   return true;
  }

bool DetectBullishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBullishBOSOn(g_h1, g_h1_highs, g_h1_high_count, 36, bar, level, t);
   g_h1_bullish_bos = ok;
   if(ok)
      g_h1_bos_time = t;
   return ok;
  }

bool DetectBearishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBearishBOSOn(g_h1, g_h1_lows, g_h1_low_count, 36, bar, level, t);
   g_h1_bearish_bos = ok;
   if(ok)
      g_h1_bos_time = t;
   return ok;
  }

bool DetectBullishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBullishBOSOn(g_h1, g_h1_highs, g_h1_high_count, 40, bar, level, t))
     {
      g_h1_bullish_mss = false;
      return false;
     }
   datetime before = g_h1[bar].time;
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, before);
   bool ok = (prior == BIAS_BEARISH || prior == BIAS_NONE);
   if(prior == BIAS_BULLISH)
      ok = false;
   if(ok)
     {
      bool had_ll = false;
      if(g_h1_low_count >= 2)
         had_ll = (g_h1_lows[0].price < g_h1_lows[1].price) || (prior == BIAS_BEARISH);
      ok = had_ll || (prior == BIAS_BEARISH);
     }
   g_h1_bullish_mss = ok;
   if(ok)
      g_h1_mss_time = t;
   return ok;
  }

bool DetectBearishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBearishBOSOn(g_h1, g_h1_lows, g_h1_low_count, 40, bar, level, t))
     {
      g_h1_bearish_mss = false;
      return false;
     }
   datetime before = g_h1[bar].time;
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, before);
   bool ok = (prior == BIAS_BULLISH);
   if(ok)
     {
      g_h1_bearish_mss = true;
      g_h1_mss_time = t;
      return true;
     }
   g_h1_bearish_mss = false;
   return false;
  }

bool DetectM5BullishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBullishBOSOn(g_m5, g_m5_highs, g_m5_high_count, InpM5ConfirmMaxBars, bar, level, t);
   g_m5_bullish_bos = ok;
   if(ok)
     {
      g_m5_bos_bar = bar;
      g_m5_bos_level = level;
      g_m5_bos_time = t;
     }
   return ok;
  }

bool DetectM5BearishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBearishBOSOn(g_m5, g_m5_lows, g_m5_low_count, InpM5ConfirmMaxBars, bar, level, t);
   g_m5_bearish_bos = ok;
   if(ok)
     {
      g_m5_bos_bar = bar;
      g_m5_bos_level = level;
      g_m5_bos_time = t;
     }
   return ok;
  }

bool DetectM5BullishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBullishBOSOn(g_m5, g_m5_highs, g_m5_high_count, InpM5ConfirmMaxBars, bar, level, t))
     {
      g_m5_bullish_mss = false;
      return false;
     }
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, g_m5[bar].time);
   bool ok = (prior == BIAS_BEARISH);
   g_m5_bullish_mss = ok;
   if(ok)
     {
      g_m5_mss_bar = bar;
      g_m5_mss_time = t;
      g_m5_bos_level = level;
     }
   return ok;
  }

bool DetectM5BearishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBearishBOSOn(g_m5, g_m5_lows, g_m5_low_count, InpM5ConfirmMaxBars, bar, level, t))
     {
      g_m5_bearish_mss = false;
      return false;
     }
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, g_m5[bar].time);
   bool ok = (prior == BIAS_BULLISH);
   g_m5_bearish_mss = ok;
   if(ok)
     {
      g_m5_mss_bar = bar;
      g_m5_mss_time = t;
      g_m5_bos_level = level;
     }
   return ok;
  }

bool IsDisplacementCandle(const MqlRates &rates[], const int i, const int direction)
  {
   int n = ArraySize(rates);
   if(i < 1 || i >= n)
      return false;
   double body = CandleBody(rates[i]);
   double range = CandleRange(rates[i]);
   if(range <= 0.0)
      return false;
   double avg = AverageBody(rates, i, 20);
   if(avg <= 0.0)
      avg = range;
   if(body < InpDisplacementFactor * avg)
      return false;
   if(direction > 0)
     {
      if(!IsBullishCandle(rates[i]))
         return false;
      if((rates[i].close - rates[i].low) < 0.55 * range)
         return false;
     }
   else
     {
      if(!IsBearishCandle(rates[i]))
         return false;
      if((rates[i].high - rates[i].close) < 0.55 * range)
         return false;
     }
   return true;
  }

bool DetectM5Displacement(const int direction, int &disp_bar)
  {
   disp_bar = -1;
   int max_bar = InpM5ConfirmMaxBars;
   int n = ArraySize(g_m5);
   if(n < 5)
      return false;
   for(int i = 1; i <= max_bar && i < n; i++)
     {
      if(IsDisplacementCandle(g_m5, i, direction))
        {
         disp_bar = i;
         return true;
        }
     }
   return false;
  }

bool IsRejectionCandle(const MqlRates &r, const int direction)
  {
   double range = CandleRange(r);
   if(range <= 0.0)
      return false;
   if(direction > 0)
     {
      double lower = MathMin(r.open, r.close) - r.low;
      if(lower < 0.45 * range)
         return false;
      if(r.close < (r.low + 0.5 * range))
         return false;
      return true;
     }
   double upper = r.high - MathMax(r.open, r.close);
   if(upper < 0.45 * range)
      return false;
   if(r.close > (r.high - 0.5 * range))
      return false;
   return true;
  }

ENUM_MARKET_BIAS GetM5Bias()
  {
   ENUM_MARKET_BIAS seq = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, 0);
   if(g_m5_bullish_mss)
      return BIAS_BULLISH;
   if(g_m5_bearish_mss)
      return BIAS_BEARISH;
   if(g_m5_bullish_bos && seq != BIAS_BEARISH)
      return BIAS_BULLISH;
   if(g_m5_bearish_bos && seq != BIAS_BULLISH)
      return BIAS_BEARISH;
   return seq;
  }

ENUM_MARKET_BIAS GetH1Bias()
  {
   if(!UseMarketStructure)
      return BIAS_NONE;

   ENUM_MARKET_BIAS seq = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, 0);

   bool bull_mss = DetectBullishMSS();
   bool bear_mss = DetectBearishMSS();
   bool bull_bos = DetectBullishBOS();
   bool bear_bos = DetectBearishBOS();

   if(bull_mss && !bear_mss)
      return BIAS_BULLISH;
   if(bear_mss && !bull_mss)
      return BIAS_BEARISH;

   if(seq == BIAS_BULLISH)
      return BIAS_BULLISH;
   if(seq == BIAS_BEARISH)
      return BIAS_BEARISH;

   if(bull_bos && !bear_bos)
      return BIAS_BULLISH;
   if(bear_bos && !bull_bos)
      return BIAS_BEARISH;

   return BIAS_NONE;
  }

void UpdateH1Range()
  {
   g_h1_range_high = 0.0;
   g_h1_range_low = 0.0;
   int n = ArraySize(g_h1);
   int look = MathMin(40, n - 1);
   if(look < 5)
      return;
   g_h1_range_high = g_h1[1].high;
   g_h1_range_low = g_h1[1].low;
   for(int i = 1; i <= look; i++)
     {
      if(g_h1[i].high > g_h1_range_high)
         g_h1_range_high = g_h1[i].high;
      if(g_h1[i].low < g_h1_range_low)
         g_h1_range_low = g_h1[i].low;
     }
   if(g_h1_high_count > 0 && g_h1_highs[0].price > g_h1_range_high)
      g_h1_range_high = g_h1_highs[0].price;
   if(g_h1_low_count > 0 && g_h1_lows[0].price < g_h1_range_low)
      g_h1_range_low = g_h1_lows[0].price;
  }

bool PriceInDiscount()
  {
   if(g_h1_range_high <= g_h1_range_low)
      return false;
   double eq = (g_h1_range_high + g_h1_range_low) * 0.5;
   return (CurrentMid() <= eq);
  }

bool PriceInPremium()
  {
   if(g_h1_range_high <= g_h1_range_low)
      return false;
   double eq = (g_h1_range_high + g_h1_range_low) * 0.5;
   return (CurrentMid() >= eq);
  }

bool AnalyzeStructure()
  {
   g_h1_high_count = FindSwingHighs(g_h1, InpH1SwingStrength, g_h1_highs, SMC_MAX_SWINGS);
   g_h1_low_count  = FindSwingLows(g_h1, InpH1SwingStrength, g_h1_lows, SMC_MAX_SWINGS);
   g_m5_high_count = FindSwingHighs(g_m5, InpM5SwingStrength, g_m5_highs, SMC_MAX_SWINGS);
   g_m5_low_count  = FindSwingLows(g_m5, InpM5SwingStrength, g_m5_lows, SMC_MAX_SWINGS);

   MarkBrokenSwings(g_h1, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count);
   MarkBrokenSwings(g_m5, g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count);

   g_atr_h1 = CalcATR(g_h1, 14, 1);
   g_atr_m5 = CalcATR(g_m5, 14, 1);
   UpdateH1Range();

   g_h1_bias = GetH1Bias();

   int disp_bar = -1;
   g_m5_bullish_disp = DetectM5Displacement(1, disp_bar);
   if(g_m5_bullish_disp)
      g_m5_disp_bar = disp_bar;
   g_m5_bearish_disp = DetectM5Displacement(-1, disp_bar);
   if(g_m5_bearish_disp && !g_m5_bullish_disp)
      g_m5_disp_bar = disp_bar;

   DetectM5BullishBOS();
   DetectM5BearishBOS();
   DetectM5BullishMSS();
   DetectM5BearishMSS();
   g_m5_bias = GetM5Bias();
   return true;
  }

//+------------------------------------------------------------------+
//| Liquidity and zones
//+------------------------------------------------------------------+
LiquidityLevel g_liq_highs[];
LiquidityLevel g_liq_lows[];
int            g_liq_high_count = 0;
int            g_liq_low_count  = 0;
Zone           g_demand_zones[];
Zone           g_supply_zones[];
int            g_demand_count = 0;
int            g_supply_count = 0;
Zone           g_active_demand;
Zone           g_active_supply;
LiquidityLevel g_last_bull_sweep;
LiquidityLevel g_last_bear_sweep;
bool           g_bullish_sweep = false;
bool           g_bearish_sweep = false;

double EqualTolerance()
  {
   double by_points = PointsToPrice(EqualLevelPoints);
   double by_atr = g_atr_h1 * 0.12;
   if(by_atr <= 0.0)
      return by_points;
   return MathMax(by_points, by_atr);
  }

bool AddLiquidityLevel(LiquidityLevel &arr[], int &count, const datetime t, const double price, const int bar, const bool is_high, const bool equal_level, const bool major_level)
  {
   for(int i = 0; i < count; i++)
     {
      if(MathAbs(arr[i].price - price) <= EqualTolerance())
        {
         arr[i].equal_level = true;
         if(major_level)
            arr[i].major_level = true;
         return true;
        }
     }
   if(count >= SMC_MAX_LIQ)
      return false;
   ArrayResize(arr, count + 1);
   arr[count].time = t;
   arr[count].price = price;
   arr[count].is_high = is_high;
   arr[count].equal_level = equal_level;
   arr[count].major_level = major_level;
   arr[count].swept = false;
   arr[count].sweep_time = 0;
   arr[count].sweep_extreme = 0.0;
   arr[count].bar_index = bar;
   arr[count].valid = true;
   count++;
   return true;
  }

void DetectEqualLevels(const SwingPoint &swings[], const int swing_count, LiquidityLevel &arr[], int &count, const bool is_high)
  {
   double tol = EqualTolerance();
   for(int i = 0; i < swing_count; i++)
     {
      for(int j = i + 1; j < swing_count; j++)
        {
         if(MathAbs(swings[i].price - swings[j].price) <= tol)
           {
            AddLiquidityLevel(arr, count, swings[i].time, swings[i].price, swings[i].bar_index, is_high, true, true);
            break;
           }
        }
     }
  }

void DetectConsolidationLiquidity()
  {
   int n = ArraySize(g_h1);
   int window = 12;
   if(n < window + 2)
      return;
   double max_h = g_h1[1].high;
   double min_l = g_h1[1].low;
   datetime high_t = g_h1[1].time;
   datetime low_t = g_h1[1].time;
   int high_bar = 1;
   int low_bar = 1;
   for(int i = 1; i <= window; i++)
     {
      if(g_h1[i].high >= max_h)
        {
         max_h = g_h1[i].high;
         high_t = g_h1[i].time;
         high_bar = i;
        }
      if(g_h1[i].low <= min_l)
        {
         min_l = g_h1[i].low;
         low_t = g_h1[i].time;
         low_bar = i;
        }
     }
   double rng = max_h - min_l;
   if(g_atr_h1 > 0.0 && rng < 1.15 * g_atr_h1)
     {
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, high_t, max_h, high_bar, true, false, true);
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, low_t, min_l, low_bar, false, false, true);
     }
  }

void BuildLiquidityLevels()
  {
   g_liq_high_count = 0;
   g_liq_low_count = 0;
   ArrayResize(g_liq_highs, 0);
   ArrayResize(g_liq_lows, 0);

   int swing_use = MathMin(12, g_h1_high_count);
   for(int i = 0; i < swing_use; i++)
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, g_h1_highs[i].time, g_h1_highs[i].price, g_h1_highs[i].bar_index, true, false, (i == 0));

   swing_use = MathMin(12, g_h1_low_count);
   for(int i = 0; i < swing_use; i++)
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, g_h1_lows[i].time, g_h1_lows[i].price, g_h1_lows[i].bar_index, false, false, (i == 0));

   DetectEqualLevels(g_h1_highs, g_h1_high_count, g_liq_highs, g_liq_high_count, true);
   DetectEqualLevels(g_h1_lows, g_h1_low_count, g_liq_lows, g_liq_low_count, false);

   int n = ArraySize(g_h1);
   if(n > 25)
     {
      double major_high = g_h1[1].high;
      double major_low = g_h1[1].low;
      datetime ht = g_h1[1].time;
      datetime lt = g_h1[1].time;
      int hb = 1;
      int lb = 1;
      int look = MathMin(80, n - 1);
      for(int i = 1; i <= look; i++)
        {
         if(g_h1[i].high >= major_high)
           {
            major_high = g_h1[i].high;
            ht = g_h1[i].time;
            hb = i;
           }
         if(g_h1[i].low <= major_low)
           {
            major_low = g_h1[i].low;
            lt = g_h1[i].time;
            lb = i;
           }
        }
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, ht, major_high, hb, true, false, true);
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, lt, major_low, lb, false, false, true);
     }

   DetectConsolidationLiquidity();
  }

bool LevelIsMeaningful(const LiquidityLevel &lv)
  {
   if(!lv.valid)
      return false;
   return (lv.equal_level || lv.major_level || lv.bar_index > 0);
  }

bool DetectSweepAgainstLevel(const LiquidityLevel &lv, const int direction, LiquidityLevel &result)
  {
   int n = ArraySize(g_m5);
   int max_age = SweepMaxAgeM5Bars;
   if(n < 4)
      return false;

   double min_pierce = PointsToPrice(MathMax(20, SweepMinPiercePoints));
   if(g_atr_m5 > 0.0)
      min_pierce = MathMax(min_pierce, g_atr_m5 * 0.08);

   double max_close_beyond = min_pierce * 0.35;
   double level = lv.price;

   for(int i = 1; i <= max_age && i < n; i++)
     {
      if(direction > 0)
        {
         double extreme = g_m5[i].low;
         if(g_m5[i].low >= level - min_pierce * 0.25)
            continue;
         if(level - g_m5[i].low < min_pierce)
            continue;

         bool reclaimed = false;
         datetime reclaim_time = 0;
         double reclaim_close = 0.0;
         int last = MathMin(i, 4);
         for(int k = i; k >= 1 && k >= i - 3; k--)
           {
            if(g_m5[k].close > level - max_close_beyond)
              {
               reclaimed = true;
               reclaim_time = g_m5[k].time;
               reclaim_close = g_m5[k].close;
               if(k < i)
                  extreme = MathMin(extreme, g_m5[i].low);
              }
           }
         if(!reclaimed)
            continue;
         if(reclaim_close <= extreme)
            continue;

         result = lv;
         result.swept = true;
         result.sweep_time = reclaim_time;
         result.sweep_extreme = MathMin(g_m5[i].low, extreme);
         return true;
        }
      else
        {
         double extreme = g_m5[i].high;
         if(g_m5[i].high <= level + min_pierce * 0.25)
            continue;
         if(g_m5[i].high - level < min_pierce)
            continue;

         bool reclaimed = false;
         datetime reclaim_time = 0;
         double reclaim_close = 0.0;
         for(int k = i; k >= 1 && k >= i - 3; k--)
           {
            if(g_m5[k].close < level + max_close_beyond)
              {
               reclaimed = true;
               reclaim_time = g_m5[k].time;
               reclaim_close = g_m5[k].close;
              }
           }
         if(!reclaimed)
            continue;
         if(reclaim_close >= extreme)
            continue;

         result = lv;
         result.swept = true;
         result.sweep_time = reclaim_time;
         result.sweep_extreme = MathMax(g_m5[i].high, extreme);
         return true;
        }
     }
   return false;
  }

bool DetectLiquiditySweep(const int direction, LiquidityLevel &out_sweep)
  {
   ZeroMemory(out_sweep);
   if(!UseLiquiditySweep)
      return false;

   if(direction > 0)
     {
      for(int i = 0; i < g_liq_low_count; i++)
        {
         if(!LevelIsMeaningful(g_liq_lows[i]))
            continue;
         LiquidityLevel tmp;
         if(DetectSweepAgainstLevel(g_liq_lows[i], 1, tmp))
           {
            out_sweep = tmp;
            return true;
           }
        }
     }
   else
     {
      for(int i = 0; i < g_liq_high_count; i++)
        {
         if(!LevelIsMeaningful(g_liq_highs[i]))
            continue;
         LiquidityLevel tmp;
         if(DetectSweepAgainstLevel(g_liq_highs[i], -1, tmp))
           {
            out_sweep = tmp;
            return true;
           }
        }
     }
   return false;
  }

int CountZoneTests(const MqlRates &rates[], const Zone &z, const int from_bar)
  {
   int tests = 0;
   bool inside = false;
   for(int i = from_bar - 1; i >= 1; i--)
     {
      bool touch = (rates[i].low <= z.top && rates[i].high >= z.bottom);
      if(touch && !inside)
        {
         tests++;
         inside = true;
        }
      else
         if(!touch)
            inside = false;
     }
   return tests;
  }

bool ZoneFullyMitigated(const MqlRates &rates[], const Zone &z, const int from_bar)
  {
   for(int i = from_bar - 1; i >= 1; i--)
     {
      if(z.is_demand && rates[i].close < z.bottom)
         return true;
      if(!z.is_demand && rates[i].close > z.top)
         return true;
     }
   return false;
  }

bool BuildZoneFromImpulse(const MqlRates &rates[], const int impulse_bar, const bool is_demand, Zone &z)
  {
   int n = ArraySize(rates);
   if(impulse_bar + 1 >= n)
      return false;

   int search_end = MathMin(impulse_bar + 6, n - 1);
   int found = -1;
   double top = 0.0;
   double bottom = 0.0;
   datetime t = 0;

   for(int j = impulse_bar + 1; j <= search_end; j++)
     {
      if(is_demand && IsBearishCandle(rates[j]))
        {
         if(found < 0)
           {
            found = j;
            top = rates[j].high;
            bottom = rates[j].low;
            t = rates[j].time;
           }
         else
           {
            top = MathMax(top, rates[j].high);
            bottom = MathMin(bottom, rates[j].low);
           }
        }
      else
         if(!is_demand && IsBullishCandle(rates[j]))
           {
            if(found < 0)
              {
               found = j;
               top = rates[j].high;
               bottom = rates[j].low;
               t = rates[j].time;
              }
            else
              {
               top = MathMax(top, rates[j].high);
               bottom = MathMin(bottom, rates[j].low);
              }
           }
         else
            if(found >= 0)
               break;
     }

   if(found < 0)
     {
      int j = impulse_bar + 1;
      found = j;
      top = rates[j].high;
      bottom = rates[j].low;
      t = rates[j].time;
     }

   if(top - bottom <= 0.0)
      return false;

   z.time = t;
   z.bar_index = found;
   z.top = top;
   z.bottom = bottom;
   z.is_demand = is_demand;
   z.from_displacement = true;
   z.valid = true;
   z.mitigated = ZoneFullyMitigated(rates, z, found);
   z.tests = CountZoneTests(rates, z, found);
   if(z.mitigated)
      z.valid = false;
   if(z.tests > ZoneMaxTests)
      z.valid = false;
   return z.valid;
  }

bool ImpulseBrokeStructure(const MqlRates &rates[], const int impulse_bar, const bool bullish, const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count)
  {
   if(bullish)
     {
      for(int i = 0; i < high_count; i++)
        {
         if(highs[i].bar_index <= impulse_bar)
            continue;
         if(rates[impulse_bar].close > highs[i].price)
            return true;
        }
      if(impulse_bar + 3 < ArraySize(rates))
        {
         double prior_high = rates[impulse_bar + 1].high;
         for(int k = impulse_bar + 1; k <= impulse_bar + 8 && k < ArraySize(rates); k++)
            prior_high = MathMax(prior_high, rates[k].high);
         if(rates[impulse_bar].close > prior_high)
            return true;
        }
     }
   else
     {
      for(int i = 0; i < low_count; i++)
        {
         if(lows[i].bar_index <= impulse_bar)
            continue;
         if(rates[impulse_bar].close < lows[i].price)
            return true;
        }
      if(impulse_bar + 3 < ArraySize(rates))
        {
         double prior_low = rates[impulse_bar + 1].low;
         for(int k = impulse_bar + 1; k <= impulse_bar + 8 && k < ArraySize(rates); k++)
            prior_low = MathMin(prior_low, rates[k].low);
         if(rates[impulse_bar].close < prior_low)
            return true;
        }
     }
   return false;
  }

int CollectZones(const MqlRates &rates[], const bool is_demand, const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count, Zone &out[], const int max_scan)
  {
   ArrayResize(out, 0);
   int count = 0;
   int n = ArraySize(rates);
   int scan = MathMin(max_scan, n - 8);
   int dir = is_demand ? 1 : -1;
   for(int i = 2; i <= scan; i++)
     {
      if(!IsDisplacementCandle(rates, i, dir))
         continue;
      if(!ImpulseBrokeStructure(rates, i, is_demand, highs, high_count, lows, low_count))
         continue;
      Zone z;
      ZeroMemory(z);
      if(!BuildZoneFromImpulse(rates, i, is_demand, z))
         continue;
      ArrayResize(out, count + 1);
      out[count] = z;
      count++;
      if(count >= SMC_MAX_ZONES)
         break;
     }
   return count;
  }

bool FindDemandZone(Zone &out_zone)
  {
   ZeroMemory(out_zone);
   if(!UseOrderBlocks)
      return false;
   g_demand_count = CollectZones(g_h1, true, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, g_demand_zones, 80);
   if(g_demand_count <= 0)
      return false;
   out_zone = g_demand_zones[0];
   return out_zone.valid;
  }

bool FindSupplyZone(Zone &out_zone)
  {
   ZeroMemory(out_zone);
   if(!UseOrderBlocks)
      return false;
   g_supply_count = CollectZones(g_h1, false, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, g_supply_zones, 80);
   if(g_supply_count <= 0)
      return false;
   out_zone = g_supply_zones[0];
   return out_zone.valid;
  }

bool PriceNearZone(const Zone &z, const double atr_mult)
  {
   if(!z.valid)
      return false;
   double px = CurrentMid();
   if(px <= z.top && px >= z.bottom)
      return true;
   double buf = 0.0;
   if(g_atr_h1 > 0.0)
      buf = g_atr_h1 * atr_mult;
   buf = MathMax(buf, PointsToPrice(ZoneApproachPoints));
   if(px < z.bottom && (z.bottom - px) <= buf)
      return true;
   if(px > z.top && (px - z.top) <= buf)
      return true;
   return false;
  }

bool PriceNearLevel(const double level, const double atr_mult)
  {
   double px = CurrentMid();
   double buf = PointsToPrice(ZoneApproachPoints);
   if(g_atr_h1 > 0.0)
      buf = MathMax(buf, g_atr_h1 * atr_mult);
   return (MathAbs(px - level) <= buf);
  }

bool PriceAtBullishArea()
  {
   if(g_active_demand.valid && PriceNearZone(g_active_demand, 0.35))
      return true;
   if(g_h1_low_count > 0 && PriceNearLevel(g_h1_lows[0].price, 0.30))
      return true;
   if(g_liq_low_count > 0 && PriceNearLevel(g_liq_lows[0].price, 0.30))
      return true;
   if(g_bullish_sweep)
      return true;
   if(RequireDiscountPremium && PriceInDiscount())
      return true;
   if(!RequireDiscountPremium && PriceInDiscount())
      return true;
   return false;
  }

bool PriceAtBearishArea()
  {
   if(g_active_supply.valid && PriceNearZone(g_active_supply, 0.35))
      return true;
   if(g_h1_high_count > 0 && PriceNearLevel(g_h1_highs[0].price, 0.30))
      return true;
   if(g_liq_high_count > 0 && PriceNearLevel(g_liq_highs[0].price, 0.30))
      return true;
   if(g_bearish_sweep)
      return true;
   if(RequireDiscountPremium && PriceInPremium())
      return true;
   if(!RequireDiscountPremium && PriceInPremium())
      return true;
   return false;
  }

void AnalyzeLiquidityAndZones()
  {
   BuildLiquidityLevels();
   FindDemandZone(g_active_demand);
   FindSupplyZone(g_active_supply);

   g_bullish_sweep = DetectLiquiditySweep(1, g_last_bull_sweep);
   g_bearish_sweep = DetectLiquiditySweep(-1, g_last_bear_sweep);
  }

//+------------------------------------------------------------------+
//| Setup confirmation, SL/TP
//+------------------------------------------------------------------+
bool FindLastBearishBefore(const int before_bar, const int search, double &top, double &bottom, datetime &t)
  {
   int n = ArraySize(g_m5);
   int end = MathMin(before_bar + search, n - 1);
   for(int i = before_bar + 1; i <= end; i++)
     {
      if(IsBearishCandle(g_m5[i]) || CandleBody(g_m5[i]) < g_atr_m5 * 0.15)
        {
         top = g_m5[i].high;
         bottom = g_m5[i].low;
         t = g_m5[i].time;
         if(i + 1 <= end && IsBearishCandle(g_m5[i + 1]))
           {
            top = MathMax(top, g_m5[i + 1].high);
            bottom = MathMin(bottom, g_m5[i + 1].low);
           }
         return true;
        }
     }
   if(before_bar + 1 < n)
     {
      top = g_m5[before_bar + 1].high;
      bottom = g_m5[before_bar + 1].low;
      t = g_m5[before_bar + 1].time;
      return true;
     }
   return false;
  }

bool FindLastBullishBefore(const int before_bar, const int search, double &top, double &bottom, datetime &t)
  {
   int n = ArraySize(g_m5);
   int end = MathMin(before_bar + search, n - 1);
   for(int i = before_bar + 1; i <= end; i++)
     {
      if(IsBullishCandle(g_m5[i]) || CandleBody(g_m5[i]) < g_atr_m5 * 0.15)
        {
         top = g_m5[i].high;
         bottom = g_m5[i].low;
         t = g_m5[i].time;
         if(i + 1 <= end && IsBullishCandle(g_m5[i + 1]))
           {
            top = MathMax(top, g_m5[i + 1].high);
            bottom = MathMin(bottom, g_m5[i + 1].low);
           }
         return true;
        }
     }
   if(before_bar + 1 < n)
     {
      top = g_m5[before_bar + 1].high;
      bottom = g_m5[before_bar + 1].low;
      t = g_m5[before_bar + 1].time;
      return true;
     }
   return false;
  }

bool M5RetestConfirmed(const int direction, const double ob_top, const double ob_bottom)
  {
   if(ArraySize(g_m5) < 3)
      return false;
   MqlRates c = g_m5[1];
   double buf = PointsToPrice(5);
   if(g_atr_m5 > 0.0)
      buf = MathMax(buf, g_atr_m5 * 0.05);

   if(direction > 0)
     {
      bool touched = (c.low <= ob_top + buf && c.low >= ob_bottom - buf) ||
                     (c.low <= ob_top && c.high >= ob_bottom);
      if(!touched)
         return false;
      if(c.close < ob_bottom - buf)
         return false;
      if(IsBearishCandle(c) && !IsRejectionCandle(c, 1))
         return false;
      return (IsBullishCandle(c) || IsRejectionCandle(c, 1));
     }

   bool touched = (c.high >= ob_bottom - buf && c.high <= ob_top + buf) ||
                  (c.high >= ob_bottom && c.low <= ob_top);
   if(!touched)
      return false;
   if(c.close > ob_top + buf)
      return false;
   if(IsBullishCandle(c) && !IsRejectionCandle(c, -1))
      return false;
   return (IsBearishCandle(c) || IsRejectionCandle(c, -1));
  }

bool IsChasingMove(const int direction, const double entry, const double tp)
  {
   if(tp == entry)
      return true;
   double px = (direction > 0 ? CurrentAsk() : CurrentBid());
   if(direction > 0)
     {
      if(px >= tp)
         return true;
      if(px > entry && (px - entry) > 0.35 * MathAbs(tp - entry))
         return true;
      if(ArraySize(g_m5) > 1)
        {
         double range = CandleRange(g_m5[1]);
         if(IsBullishCandle(g_m5[1]) && g_atr_m5 > 0.0 && range > 2.2 * g_atr_m5)
           {
            if(g_m5[1].close > entry && !M5RetestConfirmed(1, g_pending.ob_top, g_pending.ob_bottom))
               return true;
           }
        }
     }
   else
     {
      if(px <= tp)
         return true;
      if(px < entry && (entry - px) > 0.35 * MathAbs(entry - tp))
         return true;
      if(ArraySize(g_m5) > 1)
        {
         double range = CandleRange(g_m5[1]);
         if(IsBearishCandle(g_m5[1]) && g_atr_m5 > 0.0 && range > 2.2 * g_atr_m5)
           {
            if(g_m5[1].close < entry && !M5RetestConfirmed(-1, g_pending.ob_top, g_pending.ob_bottom))
               return true;
           }
        }
     }
   return false;
  }

double FindInvalidationLow()
  {
   double sl = 0.0;
   if(g_m5_low_count > 0)
      sl = g_m5_lows[0].price;
   if(g_bullish_sweep && g_last_bull_sweep.sweep_extreme > 0.0)
     {
      if(sl <= 0.0)
         sl = g_last_bull_sweep.sweep_extreme;
      else
         sl = MathMin(sl, g_last_bull_sweep.sweep_extreme);
     }
   if(g_pending.active && g_pending.sweep_extreme > 0.0)
      sl = (sl <= 0.0 ? g_pending.sweep_extreme : MathMin(sl, g_pending.sweep_extreme));
   if(g_active_demand.valid)
      sl = (sl <= 0.0 ? g_active_demand.bottom : MathMin(sl, g_active_demand.bottom));
   if(g_pending.active && g_pending.ob_bottom > 0.0)
      sl = (sl <= 0.0 ? g_pending.ob_bottom : MathMin(sl, g_pending.ob_bottom));
   if(sl <= 0.0 && ArraySize(g_m5) > 3)
     {
      sl = g_m5[1].low;
      int look = MathMin(8, ArraySize(g_m5) - 1);
      for(int i = 1; i <= look; i++)
         sl = MathMin(sl, g_m5[i].low);
     }
   return sl;
  }

double FindInvalidationHigh()
  {
   double sl = 0.0;
   if(g_m5_high_count > 0)
      sl = g_m5_highs[0].price;
   if(g_bearish_sweep && g_last_bear_sweep.sweep_extreme > 0.0)
     {
      if(sl <= 0.0)
         sl = g_last_bear_sweep.sweep_extreme;
      else
         sl = MathMax(sl, g_last_bear_sweep.sweep_extreme);
     }
   if(g_pending.active && g_pending.sweep_extreme > 0.0)
      sl = (sl <= 0.0 ? g_pending.sweep_extreme : MathMax(sl, g_pending.sweep_extreme));
   if(g_active_supply.valid)
      sl = (sl <= 0.0 ? g_active_supply.top : MathMax(sl, g_active_supply.top));
   if(g_pending.active && g_pending.ob_top > 0.0)
      sl = (sl <= 0.0 ? g_pending.ob_top : MathMax(sl, g_pending.ob_top));
   if(sl <= 0.0 && ArraySize(g_m5) > 3)
     {
      sl = g_m5[1].high;
      int look = MathMin(8, ArraySize(g_m5) - 1);
      for(int i = 1; i <= look; i++)
         sl = MathMax(sl, g_m5[i].high);
     }
   return sl;
  }

double CalculateStopLoss(const int direction)
  {
   double buffer = PointsToPrice(SLBufferPoints);
   if(g_atr_m5 > 0.0)
      buffer = MathMax(buffer, g_atr_m5 * 0.08);
   buffer = MathMax(buffer, g_stops_level * g_point);

   if(direction > 0)
     {
      double raw = FindInvalidationLow();
      if(raw <= 0.0)
         return 0.0;
      return NormalizePrice(raw - buffer);
     }
   double rawh = FindInvalidationHigh();
   if(rawh <= 0.0)
      return 0.0;
   return NormalizePrice(rawh + buffer);
  }

double NextBuyTarget(const double entry)
  {
   double best = 0.0;
   for(int i = 0; i < g_h1_high_count; i++)
     {
      if(g_h1_highs[i].price > entry)
        {
         if(best <= 0.0 || g_h1_highs[i].price < best)
            best = g_h1_highs[i].price;
        }
     }
   for(int i = 0; i < g_liq_high_count; i++)
     {
      if(g_liq_highs[i].price > entry)
        {
         if(best <= 0.0 || (g_liq_highs[i].major_level && g_liq_highs[i].price > best * 0.999))
           {
            if(best <= 0.0 || g_liq_highs[i].price < best || g_liq_highs[i].major_level)
              {
               if(best <= 0.0)
                  best = g_liq_highs[i].price;
               else
                  if(g_liq_highs[i].price > entry && g_liq_highs[i].price < best)
                     best = g_liq_highs[i].price;
              }
           }
        }
     }
   if(g_active_supply.valid && g_active_supply.bottom > entry)
     {
      if(best <= 0.0 || g_active_supply.bottom < best)
         best = g_active_supply.bottom;
     }
   if(best <= 0.0 && g_h1_range_high > entry)
      best = g_h1_range_high;
   return best;
  }

double NextSellTarget(const double entry)
  {
   double best = 0.0;
   for(int i = 0; i < g_h1_low_count; i++)
     {
      if(g_h1_lows[i].price < entry)
        {
         if(best <= 0.0 || g_h1_lows[i].price > best)
            best = g_h1_lows[i].price;
        }
     }
   for(int i = 0; i < g_liq_low_count; i++)
     {
      if(g_liq_low_count > 0 && g_liq_lows[i].price < entry)
        {
         if(best <= 0.0)
            best = g_liq_lows[i].price;
         else
            if(g_liq_lows[i].price > best)
               best = g_liq_lows[i].price;
        }
     }
   if(g_active_demand.valid && g_active_demand.top < entry)
     {
      if(best <= 0.0 || g_active_demand.top > best)
         best = g_active_demand.top;
     }
   if(best <= 0.0 && g_h1_range_low < entry && g_h1_range_low > 0.0)
      best = g_h1_range_low;
   return best;
  }

double CalculateTakeProfit(const int direction, const double entry, const double sl)
  {
   double risk = MathAbs(entry - sl);
   if(risk <= 0.0)
      return 0.0;
   double min_dist = risk * MinimumRiskReward;

   if(direction > 0)
     {
      double candidates[8];
      int n = 0;
      for(int i = 0; i < g_h1_high_count && n < 6; i++)
        {
         if(g_h1_highs[i].price > entry + min_dist * 0.98)
            candidates[n++] = g_h1_highs[i].price;
        }
      for(int i = 0; i < g_liq_high_count && n < 8; i++)
        {
         if(g_liq_highs[i].price > entry + min_dist * 0.98)
            candidates[n++] = g_liq_highs[i].price;
        }
      if(g_active_supply.valid && g_active_supply.bottom > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = g_active_supply.bottom;
      if(g_h1_range_high > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = g_h1_range_high;
      double nearest_buy = NextBuyTarget(entry);
      if(nearest_buy > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = nearest_buy;

      double best = 0.0;
      for(int i = 0; i < n; i++)
        {
         if(candidates[i] <= entry)
            continue;
         if(best <= 0.0 || candidates[i] < best)
            best = candidates[i];
        }
      if(best > 0.0)
         return NormalizePrice(best);
      return 0.0;
     }

   double candidates_s[8];
   int ns = 0;
   for(int i = 0; i < g_h1_low_count && ns < 6; i++)
     {
      if(g_h1_lows[i].price < entry - min_dist * 0.98)
         candidates_s[ns++] = g_h1_lows[i].price;
     }
   for(int i = 0; i < g_liq_low_count && ns < 8; i++)
     {
      if(g_liq_lows[i].price < entry - min_dist * 0.98)
         candidates_s[ns++] = g_liq_lows[i].price;
     }
   if(g_active_demand.valid && g_active_demand.top < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = g_active_demand.top;
   if(g_h1_range_low > 0.0 && g_h1_range_low < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = g_h1_range_low;
   double nearest_sell = NextSellTarget(entry);
   if(nearest_sell > 0.0 && nearest_sell < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = nearest_sell;

   double bests = 0.0;
   for(int i = 0; i < ns; i++)
     {
      if(candidates_s[i] >= entry)
         continue;
      if(bests <= 0.0 || candidates_s[i] > bests)
         bests = candidates_s[i];
     }
   if(bests > 0.0)
      return NormalizePrice(bests);
   return 0.0;
  }

double CalculateRiskReward(const double entry, const double sl, const double tp)
  {
   double risk = MathAbs(entry - sl);
   double reward = MathAbs(tp - entry);
   if(risk <= 0.0)
      return 0.0;
   return reward / risk;
  }

bool StopDistanceAcceptable(const double entry, const double sl)
  {
   double dist = MathAbs(entry - sl);
   if(dist <= 0.0)
      return false;
   int points = (int)MathRound(dist / g_point);
   if(points > MaxStopLossPoints)
      return false;
   int min_points = MathMax(g_stops_level, 5);
   if(points < min_points)
      return false;
   return true;
  }

bool FillM5EntryZone(const int direction, const int confirm_bar, double &ob_top, double &ob_bottom)
  {
   datetime dummy = 0;
   if(direction > 0)
      return FindLastBearishBefore(confirm_bar, 5, ob_top, ob_bottom, dummy);
   return FindLastBullishBefore(confirm_bar, 5, ob_top, ob_bottom, dummy);
  }

bool M5ConfirmationReady(const int direction, PendingSetup &ps)
  {
   if(!UseM5Confirmation)
      return true;

   bool disp = (direction > 0 ? g_m5_bullish_disp : g_m5_bearish_disp);
   bool bos  = (direction > 0 ? g_m5_bullish_bos  : g_m5_bearish_bos);
   bool mss  = (direction > 0 ? g_m5_bullish_mss  : g_m5_bearish_mss);
   bool rej  = false;
   if(ArraySize(g_m5) > 1)
      rej = IsRejectionCandle(g_m5[1], direction);

   if(!disp && !bos && !mss && !rej)
      return false;

   int confirm_bar = 1;
   if(mss && g_m5_mss_bar > 0)
      confirm_bar = g_m5_mss_bar;
   else
      if(bos && g_m5_bos_bar > 0)
         confirm_bar = g_m5_bos_bar;
      else
         if(disp && g_m5_disp_bar > 0)
            confirm_bar = g_m5_disp_bar;

   ps.had_displacement = disp;
   ps.had_bos = bos;
   ps.had_mss = mss;
   ps.had_rejection = rej;
   ps.bos_time = (bos ? g_m5_bos_time : 0);
   ps.mss_time = (mss ? g_m5_mss_time : 0);
   ps.bos_level = g_m5_bos_level;

   double top = 0.0;
   double bot = 0.0;
   if(!FillM5EntryZone(direction, confirm_bar, top, bot))
     {
      if(direction > 0 && g_m5_low_count > 0)
        {
         bot = g_m5_lows[0].price;
         top = bot + MathMax(g_atr_m5 * 0.4, PointsToPrice(50));
        }
      else
         if(direction < 0 && g_m5_high_count > 0)
           {
            top = g_m5_highs[0].price;
            bot = top - MathMax(g_atr_m5 * 0.4, PointsToPrice(50));
           }
         else
            return false;
     }
   ps.ob_top = top;
   ps.ob_bottom = bot;
   return true;
  }

bool PendingInvalidated()
  {
   if(!g_pending.active)
      return false;
   if(ArraySize(g_m5) < 2)
      return false;
   if(g_pending.direction > 0)
     {
      if(g_pending.sweep_extreme > 0.0 && g_m5[1].close < g_pending.sweep_extreme)
         return true;
      if(g_h1_bias == BIAS_BEARISH)
         return true;
     }
   else
     {
      if(g_pending.sweep_extreme > 0.0 && g_m5[1].close > g_pending.sweep_extreme)
         return true;
      if(g_h1_bias == BIAS_BULLISH)
         return true;
     }
   int age = iBarShift(g_symbol, InpEntryTF, g_pending.created_time, true);
   if(age < 0)
      age = SweepMaxAgeM5Bars + 1;
   if(age > SweepMaxAgeM5Bars)
      return true;
   return false;
  }

bool BuildTradePlan(const int direction, TradePlan &plan)
  {
   ZeroMemory(plan);
   plan.direction = direction;
   plan.entry = (direction > 0 ? CurrentAsk() : CurrentBid());
   plan.sl = CalculateStopLoss(direction);
   if(plan.sl <= 0.0)
     {
      plan.reason = "No trade: invalid structural stop";
      return false;
     }
   if(direction > 0 && plan.sl >= plan.entry)
     {
      plan.reason = "No trade: invalid stops";
      return false;
     }
   if(direction < 0 && plan.sl <= plan.entry)
     {
      plan.reason = "No trade: invalid stops";
      return false;
     }
   if(!StopDistanceAcceptable(plan.entry, plan.sl))
     {
      plan.reason = "No trade: stop exceeds MaxStopLossPoints";
      return false;
     }

   plan.tp = CalculateTakeProfit(direction, plan.entry, plan.sl);
   if(plan.tp <= 0.0)
     {
      plan.reason = StringFormat("No trade: RR below %.1f", MinimumRiskReward);
      return false;
     }
   plan.rr = CalculateRiskReward(plan.entry, plan.sl, plan.tp);
   g_last_rr = plan.rr;
   if(plan.rr + 1.0e-8 < MinimumRiskReward)
     {
      plan.reason = StringFormat("No trade: RR below %.1f", MinimumRiskReward);
      return false;
     }
   if(IsChasingMove(direction, plan.entry, plan.tp))
     {
      plan.reason = "No trade: chasing price after large move";
      return false;
     }
   plan.lots = CalculateLotSizeFromBalance(AccountInfoDouble(ACCOUNT_BALANCE));
   if(plan.lots < g_volume_min)
     {
      plan.reason = "No trade: invalid volume";
      return false;
     }
   plan.zone_top = g_pending.ob_top;
   plan.zone_bottom = g_pending.ob_bottom;
   plan.sweep_extreme = g_pending.sweep_extreme;
   plan.sweep_time = g_pending.sweep_time;
   plan.confirmation_time = g_m5[1].time;
   plan.setup_id = g_pending.setup_id;
   plan.valid = true;
   plan.reason = (direction > 0 ? "BUY setup confirmed" : "SELL setup confirmed");
   return true;
  }

bool ConfirmBuySetup(TradePlan &plan)
  {
   ZeroMemory(plan);
   if(g_h1_bias != BIAS_BULLISH)
     {
      LogReason("No trade: H1 bias unclear");
      return false;
     }
   if(RequireDiscountPremium && !PriceInDiscount() && !g_bullish_sweep && !(g_active_demand.valid && PriceNearZone(g_active_demand, 0.35)))
     {
      LogReason("No trade: price not in discount / demand area");
      return false;
     }
   if(!PriceAtBullishArea())
     {
      LogReason("No trade: price not at H1 demand/support/liquidity");
      return false;
     }
   if(UseLiquiditySweep && !g_bullish_sweep && !g_pending.active)
     {
      LogReason("No trade: liquidity sweep not detected");
      return false;
     }
   if(UseM5Confirmation)
     {
      if(!g_pending.active || g_pending.direction != 1)
        {
         PendingSetup ps;
         ZeroMemory(ps);
         if(!M5ConfirmationReady(1, ps))
           {
            g_ea_status = EA_STATUS_WAITING_M5;
            LogReason("No trade: M5 confirmation missing");
            return false;
           }
         g_pending = ps;
         g_pending.active = true;
         g_pending.direction = 1;
         g_pending.waiting_retest = RequireM5Retest;
         g_pending.created_time = TimeCurrent();
         if(g_bullish_sweep)
           {
            g_pending.sweep_time = g_last_bull_sweep.sweep_time;
            g_pending.sweep_extreme = g_last_bull_sweep.sweep_extreme;
            g_pending.liq_price = g_last_bull_sweep.price;
            g_pending.liq_time = g_last_bull_sweep.time;
           }
         g_pending.setup_id = BuildSetupId(1, g_pending.liq_time, g_pending.liq_price);
         if(SetupAlreadyUsed(g_pending.setup_id))
           {
            LogReason("No trade: setup already used");
            ResetPending();
            return false;
           }
        }

      if(RequireM5Retest)
        {
         if(!M5RetestConfirmed(1, g_pending.ob_top, g_pending.ob_bottom))
           {
            g_pending.waiting_retest = true;
            g_ea_status = EA_STATUS_WAITING_RETEST;
            LogReason("No trade: waiting M5 retest into demand/OB");
            return false;
           }
        }
     }

   if(!BuildTradePlan(1, plan))
     {
      LogReason(plan.reason);
      if(StringFind(plan.reason, "RR below") >= 0)
         MarkSetupUsed(g_pending.setup_id);
      return false;
     }
   return true;
  }

bool ConfirmSellSetup(TradePlan &plan)
  {
   ZeroMemory(plan);
   if(g_h1_bias != BIAS_BEARISH)
     {
      LogReason("No trade: H1 bias unclear");
      return false;
     }
   if(RequireDiscountPremium && !PriceInPremium() && !g_bearish_sweep && !(g_active_supply.valid && PriceNearZone(g_active_supply, 0.35)))
     {
      LogReason("No trade: price not in premium / supply area");
      return false;
     }
   if(!PriceAtBearishArea())
     {
      LogReason("No trade: price not at H1 supply/resistance/liquidity");
      return false;
     }
   if(UseLiquiditySweep && !g_bearish_sweep && !g_pending.active)
     {
      LogReason("No trade: liquidity sweep not detected");
      return false;
     }
   if(UseM5Confirmation)
     {
      if(!g_pending.active || g_pending.direction != -1)
        {
         PendingSetup ps;
         ZeroMemory(ps);
         if(!M5ConfirmationReady(-1, ps))
           {
            g_ea_status = EA_STATUS_WAITING_M5;
            LogReason("No trade: M5 confirmation missing");
            return false;
           }
         g_pending = ps;
         g_pending.active = true;
         g_pending.direction = -1;
         g_pending.waiting_retest = RequireM5Retest;
         g_pending.created_time = TimeCurrent();
         if(g_bearish_sweep)
           {
            g_pending.sweep_time = g_last_bear_sweep.sweep_time;
            g_pending.sweep_extreme = g_last_bear_sweep.sweep_extreme;
            g_pending.liq_price = g_last_bear_sweep.price;
            g_pending.liq_time = g_last_bear_sweep.time;
           }
         g_pending.setup_id = BuildSetupId(-1, g_pending.liq_time, g_pending.liq_price);
         if(SetupAlreadyUsed(g_pending.setup_id))
           {
            LogReason("No trade: setup already used");
            ResetPending();
            return false;
           }
        }

      if(RequireM5Retest)
        {
         if(!M5RetestConfirmed(-1, g_pending.ob_top, g_pending.ob_bottom))
           {
            g_pending.waiting_retest = true;
            g_ea_status = EA_STATUS_WAITING_RETEST;
            LogReason("No trade: waiting M5 retest into supply/OB");
            return false;
           }
        }
     }

   if(!BuildTradePlan(-1, plan))
     {
      LogReason(plan.reason);
      if(StringFind(plan.reason, "RR below") >= 0)
         MarkSetupUsed(g_pending.setup_id);
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Trade engine
//+------------------------------------------------------------------+
CTrade g_trade;

ENUM_ORDER_TYPE_FILLING SelectFillingMode()
  {
   long mode = SymbolInfoInteger(g_symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

void InitTradeEngine()
  {
   g_trade.SetExpertMagicNumber((ulong)MagicNumber);
   g_trade.SetDeviationInPoints(SlippagePoints);
   g_trade.SetAsyncMode(false);
   g_trade.SetTypeFilling(SelectFillingMode());
   g_trade.LogLevel(LOG_LEVEL_ERRORS);
  }

int CountEAPositions()
  {
   int count = 0;
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      count++;
     }
   return count;
  }

void ResetDailyStateIfNeeded()
  {
   datetime now = TimeCurrent();
   datetime day = BeginningOfDay(now);
   if(g_daily.day_start != day)
     {
      g_daily.day_start = day;
      g_daily.day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
      g_daily.trades_today = 0;
      g_daily.closed_pnl_today = 0.0;
      if(g_daily.peak_equity <= 0.0)
         g_daily.peak_equity = AccountInfoDouble(ACCOUNT_EQUITY);
     }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_daily.peak_equity)
      g_daily.peak_equity = eq;
  }

double DealPnL(const ulong ticket)
  {
   double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
   profit += HistoryDealGetDouble(ticket, DEAL_SWAP);
   profit += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
   return profit;
  }

void RefreshDailyStats()
  {
   ResetDailyStateIfNeeded();
   datetime from = g_daily.day_start;
   datetime to = TimeCurrent();
   if(!HistorySelect(from, to))
      return;

   double pnl = 0.0;
   int trades = 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != g_symbol)
         continue;
      long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry == DEAL_ENTRY_IN)
         trades++;
      if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT || entry == DEAL_ENTRY_OUT_BY)
         pnl += DealPnL(ticket);
     }
   g_daily.closed_pnl_today = pnl;
   g_daily.trades_today = trades;
  }

double FloatingPnL()
  {
   double pnl = 0.0;
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      pnl += PositionGetDouble(POSITION_PROFIT);
      pnl += PositionGetDouble(POSITION_SWAP);
     }
   return pnl;
  }

bool CheckRiskLimits()
  {
   RefreshDailyStats();

   if(UseMaxDrawdownProtection && g_daily.peak_equity > 0.0)
     {
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      double dd = 100.0 * (g_daily.peak_equity - eq) / g_daily.peak_equity;
      if(dd >= MaximumDrawdownPercent)
        {
         g_ea_status = EA_STATUS_DRAWDOWN_LIMIT;
         LogReason("No trade: maximum drawdown reached");
         return false;
        }
     }

   if(UseDailyLossProtection)
     {
      double day_pnl = g_daily.closed_pnl_today + FloatingPnL();
      double start_bal = g_daily.day_start_balance;
      if(start_bal <= 0.0)
         start_bal = AccountInfoDouble(ACCOUNT_BALANCE);
      double loss_pct = 0.0;
      if(start_bal > 0.0 && day_pnl < 0.0)
         loss_pct = 100.0 * (-day_pnl) / start_bal;
      if(loss_pct >= MaximumDailyLossPercent)
        {
         g_ea_status = EA_STATUS_DAILY_LIMIT;
         LogReason("No trade: daily loss limit reached");
         return false;
        }
     }

   if(MaximumDailyTrades > 0 && g_daily.trades_today >= MaximumDailyTrades)
     {
      g_ea_status = EA_STATUS_DAILY_LIMIT;
      LogReason("No trade: maximum daily trades reached");
      return false;
     }

   if(CountEAPositions() >= MaxOpenPositions)
     {
      g_ea_status = EA_STATUS_TRADE_OPEN;
      return false;
     }
   return true;
  }

bool NewsFilterBlocks()
  {
   if(!UseNewsFilter)
      return false;
   if(!g_news_warned)
     {
      Print("News filter enabled but no news calendar API is available. Filter will not invent events and will not block trades.");
      g_news_warned = true;
     }
   return false;
  }

bool StopsValidForBroker(const int type, const double price, const double sl, const double tp)
  {
   int level = MathMax(g_stops_level, g_freeze_level);
   double min_dist = level * g_point;
   if(min_dist <= 0.0)
      min_dist = g_point;
   if(type == ORDER_TYPE_BUY)
     {
      if(sl >= price - min_dist)
         return false;
      if(tp <= price + min_dist)
         return false;
     }
   else
     {
      if(sl <= price + min_dist)
         return false;
      if(tp >= price - min_dist)
         return false;
     }
   return true;
  }

bool PreTradeChecks(const int type, const TradePlan &plan)
  {
   if(!IsXAUUSDmName(g_symbol))
     {
      LogReason("No trade: symbol is not XAUUSDm");
      return false;
     }
   if(!TradingAllowed())
     {
      LogReason("No trade: trading disabled");
      return false;
     }
   if(!MarketIsOpen())
     {
      g_ea_status = EA_STATUS_MARKET_CLOSED;
      LogReason("No trade: market closed");
      return false;
     }
   if(!IsWithinTradingSession(TimeCurrent()))
     {
      g_ea_status = EA_STATUS_SESSION_CLOSED;
      LogReason("No trade: outside trading session");
      return false;
     }
   if(!CheckSpread())
     {
      LogReason("No trade: spread too high");
      return false;
     }
   if(NewsFilterBlocks())
      return false;
   if(!CheckRiskLimits())
      return false;
   if(CountEAPositions() >= MaxOpenPositions)
     {
      LogReason("No trade: max open positions reached");
      return false;
     }
   if(!plan.valid)
      return false;
   if(plan.rr + 1.0e-8 < MinimumRiskReward)
     {
      LogReason(StringFormat("No trade: RR below %.1f", MinimumRiskReward));
      return false;
     }
   if(plan.lots < g_volume_min || plan.lots > g_volume_max)
     {
      LogReason("No trade: invalid volume");
      return false;
     }
   double price = (type == ORDER_TYPE_BUY ? CurrentAsk() : CurrentBid());
   if(!StopsValidForBroker(type, price, plan.sl, plan.tp))
     {
      LogReason("No trade: invalid stops");
      return false;
     }
   if(g_last_fail_time > 0 && (TimeCurrent() - g_last_fail_time) < FailedOrderWaitSeconds)
     {
      LogReason("No trade: waiting after previous order error");
      return false;
     }
   return true;
  }

bool SendMarketOrder(const int type, const TradePlan &plan)
  {
   double lots = NormalizeVolume(plan.lots);
   double sl = NormalizePrice(plan.sl);
   double tp = NormalizePrice(plan.tp);
   double price = (type == ORDER_TYPE_BUY ? CurrentAsk() : CurrentBid());
   string comment = TradeComment;

   ENUM_ORDER_TYPE_FILLING fills[3];
   fills[0] = SelectFillingMode();
   fills[1] = ORDER_FILLING_IOC;
   fills[2] = ORDER_FILLING_FOK;

   for(int i = 0; i < 3; i++)
     {
      if(i > 0 && fills[i] == fills[0])
         continue;
      g_trade.SetTypeFilling(fills[i]);
      bool ok = false;
      if(type == ORDER_TYPE_BUY)
         ok = g_trade.Buy(lots, g_symbol, price, sl, tp, comment);
      else
         ok = g_trade.Sell(lots, g_symbol, price, sl, tp, comment);
      if(ok)
         return true;

      uint code = g_trade.ResultRetcode();
      PrintFormat("Order failed retcode=%u %s filling=%d", code, g_trade.ResultRetcodeDescription(), (int)fills[i]);
      if(code != TRADE_RETCODE_INVALID_FILL)
        {
         g_last_fail_time = TimeCurrent();
         return false;
        }
     }
   g_last_fail_time = TimeCurrent();
   return false;
  }

bool OpenBuy(const TradePlan &plan)
  {
   if(!PreTradeChecks(ORDER_TYPE_BUY, plan))
      return false;
   PrintFormat("Lot size calculated: %.2f", plan.lots);
   if(!SendMarketOrder(ORDER_TYPE_BUY, plan))
     {
      LogReason("BUY order failed");
      return false;
     }
   Print("BUY order opened");
   MarkSetupUsed(plan.setup_id);
   ResetPending();
   g_last_plan = plan;
   g_ea_status = EA_STATUS_TRADE_OPEN;
   return true;
  }

bool OpenSell(const TradePlan &plan)
  {
   if(!PreTradeChecks(ORDER_TYPE_SELL, plan))
      return false;
   PrintFormat("Lot size calculated: %.2f", plan.lots);
   if(!SendMarketOrder(ORDER_TYPE_SELL, plan))
     {
      LogReason("SELL order failed");
      return false;
     }
   Print("SELL order opened");
   MarkSetupUsed(plan.setup_id);
   ResetPending();
   g_last_plan = plan;
   g_ea_status = EA_STATUS_TRADE_OPEN;
   return true;
  }

bool ManageTrade()
  {
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;

      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      long type = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);

      if(sl > 0.0 && tp > 0.0)
         continue;

      if(g_last_plan.valid && g_last_plan.sl > 0.0 && g_last_plan.tp > 0.0)
        {
         if(!g_trade.PositionModify(ticket, g_last_plan.sl, g_last_plan.tp))
            Print("Failed to restore SL/TP: ", g_trade.ResultRetcodeDescription());
         continue;
        }

      int dir = (type == POSITION_TYPE_BUY ? 1 : -1);
      double new_sl = CalculateStopLoss(dir);
      double new_tp = CalculateTakeProfit(dir, open, new_sl);
      if(new_sl > 0.0 && new_tp > 0.0)
         g_trade.PositionModify(ticket, new_sl, new_tp);
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Visualization
//+------------------------------------------------------------------+
#define DASH_PREFIX SMC_PREFIX "DASH_"
#define OBJ_PREFIX  SMC_PREFIX "OBJ_"

void DeleteByPrefix(const string prefix)
  {
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(0, i, -1, -1);
      if(StringFind(name, prefix) == 0)
         ObjectDelete(0, name);
     }
  }

void CleanupVisuals()
  {
   DeleteByPrefix(SMC_PREFIX);
  }

void CreateLabel(const string name, const int x, const int y, const string text, const color clr, const int size)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
  }

void CreatePanelBg(const string name, const int x, const int y, const int w, const int h)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, C'18,24,32');
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_COLOR, C'70,90,110');
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
  }

string M5ConfirmText()
  {
   if(g_ea_status == EA_STATUS_WAITING_M5)
      return "WAITING";
   if(g_ea_status == EA_STATUS_WAITING_RETEST)
      return "RETEST";
   if(g_m5_bullish_mss)
      return "BULL MSS";
   if(g_m5_bearish_mss)
      return "BEAR MSS";
   if(g_m5_bullish_bos)
      return "BULL BOS";
   if(g_m5_bearish_bos)
      return "BEAR BOS";
   if(g_m5_bias == BIAS_BULLISH)
      return "BULLISH";
   if(g_m5_bias == BIAS_BEARISH)
      return "BEARISH";
   return "NONE";
  }

void UpdateDashboard()
  {
   if(!ShowDashboard)
      return;

   int x = 12;
   int y = 22;
   CreatePanelBg(DASH_PREFIX "BG", x, y, 278, 268);

   color bias_clr = clrSilver;
   if(g_h1_bias == BIAS_BULLISH)
      bias_clr = clrLime;
   if(g_h1_bias == BIAS_BEARISH)
      bias_clr = clrOrangeRed;

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double lots = CalculateLotSizeFromBalance(bal);
   int positions = CountEAPositions();
   int spread = CurrentSpreadPoints();

   CreateLabel(DASH_PREFIX "T0", x + 12, y + 8,  g_symbol, clrGold, 11);
   CreateLabel(DASH_PREFIX "T1", x + 12, y + 28, "H1 Bias: " + BiasToText(g_h1_bias), bias_clr, 10);
   CreateLabel(DASH_PREFIX "T2", x + 12, y + 46, "M5 Confirmation: " + M5ConfirmText(), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T3", x + 12, y + 64, "Balance: $" + DoubleToString(bal, 2), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T4", x + 12, y + 82, "Lot Size: " + DoubleToString(lots, 2), clrAqua, 10);
   CreateLabel(DASH_PREFIX "T5", x + 12, y + 100, "Open Trades: " + IntegerToString(positions), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T6", x + 12, y + 118, "Spread: " + IntegerToString(spread), (spread > MaxSpreadPoints ? clrOrangeRed : clrWhite), 10);
   CreateLabel(DASH_PREFIX "T7", x + 12, y + 136, "Daily Trades: " + IntegerToString(g_daily.trades_today), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T8", x + 12, y + 154, "Daily P/L: " + DoubleToString(g_daily.closed_pnl_today + FloatingPnL(), 2), (g_daily.closed_pnl_today + FloatingPnL() >= 0 ? clrLime : clrOrangeRed), 10);
   CreateLabel(DASH_PREFIX "T9", x + 12, y + 172, "Current R:R: " + DoubleToString(g_last_rr, 2), clrWhite, 10);
   CreateLabel(DASH_PREFIX "TA", x + 12, y + 190, "Status: " + StatusToText(g_ea_status), clrKhaki, 10);
   CreateLabel(DASH_PREFIX "TB", x + 12, y + 214, (g_h1_bias == BIAS_BULLISH ? "H1 BULLISH BIAS" : (g_h1_bias == BIAS_BEARISH ? "H1 BEARISH BIAS" : "H1 NO CLEAR BIAS")), bias_clr, 10);
   string extra = g_status_text;
   if(StringLen(extra) > 42)
      extra = StringSubstr(extra, 0, 42);
   CreateLabel(DASH_PREFIX "TC", x + 12, y + 236, extra, clrSilver, 8);
  }

void DrawHLineNamed(const string name, const double price, const color clr, const int style, const int width, const string text)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

void DrawRect(const string name, datetime t1, const double p1, datetime t2, const double p2, const color clr)
  {
   if(t2 <= t1)
      t2 = t1 + PeriodSeconds(InpAnalysisTF) * 8;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p1);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 1, p2);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   color fill = clr;
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, fill);
  }

void DrawTextAt(const string name, const datetime t, const double price, const string text, const color clr)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetInteger(0, name, OBJPROP_TIME, t);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void DrawStructure()
  {
   DeleteByPrefix(OBJ_PREFIX);

   datetime t_now = TimeCurrent();

   if(ShowStructure)
     {
      int hs = MathMin(8, g_h1_high_count);
      for(int i = 0; i < hs; i++)
        {
         string n = OBJ_PREFIX + "H1H" + IntegerToString(i);
         DrawHLineNamed(n, g_h1_highs[i].price, clrTomato, STYLE_DOT, 1, "H1 SH");
         DrawTextAt(n + "L", g_h1_highs[i].time, g_h1_highs[i].price, "H1 SH", clrTomato);
        }
      int ls = MathMin(8, g_h1_low_count);
      for(int i = 0; i < ls; i++)
        {
         string n = OBJ_PREFIX + "H1L" + IntegerToString(i);
         DrawHLineNamed(n, g_h1_lows[i].price, clrDodgerBlue, STYLE_DOT, 1, "H1 SL");
         DrawTextAt(n + "L", g_h1_lows[i].time, g_h1_lows[i].price, "H1 SL", clrDodgerBlue);
        }
     }

   if(ShowZones)
     {
      if(g_active_demand.valid)
        {
         DrawRect(OBJ_PREFIX + "DEMAND", g_active_demand.time, g_active_demand.top, t_now, g_active_demand.bottom, C'0,80,40');
         DrawTextAt(OBJ_PREFIX + "DEMANDL", g_active_demand.time, g_active_demand.top, "H1 DEMAND", clrLime);
        }
      if(g_active_supply.valid)
        {
         DrawRect(OBJ_PREFIX + "SUPPLY", g_active_supply.time, g_active_supply.top, t_now, g_active_supply.bottom, C'90,20,20');
         DrawTextAt(OBJ_PREFIX + "SUPPLYL", g_active_supply.time, g_active_supply.top, "H1 SUPPLY", clrOrangeRed);
        }
     }

   if(ShowLiquidity)
     {
      int lh = MathMin(6, g_liq_high_count);
      for(int i = 0; i < lh; i++)
        {
         string n = OBJ_PREFIX + "LIQH" + IntegerToString(i);
         DrawHLineNamed(n, g_liq_highs[i].price, clrGold, STYLE_DASH, 1, "BUY-SIDE LIQ");
        }
      int ll = MathMin(6, g_liq_low_count);
      for(int i = 0; i < ll; i++)
        {
         string n = OBJ_PREFIX + "LIQL" + IntegerToString(i);
         DrawHLineNamed(n, g_liq_lows[i].price, clrGold, STYLE_DASH, 1, "SELL-SIDE LIQ");
        }
      if(g_bullish_sweep)
         DrawTextAt(OBJ_PREFIX + "SWEEP", g_last_bull_sweep.sweep_time, g_last_bull_sweep.sweep_extreme, "LIQUIDITY SWEEP", clrAqua);
      if(g_bearish_sweep)
         DrawTextAt(OBJ_PREFIX + "SWEEP2", g_last_bear_sweep.sweep_time, g_last_bear_sweep.sweep_extreme, "LIQUIDITY SWEEP", clrAqua);
     }

   if(g_m5_bullish_bos)
      DrawTextAt(OBJ_PREFIX + "M5BOS", g_m5_bos_time, g_m5_bos_level, "M5 BOS", clrLime);
   if(g_m5_bearish_bos)
      DrawTextAt(OBJ_PREFIX + "M5BOSB", g_m5_bos_time, g_m5_bos_level, "M5 BOS", clrOrangeRed);
   if(g_m5_bullish_mss)
      DrawTextAt(OBJ_PREFIX + "M5MSS", g_m5_mss_time, g_m5_bos_level, "M5 MSS", clrLime);
   if(g_m5_bearish_mss)
      DrawTextAt(OBJ_PREFIX + "M5MSSB", g_m5_mss_time, g_m5_bos_level, "M5 MSS", clrOrangeRed);

   if(ShowEntryLevels && g_last_plan.valid && CountEAPositions() > 0)
     {
      DrawHLineNamed(OBJ_PREFIX + "ENTRY", g_last_plan.entry, clrWhite, STYLE_SOLID, 1, (g_last_plan.direction > 0 ? "BUY ENTRY" : "SELL ENTRY"));
      DrawHLineNamed(OBJ_PREFIX + "SL", g_last_plan.sl, clrRed, STYLE_SOLID, 2, "SL");
      DrawHLineNamed(OBJ_PREFIX + "TP", g_last_plan.tp, clrLime, STYLE_SOLID, 2, "TP");
      DrawTextAt(OBJ_PREFIX + "RR", t_now, g_last_plan.tp, "RR " + DoubleToString(g_last_plan.rr, 2), clrWhite);
     }
  }

//+------------------------------------------------------------------+
//| Expert events
//+------------------------------------------------------------------+
void ProcessNewSetup()
  {
   if(PendingInvalidated())
     {
      LogReason("Pending setup invalidated");
      ResetPending();
     }

   if(!IsWithinTradingSession(TimeCurrent()))
     {
      g_ea_status = EA_STATUS_SESSION_CLOSED;
      LogReason("No trade: outside trading session");
      return;
     }

   if(!CheckRiskLimits())
      return;

   if(CountEAPositions() >= MaxOpenPositions)
     {
      g_ea_status = EA_STATUS_TRADE_OPEN;
      return;
     }

   if(g_h1_bias == BIAS_NONE)
     {
      g_ea_status = EA_STATUS_WAITING_SETUP;
      LogReason("No trade: H1 bias unclear");
      ResetPending();
      return;
     }

   TradePlan plan;
   ZeroMemory(plan);

   if(g_h1_bias == BIAS_BULLISH)
     {
      if(ConfirmBuySetup(plan))
        {
         Print(plan.reason);
         OpenBuy(plan);
        }
      return;
     }

   if(g_h1_bias == BIAS_BEARISH)
     {
      if(ConfirmSellSetup(plan))
        {
         Print(plan.reason);
         OpenSell(plan);
        }
     }
  }

int OnInit()
  {
   g_ea_status = EA_STATUS_INIT;
   ResetPending();
   ZeroMemory(g_daily);
   ZeroMemory(g_last_plan);
   g_used_setups_count = 0;
   ArrayResize(g_used_setups, 0);

   g_symbol = DetectXAUUSDm();
   if(g_symbol == "" || !IsXAUUSDmName(g_symbol))
     {
      g_ea_status = EA_STATUS_SYMBOL_ERROR;
      string err = "ERROR: XAUUSDm is unavailable. EA will not place trades.";
      Print(err);
      Alert(err);
      Comment(err);
      return INIT_FAILED;
     }

   if(!LoadSymbolContract(g_symbol))
     {
      g_ea_status = EA_STATUS_SYMBOL_ERROR;
      Print("ERROR: failed to read XAUUSDm contract specification.");
      Alert("ERROR: failed to read XAUUSDm contract specification.");
      return INIT_FAILED;
     }

   if(!SymbolIsTradable(g_symbol))
      Print("Warning: ", g_symbol, " trade mode is currently restricted.");

   InitTradeEngine();

   g_daily.day_start = BeginningOfDay(TimeCurrent());
   g_daily.day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_daily.peak_equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(UseNewsFilter)
      Print("News filter requested, but no news API is available. The filter will stay inactive and will not invent events.");

   if(!RefreshRates(true))
      Print("Warning: initial rate copy incomplete; waiting for market data.");

   PrintFormat("XAUUSDm H1/M5 EA initialized on %s  digits=%d point=%.5f minlot=%.2f",
               g_symbol, g_digits, g_point, g_volume_min);
   PrintFormat("Starting balance: %.2f  lot size: %.2f",
               AccountInfoDouble(ACCOUNT_BALANCE),
               CalculateLotSizeFromBalance(AccountInfoDouble(ACCOUNT_BALANCE)));

   g_ea_status = EA_STATUS_WAITING_SETUP;
   g_status_text = "WAITING FOR SETUP";
   UpdateDashboard();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   Print("EA removed, reason=", IntegerToString(reason));
   CleanupVisuals();
   Comment("");
  }

void OnTick()
  {
   if(g_symbol == "" || g_ea_status == EA_STATUS_SYMBOL_ERROR)
      return;

   ManageTrade();
   RefreshDailyStats();

   if(CountEAPositions() > 0)
      g_ea_status = EA_STATUS_TRADE_OPEN;

   UpdateDashboard();

   if(!IsNewM5Bar())
      return;

   if(!RefreshRates(true))
     {
      LogReason("No trade: waiting for closed candle data");
      return;
     }

   AnalyzeStructure();
   AnalyzeLiquidityAndZones();
   DrawStructure();
   ProcessNewSetup();
   UpdateDashboard();
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD || request.magic == (ulong)MagicNumber || result.order > 0)
      RefreshDailyStats();
  }
