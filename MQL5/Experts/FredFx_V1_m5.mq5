//+------------------------------------------------------------------+
//|                                              FredFx_V1_m5.mq5    |
//| Expert Advisor name : FredFx V1 m5                               |
//| Symbol              : XAUUSDm                                    |
//| Chart               : M5 (also reads M15 and H1)                 |
//| Strategy            : SMC — OB, BOS, MSS, CHoCH, FVG, sweep      |
//| Risk                : SL:TP = 1:2, move SL to breakeven at +1R   |
//| Lots                : 0.01 per $100 balance, min 0.01            |
//| Positions           : 1 at a time, many trades per day           |
//+------------------------------------------------------------------+
#property copyright   "Fred Fx"
#property version     "1.00"
#property description "FredFx V1 m5 — SMC XAUUSDm. M5 entry, M15/H1 bias, liquidity sweep, 1:2 RR, SL to breakeven."

#include <Trade/Trade.mqh>

#define ROBOT_NAME    "FredFx V1 m5"
#define DIR_NONE      0
#define DIR_BULL      1
#define DIR_BEAR     -1
#define KIND_BOS      1
#define KIND_CHOCH    2
#define KIND_MSS      3
#define ZONE_FVG      1
#define ZONE_OB       2
#define SWING_HIGH    1
#define SWING_LOW    -1

input string InpSymbol          = "XAUUSDm";
input double InpRiskReward      = 2.0;
input double InpLotPer100       = 0.01;
input double InpMinLot          = 0.01;
input double InpMaxLot          = 10.0;
input double InpSlBuffer        = 0.50;
input int    InpMagic           = 26080105;
input int    InpLookback        = 300;
input int    InpSwingLeft       = 2;
input int    InpSwingRight      = 2;
input int    InpMinConfluence   = 4;
input int    InpRecentBars      = 40;
input int    InpCooldownBars    = 8;
input bool   InpRequireSweep    = true;
input double InpBreakevenAtR    = 1.0;
input int    InpSlippagePoints  = 40;

CTrade         g_trade;
string         g_symbol;
datetime       g_last_m5 = 0;
datetime       g_last_close_time = 0;
bool           g_had_position = false;
double         g_initial_sl = 0.0;
ulong          g_ticket = 0;

struct Swing
  {
   int               index;
   double            price;
   int               kind;
  };

struct Event
  {
   int               index;
   int               kind;
   int               direction;
   double            broken;
  };

struct Zone
  {
   int               start_index;
   int               end_index;
   double            low;
   double            high;
   int               direction;
   int               kind;
   bool              mitigated;
  };

struct Sweep
  {
   int               index;
   int               direction;
   double            swept_price;
   double            wick;
  };

struct Signal
  {
   bool              valid;
   int               direction;
   double            sl;
   double            tp;
   int               confluence;
   int               zone_kind;
  };

