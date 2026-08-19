#ifndef XAUUSDM_SMC_UTILS_MQH
#define XAUUSDM_SMC_UTILS_MQH

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

#endif