//+------------------------------------------------------------------+
int OnInit()
  {
   g_symbol = (InpSymbol == "" ? _Symbol : InpSymbol);
   if(!SymbolSelect(g_symbol, true))
     {
      Print(ROBOT_NAME, " cannot select symbol ", g_symbol);
      return(INIT_FAILED);
     }

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFilling(DetectFilling());
   g_trade.SetAsyncMode(false);

   Print(ROBOT_NAME, " started on ", g_symbol, "  M5 entry / M15+H1 bias  SL:TP 1:", DoubleToString(InpRiskReward, 0));
   Comment(ROBOT_NAME, "\nWaiting for SMC setup on ", g_symbol);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   ManageBreakeven();

   datetime bar_time = iTime(g_symbol, PERIOD_M5, 0);
   if(bar_time == 0 || bar_time == g_last_m5)
      return;
   g_last_m5 = bar_time;

   int ours = CountOurPositions();
   if(g_had_position && ours == 0)
      g_last_close_time = TimeCurrent();
   g_had_position = (ours > 0);
   if(ours > 0)
     {
      Comment(ROBOT_NAME, "\nIn trade — SL to breakeven at +1R");
      return;
     }

   if(g_last_close_time > 0)
     {
      int elapsed = (int)((TimeCurrent() - g_last_close_time) / PeriodSeconds(PERIOD_M5));
      if(elapsed < InpCooldownBars)
        {
         Comment(ROBOT_NAME, "\nCooldown ", IntegerToString(elapsed), "/", IntegerToString(InpCooldownBars));
         return;
        }
     }

   Signal sig;
   if(!BuildSignal(sig) || !sig.valid)
     {
      Comment(ROBOT_NAME, "\nScanning ", g_symbol, " M5");
      return;
     }

   double lots = LotSize();
   if(lots <= 0.0)
      return;

   double price = (sig.direction == DIR_BULL
                   ? SymbolInfoDouble(g_symbol, SYMBOL_ASK)
                   : SymbolInfoDouble(g_symbol, SYMBOL_BID));
   sig.sl = NormalizePrice(sig.sl);
   sig.tp = NormalizePrice(sig.tp);
   if(!StopsOk(price, sig.sl, sig.tp))
     {
      Print(ROBOT_NAME, " SL/TP too close to price, skip");
      return;
     }

   bool ok = false;
   if(sig.direction == DIR_BULL)
      ok = g_trade.Buy(lots, g_symbol, price, sig.sl, sig.tp, ROBOT_NAME);
   else
      ok = g_trade.Sell(lots, g_symbol, price, sig.sl, sig.tp, ROBOT_NAME);

   if(!ok)
     {
      Print(ROBOT_NAME, " order failed retcode=", g_trade.ResultRetcode(),
            " ", g_trade.ResultRetcodeDescription());
      return;
     }

   g_ticket = FindOurTicket();
   g_initial_sl = sig.sl;
   if(g_ticket > 0)
      GlobalVariableSet(InitSlKey(g_ticket), g_initial_sl);

   Print(ROBOT_NAME, " opened ", (sig.direction == DIR_BULL ? "BUY" : "SELL"),
         " lots=", DoubleToString(lots, 2),
         " SL=", DoubleToString(sig.sl, (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS)),
         " TP=", DoubleToString(sig.tp, (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS)),
         " RR=1:", DoubleToString(InpRiskReward, 0),
         " confluence=", IntegerToString(sig.confluence));
   Comment(ROBOT_NAME, "\nTrade opened");
  }

//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING DetectFilling()
  {
   uint filling = (uint)SymbolInfoInteger(g_symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return(ORDER_FILLING_IOC);
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return(ORDER_FILLING_FOK);
   return(ORDER_FILLING_RETURN);
  }

//+------------------------------------------------------------------+
double NormalizePrice(const double price)
  {
   int digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   return(NormalizeDouble(price, digits));
  }

//+------------------------------------------------------------------+
double LotSize()
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0.0)
      return(0.0);

   double minlot = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MIN);
   double maxlot = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   if(minlot <= 0.0)
      minlot = InpMinLot;

   double raw = (balance / 100.0) * InpLotPer100;
   double lots = MathFloor(raw / step + 1e-12) * step;
   if(lots < InpMinLot)
      lots = InpMinLot;
   if(lots < minlot)
      lots = minlot;
   if(lots > InpMaxLot)
      lots = InpMaxLot;
   if(lots > maxlot)
      lots = maxlot;

   int digits = 2;
   if(step >= 1.0)
      digits = 0;
   else if(step >= 0.1)
      digits = 1;
   return(NormalizeDouble(lots, digits));
  }

//+------------------------------------------------------------------+
bool StopsOk(const double price, const double sl, const double tp)
  {
   long level = SymbolInfoInteger(g_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double point = SymbolInfoDouble(g_symbol, SYMBOL_POINT);
   double need = (double)level * point;
   if(MathAbs(price - sl) < need)
      return(false);
   if(MathAbs(tp - price) < need)
      return(false);
   if(sl == price || tp == price)
      return(false);
   return(true);
  }

//+------------------------------------------------------------------+
int CountOurPositions()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      n++;
     }
   return(n);
  }

//+------------------------------------------------------------------+
ulong FindOurTicket()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      return(ticket);
     }
   return(0);
  }

//+------------------------------------------------------------------+
string InitSlKey(const ulong ticket)
  {
   return("FredFxV1m5_initSL_" + IntegerToString((long)ticket));
  }

//+------------------------------------------------------------------+
void ManageBreakeven()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      long   type  = PositionGetInteger(POSITION_TYPE);

      double init_sl = g_initial_sl;
      string key = InitSlKey(ticket);
      if(GlobalVariableCheck(key))
         init_sl = GlobalVariableGet(key);
      if(init_sl == 0.0)
         init_sl = sl;

      double risk = MathAbs(entry - init_sl);
      if(risk <= 0.0)
         continue;

      double price = (type == POSITION_TYPE_BUY
                      ? SymbolInfoDouble(g_symbol, SYMBOL_BID)
                      : SymbolInfoDouble(g_symbol, SYMBOL_ASK));
      double profit_r = (type == POSITION_TYPE_BUY)
                        ? (price - entry) / risk
                        : (entry - price) / risk;
      if(profit_r < InpBreakevenAtR)
         continue;

      double new_sl = sl;
      if(type == POSITION_TYPE_BUY)
        {
         new_sl = MathMax(sl, entry);
         if(new_sl <= sl)
            continue;
        }
      else
        {
         new_sl = MathMin(sl, entry);
         if(new_sl >= sl)
            continue;
        }

      new_sl = NormalizePrice(new_sl);
      if(!g_trade.PositionModify(ticket, new_sl, tp))
         Print(ROBOT_NAME, " breakeven failed ", g_trade.ResultRetcodeDescription());
      else
         Print(ROBOT_NAME, " moved SL to breakeven ", DoubleToString(new_sl, (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS)));
     }
  }

//+------------------------------------------------------------------+
bool LoadBars(const ENUM_TIMEFRAMES tf, double &o[], double &h[], double &l[], double &c[])
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int n = CopyRates(g_symbol, tf, 1, InpLookback, rates);
   if(n < 20)
      return(false);
   ArrayResize(o, n);
   ArrayResize(h, n);
   ArrayResize(l, n);
   ArrayResize(c, n);
   for(int i = 0; i < n; i++)
     {
      o[i] = rates[i].open;
      h[i] = rates[i].high;
      l[i] = rates[i].low;
      c[i] = rates[i].close;
     }
   return(true);
  }

//+------------------------------------------------------------------+
double MaxOf(const double &a[], const int from, const int to_exclusive)
  {
   double m = a[from];
   for(int i = from + 1; i < to_exclusive; i++)
      if(a[i] > m)
         m = a[i];
   return(m);
  }

//+------------------------------------------------------------------+
double MinOf(const double &a[], const int from, const int to_exclusive)
  {
   double m = a[from];
   for(int i = from + 1; i < to_exclusive; i++)
      if(a[i] < m)
         m = a[i];
   return(m);
  }

//+------------------------------------------------------------------+
int DetectSwings(const double &high[], const double &low[], const int n,
                 const int left, const int right, Swing &swings[])
  {
   ArrayResize(swings, 0);
   if(n < left + right + 1)
      return(0);

   for(int i = left; i < n - right; i++)
     {
      double lh = MaxOf(high, i - left, i);
      double rh = MaxOf(high, i + 1, i + right + 1);
      double ll = MinOf(low, i - left, i);
      double rl = MinOf(low, i + 1, i + right + 1);
      if(high[i] > lh && high[i] >= rh)
        {
         int k = ArraySize(swings);
         ArrayResize(swings, k + 1);
         swings[k].index = i;
         swings[k].price = high[i];
         swings[k].kind  = SWING_HIGH;
        }
      if(low[i] < ll && low[i] <= rl)
        {
         int k = ArraySize(swings);
         ArrayResize(swings, k + 1);
         swings[k].index = i;
         swings[k].price = low[i];
         swings[k].kind  = SWING_LOW;
        }
     }
   return(ArraySize(swings));
  }

//+------------------------------------------------------------------+
void PushSweep(Sweep &sweeps[], const int index, const int direction, const double swept, const double wick)
  {
   int k = ArraySize(sweeps);
   ArrayResize(sweeps, k + 1);
   sweeps[k].index = index;
   sweeps[k].direction = direction;
   sweeps[k].swept_price = swept;
   sweeps[k].wick = wick;
  }

//+------------------------------------------------------------------+
int DetectSweeps(const double &high[], const double &low[], const double &close[],
                 const int n, const int left, const int right, Sweep &sweeps[])
  {
   ArrayResize(sweeps, 0);
   Swing swings[];
   DetectSwings(high, low, n, left, right, swings);
   int sc = ArraySize(swings);
   if(sc == 0)
      return(0);

   bool used_high[];
   bool used_low[];
   ArrayResize(used_high, n);
   ArrayResize(used_low, n);
   for(int u = 0; u < n; u++)
     {
      used_high[u] = false;
      used_low[u] = false;
     }

   Swing known_highs[];
   Swing known_lows[];
   ArrayResize(known_highs, 0);
   ArrayResize(known_lows, 0);

   for(int i = 0; i < n; i++)
     {
      for(int s = 0; s < sc; s++)
        {
         if(swings[s].index + right != i)
            continue;
         if(swings[s].kind == SWING_HIGH)
           {
            int k = ArraySize(known_highs);
            ArrayResize(known_highs, k + 1);
            known_highs[k] = swings[s];
           }
         else
           {
            int k = ArraySize(known_lows);
            ArrayResize(known_lows, k + 1);
            known_lows[k] = swings[s];
           }
        }

      for(int s = 0; s < ArraySize(known_lows); s++)
        {
         int idx = known_lows[s].index;
         if(used_low[idx] || idx >= i)
            continue;
         if(low[i] < known_lows[s].price && close[i] > known_lows[s].price)
           {
            PushSweep(sweeps, i, DIR_BULL, known_lows[s].price, low[i]);
            used_low[idx] = true;
           }
        }

      for(int s = 0; s < ArraySize(known_highs); s++)
        {
         int idx = known_highs[s].index;
         if(used_high[idx] || idx >= i)
            continue;
         if(high[i] > known_highs[s].price && close[i] < known_highs[s].price)
           {
            PushSweep(sweeps, i, DIR_BEAR, known_highs[s].price, high[i]);
            used_high[idx] = true;
           }
        }
     }
   return(ArraySize(sweeps));
  }

//+------------------------------------------------------------------+
bool LastRecentSweep(Sweep &sweeps[], const int n, const int bias, Sweep &out)
  {
   int last = n - 1;
   bool found = false;
   for(int i = 0; i < ArraySize(sweeps); i++)
     {
      int dist = last - sweeps[i].index;
      if(dist >= 0 && dist <= InpRecentBars && sweeps[i].direction == bias)
        {
         out = sweeps[i];
         found = true;
        }
     }
   return(found);
  }

//+------------------------------------------------------------------+
int DetectStructureHL(const double &high[], const double &low[], const double &close[],
                      const int n, const int left, const int right, Event &events[])
  {
   ArrayResize(events, 0);
   Swing swings[];
   DetectSwings(high, low, n, left, right, swings);

   int last_high_i = -1;
   int last_low_i  = -1;
   double last_high_p = 0.0;
   double last_low_p  = 0.0;
   int trend = DIR_NONE;
   bool used_high[];
   bool used_low[];
   ArrayResize(used_high, n);
   ArrayResize(used_low, n);
   for(int u = 0; u < n; u++)
     {
      used_high[u] = false;
      used_low[u] = false;
     }

   int sc = ArraySize(swings);
   for(int i = 0; i < n; i++)
     {
      for(int s = 0; s < sc; s++)
        {
         if(swings[s].index + right != i)
            continue;
         if(swings[s].kind == SWING_HIGH)
           {
            last_high_i = swings[s].index;
            last_high_p = swings[s].price;
           }
         else
           {
            last_low_i = swings[s].index;
            last_low_p = swings[s].price;
           }
        }

      if(last_high_i >= 0 && !used_high[last_high_i] && last_high_i < i)
        {
         if(close[i] > last_high_p)
           {
            int kind = (trend == DIR_NONE || trend == DIR_BULL) ? KIND_BOS : KIND_CHOCH;
            PushEvent(events, i, kind, DIR_BULL, last_high_p);
            if(kind == KIND_CHOCH)
               PushEvent(events, i, KIND_MSS, DIR_BULL, last_high_p);
            trend = DIR_BULL;
            used_high[last_high_i] = true;
           }
        }

      if(last_low_i >= 0 && !used_low[last_low_i] && last_low_i < i)
        {
         if(close[i] < last_low_p)
           {
            int kind = (trend == DIR_NONE || trend == DIR_BEAR) ? KIND_BOS : KIND_CHOCH;
            PushEvent(events, i, kind, DIR_BEAR, last_low_p);
            if(kind == KIND_CHOCH)
               PushEvent(events, i, KIND_MSS, DIR_BEAR, last_low_p);
            trend = DIR_BEAR;
            used_low[last_low_i] = true;
           }
        }
     }
   return(ArraySize(events));
  }

//+------------------------------------------------------------------+
void PushEvent(Event &events[], const int index, const int kind, const int direction, const double broken)
  {
   int k = ArraySize(events);
   ArrayResize(events, k + 1);
   events[k].index = index;
   events[k].kind = kind;
   events[k].direction = direction;
   events[k].broken = broken;
  }

//+------------------------------------------------------------------+
int InferBias(const double &high[], const double &low[], const double &close[],
              const int n, const Event &events[], const int ec)
  {
   if(ec > 0)
      return(events[ec - 1].direction);
   int lookback = 10;
   if(n < lookback + 1)
      return(DIR_NONE);
   int last = n - 1;
   int prev = n - lookback - 1;
   if(high[last] > high[prev] && low[last] >= low[prev])
      return(DIR_BULL);
   if(low[last] < low[prev] && high[last] <= high[prev])
      return(DIR_BEAR);
   if(close[last] > close[prev])
      return(DIR_BULL);
   if(close[last] < close[prev])
      return(DIR_BEAR);
   return(DIR_NONE);
  }

//+------------------------------------------------------------------+
bool HasRecentDirection(const Event &events[], const int n, const int bias)
  {
   int last = n - 1;
   int ec = ArraySize(events);
   for(int i = 0; i < ec; i++)
     {
      int dist = last - events[i].index;
      if(dist >= 0 && dist <= InpRecentBars && events[i].direction == bias)
         return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
bool HasKindDirection(const Event &events[], const int bias, const int kind_a, const int kind_b)
  {
   int last = ArraySize(events);
   int start = last - 40;
   if(start < 0)
      start = 0;
   for(int i = start; i < last; i++)
     {
      if(events[i].direction != bias)
         continue;
      if(events[i].kind == kind_a || events[i].kind == kind_b)
         return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
int DetectFvg(const double &high[], const double &low[], const double &close[], const int n, Zone &zones[])
  {
   ArrayResize(zones, 0);
   if(n < 3)
      return(0);
   for(int i = 1; i < n - 1; i++)
     {
      if(low[i + 1] > high[i - 1])
        {
         Zone z;
         z.start_index = i - 1;
         z.end_index = i + 1;
         z.low = high[i - 1];
         z.high = low[i + 1];
         z.direction = DIR_BULL;
         z.kind = ZONE_FVG;
         z.mitigated = MitigatedAfter(close, n, i + 2, z.low, DIR_BULL);
         PushZone(zones, z);
        }
      else if(high[i + 1] < low[i - 1])
        {
         Zone z;
         z.start_index = i - 1;
         z.end_index = i + 1;
         z.low = high[i + 1];
         z.high = low[i - 1];
         z.direction = DIR_BEAR;
         z.kind = ZONE_FVG;
         z.mitigated = MitigatedAfter(close, n, i + 2, z.high, DIR_BEAR);
         PushZone(zones, z);
        }
     }
   return(ArraySize(zones));
  }

//+------------------------------------------------------------------+
bool MitigatedAfter(const double &close[], const int n, const int start, const double level, const int direction)
  {
   if(start >= n)
      return(false);
   for(int i = start; i < n; i++)
     {
      if(direction == DIR_BULL && close[i] < level)
         return(true);
      if(direction == DIR_BEAR && close[i] > level)
         return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
void PushZone(Zone &zones[], const Zone &z)
  {
   int k = ArraySize(zones);
   ArrayResize(zones, k + 1);
   zones[k] = z;
  }

//+------------------------------------------------------------------+
int DetectOrderBlocks(const double &open[], const double &high[], const double &low[],
                      const double &close[], const int n, const Event &events[], Zone &zones[])
  {
   ArrayResize(zones, 0);
   int ec = ArraySize(events);
   int lookback = 15;
   for(int e = 0; e < ec; e++)
     {
      int start = events[e].index - lookback;
      if(start < 0)
         start = 0;
      int ob = -1;
      if(events[e].direction == DIR_BULL)
        {
         for(int i = events[e].index - 1; i >= start; i--)
            if(close[i] < open[i])
              {
               ob = i;
               break;
              }
        }
      else
        {
         for(int i = events[e].index - 1; i >= start; i--)
            if(close[i] > open[i])
              {
               ob = i;
               break;
              }
        }
      if(ob < 0)
         continue;

      bool seen = false;
      for(int k = 0; k < ArraySize(zones); k++)
         if(zones[k].start_index == ob)
           {
            seen = true;
            break;
           }
      if(seen)
         continue;

      Zone z;
      z.start_index = ob;
      z.end_index = ob;
      z.low = low[ob];
      z.high = high[ob];
      z.direction = events[e].direction;
      z.kind = ZONE_OB;
      z.mitigated = false;
      if(ob + 1 < n)
        {
         if(events[e].direction == DIR_BULL)
            z.mitigated = MitigatedAfter(close, n, ob + 1, z.low, DIR_BULL);
         else
            z.mitigated = MitigatedAfter(close, n, ob + 1, z.high, DIR_BEAR);
        }
      PushZone(zones, z);
     }
   return(ArraySize(zones));
  }

//+------------------------------------------------------------------+
bool PriceInZone(const double bar_low, const double bar_high, const Zone &z)
  {
   return(bar_low <= z.high && bar_high >= z.low);
  }

//+------------------------------------------------------------------+
bool BuildSignal(Signal &sig)
  {
   sig.valid = false;
   sig.direction = DIR_NONE;
   sig.sl = 0;
   sig.tp = 0;
   sig.confluence = 0;
   sig.zone_kind = 0;

   double h1o[], h1h[], h1l[], h1c[];
   double m15o[], m15h[], m15l[], m15c[];
   double m5o[], m5h[], m5l[], m5c[];
   if(!LoadBars(PERIOD_H1, h1o, h1h, h1l, h1c))
      return(false);
   if(!LoadBars(PERIOD_M15, m15o, m15h, m15l, m15c))
      return(false);
   if(!LoadBars(PERIOD_M5, m5o, m5h, m5l, m5c))
      return(false);

   if(ArraySize(h1o) < 20 || ArraySize(m15o) < 20 || ArraySize(m5o) < 20)
      return(false);
   int n1 = ArraySize(h1c);
   int n15 = ArraySize(m15c);
   int n5 = ArraySize(m5c);

   Event h1e[], m15e[], m5e[];
   DetectStructureHL(h1h, h1l, h1c, n1, InpSwingLeft, InpSwingRight, h1e);
   DetectStructureHL(m15h, m15l, m15c, n15, InpSwingLeft, InpSwingRight, m15e);
   DetectStructureHL(m5h, m5l, m5c, n5, InpSwingLeft, InpSwingRight, m5e);

   int bias = InferBias(h1h, h1l, h1c, n1, h1e, ArraySize(h1e));
   if(bias == DIR_NONE)
      return(false);

   bool m15_ok = HasRecentDirection(m15e, n15, bias);
   if(!m15_ok && InferBias(m15h, m15l, m15c, n15, m15e, ArraySize(m15e)) != bias)
      return(false);

   Sweep sweeps[];
   DetectSweeps(m5h, m5l, m5c, n5, InpSwingLeft, InpSwingRight, sweeps);
   Sweep sweep;
   sweep.index = -1;
   sweep.direction = DIR_NONE;
   sweep.swept_price = 0.0;
   sweep.wick = 0.0;
   bool have_sweep = LastRecentSweep(sweeps, n5, bias, sweep);
   if(InpRequireSweep && !have_sweep)
      return(false);

   Zone fvgs[], obs[], zones[];
   DetectFvg(m5h, m5l, m5c, n5, fvgs);
   DetectOrderBlocks(m5o, m5h, m5l, m5c, n5, m5e, obs);
   ArrayResize(zones, 0);
   for(int i = 0; i < ArraySize(fvgs); i++)
      if(!fvgs[i].mitigated && fvgs[i].direction == bias)
         PushZone(zones, fvgs[i]);
   for(int i = 0; i < ArraySize(obs); i++)
      if(!obs[i].mitigated && obs[i].direction == bias)
         PushZone(zones, obs[i]);
   if(ArraySize(zones) == 0)
      return(false);

   int last = n5 - 1;
   Zone tapped[];
   ArrayResize(tapped, 0);
   for(int i = 0; i < ArraySize(zones); i++)
      if(PriceInZone(m5l[last], m5h[last], zones[i]))
         PushZone(tapped, zones[i]);
   if(ArraySize(tapped) == 0)
      return(false);

   int best = 0;
   double best_d = 1e100;
   double px = m5c[last];
   for(int i = 0; i < ArraySize(tapped); i++)
     {
      double mid = 0.5 * (tapped[i].low + tapped[i].high);
      double d = MathMin(MathAbs(px - tapped[i].low), MathMin(MathAbs(px - tapped[i].high), MathAbs(px - mid)));
      if(d < best_d)
        {
         best_d = d;
         best = i;
        }
     }
   Zone zone = tapped[best];
   if(last >= 1)
     {
      double prev_close = m5c[last - 1];
      if(prev_close >= zone.low && prev_close <= zone.high)
         return(false);
     }

   int confluence = 2;
   if(HasKindDirection(m15e, bias, KIND_CHOCH, KIND_MSS))
      confluence++;
   confluence++;
   if(have_sweep)
      confluence++;
   if(zone.kind == ZONE_FVG || zone.kind == ZONE_OB)
      confluence++;
   if(HasRecentDirection(m5e, n5, bias))
      confluence++;
   if(confluence < InpMinConfluence)
      return(false);

   double entry = m5c[last];
   double sl, tp;
   if(bias == DIR_BULL)
     {
      sl = zone.low - InpSlBuffer;
      if(have_sweep)
         sl = MathMin(sl, sweep.wick - InpSlBuffer);
      if(sl >= entry)
         return(false);
      tp = entry + (entry - sl) * InpRiskReward;
     }
   else
     {
      sl = zone.high + InpSlBuffer;
      if(have_sweep)
         sl = MathMax(sl, sweep.wick + InpSlBuffer);
      if(sl <= entry)
         return(false);
      tp = entry - (sl - entry) * InpRiskReward;
     }

   sig.valid = true;
   sig.direction = bias;
   sig.sl = sl;
   sig.tp = tp;
   sig.confluence = confluence;
   sig.zone_kind = zone.kind;
   return(true);
  }
//+------------------------------------------------------------------+
