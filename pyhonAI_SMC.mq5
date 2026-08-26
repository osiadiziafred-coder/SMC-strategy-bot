#property copyright "Python AI SMC Robot"
#property version   "1.00"
#property description "Native MQL5 Expert Advisor. Do not paste Python into this file."

//+------------------------------------------------------------------+
//| PythonAI_SMC.mq5  —  MetaTrader 5 Expert Advisor (MQL5 language) |
//|                                                                  |
//| YOUR ERRORS HAPPENED BECAUSE PYTHON WAS PASTED INTO .mq5         |
//| MetaEditor only compiles MQL5. Python files use .py              |
//|                                                                  |
//| Install:                                                         |
//| 1. File -> Open Data Folder                                      |
//| 2. Copy this file into MQL5\Experts\                             |
//| 3. Press F7 to compile — 0 errors                                |
//| 4. Attach to an XAUUSDm chart                                    |
//+------------------------------------------------------------------+

#include <Trade/Trade.mqh>

input string InpSymbol              = "XAUUSDm";
input int    InpMagic               = 20250824;
input double InpMinScore            = 70.0;
input double InpRewardRatio         = 2.0;
input double InpBalancePerStep      = 100.0;
input double InpLotPerStep          = 0.01;
input int    InpMaxSpreadPoints     = 80;
input int    InpSlippagePoints      = 40;
input double InpSpreadSpikeMult     = 2.5;
input int    InpSwingInternal       = 2;
input int    InpSwingExternal       = 5;
input int    InpObLookback          = 12;
input double InpObImpulseAtr        = 1.20;
input int    InpObMaxAge            = 24;
input int    InpFvgMinAtrMultX100   = 10;
input int    InpEqualAtrMultX100    = 15;
input int    InpSweepLookback       = 6;
input int    InpEventAgeM30         = 8;
input int    InpEventAgeM15         = 10;
input int    InpAtrPeriod           = 14;
input int    InpAtrSlow             = 50;
input double InpSlBufferAtr         = 0.10;
input double InpBreakevenR          = 1.0;
input int    InpBarsH1              = 300;
input int    InpBarsM30             = 400;
input int    InpBarsM15             = 500;
input double InpW_H1                = 20.0;
input double InpW_M30               = 15.0;
input double InpW_Sweep             = 15.0;
input double InpW_OB                = 15.0;
input double InpW_FVG               = 10.0;
input double InpW_BOS               = 5.0;
input double InpW_CHOCH             = 5.0;
input double InpW_MSS               = 10.0;
input double InpW_Good              = 10.0;
input double InpW_Poor              = -20.0;
input bool   InpTradeOnNewBarOnly   = true;

#define MAX_BARS    520
#define MAX_SWINGS  220
#define MAX_EVENTS  220
#define MAX_ZONES   120
#define MAX_SWEEPS  120
#define MAX_SPREADS 20

#define DIR_BUY   1
#define DIR_SELL -1

#define TREND_RANGE 0
#define TREND_BULL  1
#define TREND_BEAR -1

#define EVT_BOS   1
#define EVT_CHOCH 2
#define EVT_MSS   3

#define KIND_HIGH 1
#define KIND_LOW -1

struct Candle
  {
   datetime time;
   double   open;
   double   high;
   double   low;
   double   close;
  };

struct Swing
  {
   int      kind;
   int      index;
   datetime time;
   double   price;
  };

struct Event
  {
   int      type;
   int      direction;
   int      index;
   datetime time;
   double   level;
   double   close;
  };

struct Zone
  {
   int      direction;
   int      index;
   datetime time;
   double   low;
   double   high;
  };

struct Sweep
  {
   int      direction;
   int      index;
   datetime time;
   double   swept;
   double   wick;
   double   close;
   bool     equal_liq;
  };

struct Pool
  {
   int    kind;
   double price;
   int    index;
   bool   equal_liq;
   int    members;
  };

struct Analysis
  {
   Candle candles[MAX_BARS];
   int    n;
   int    trend;
   Swing  swingsI[MAX_SWINGS];
   int    nSwI;
   Swing  swingsE[MAX_SWINGS];
   int    nSwE;
   Event  events[MAX_EVENTS];
   int    nEv;
   Zone   obs[MAX_ZONES];
   int    nOb;
   Zone   fvgs[MAX_ZONES];
   int    nFvg;
   Sweep  sweeps[MAX_SWEEPS];
   int    nSwp;
  };

CTrade trade;
datetime g_lastM15 = 0;
double   g_spreads[MAX_SPREADS];
int      g_spreadCount = 0;
int      g_spreadPos = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(!SymbolSelect(InpSymbol, true))
     {
      Print("Cannot select symbol ", InpSymbol);
      return INIT_FAILED;
     }
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFilling(GetFilling());
   Print("Python AI SMC EA ready on ", InpSymbol, " magic=", InpMagic);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) {}

void OnTick()
  {
   if(_Symbol != InpSymbol)
     {
      static bool warned = false;
      if(!warned)
        {
         Print("Attach this EA to ", InpSymbol);
         warned = true;
        }
     }

   ManageBreakeven();

   if(CountOurPositions() >= 1)
      return;

   if(InpTradeOnNewBarOnly)
     {
      datetime t = iTime(InpSymbol, PERIOD_M15, 0);
      if(t == 0 || t == g_lastM15)
         return;
      g_lastM15 = t;
     }

   ObserveSpread();
   string block = SpreadBlockReason();
   if(block != "")
     {
      Print("Blocked: ", block);
      return;
     }

   Analysis h1, m30, m15;
   if(!LoadAnalysis(PERIOD_H1, InpBarsH1, h1))
      return;
   if(!LoadAnalysis(PERIOD_M30, InpBarsM30, m30))
      return;
   if(!LoadAnalysis(PERIOD_M15, InpBarsM15, m15))
      return;

   int direction = 0;
   double score = 0.0;
   string reason = "";
   double sl = 0.0, tp = 0.0, lots = 0.0;
   if(!BuildSetup(h1, m30, m15, direction, score, reason, sl, tp, lots))
     {
      Print("Skip: ", reason, " score=", DoubleToString(score, 1));
      return;
     }

   double price = (direction == DIR_BUY) ? SymbolInfoDouble(InpSymbol, SYMBOL_ASK)
                                        : SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   sl = NormalizePrice(sl);
   tp = NormalizePrice(tp);
   lots = NormalizeVolume(lots);

   bool ok = false;
   if(direction == DIR_BUY)
      ok = trade.Buy(lots, InpSymbol, price, sl, tp, "SMC-AI");
   else
      ok = trade.Sell(lots, InpSymbol, price, sl, tp, "SMC-AI");

   if(ok)
      Print("Order sent ", (direction == DIR_BUY ? "BUY" : "SELL"),
            " lots=", lots, " sl=", sl, " tp=", tp, " score=", score);
   else
      Print("OrderSend failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetFilling()
  {
   uint filling = (uint)SymbolInfoInteger(InpSymbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

double NormalizePrice(const double price)
  {
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
  }

double NormalizeVolume(double lots)
  {
   double vmin = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   lots = MathFloor(lots / step + 1e-8) * step;
   lots = MathMax(vmin, MathMin(vmax, lots));
   int d = 2;
   if(step < 0.01)
      d = 3;
   return NormalizeDouble(lots, d);
  }

double LotsFromBalance()
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance < InpBalancePerStep)
      return 0.0;
   return ((int)MathFloor(balance / InpBalancePerStep)) * InpLotPerStep;
  }

int CountOurPositions()
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      n++;
     }
   return n;
  }

void ManageBreakeven()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      long type = PositionGetInteger(POSITION_TYPE);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
      if(point <= 0.0)
         point = 0.01;

      if(type == POSITION_TYPE_BUY && sl >= entry && sl > 0.0)
         continue;
      if(type == POSITION_TYPE_SELL && sl <= entry && sl > 0.0)
         continue;

      double risk = MathAbs(entry - sl);
      if(risk <= 0.0)
         continue;

      if(type == POSITION_TYPE_BUY)
        {
         double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
         if(bid - entry >= InpBreakevenR * risk && entry > sl)
            trade.PositionModify(ticket, NormalizePrice(entry), tp);
        }
      else
        {
         double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
         if(entry - ask >= InpBreakevenR * risk && (sl == 0.0 || entry < sl))
            trade.PositionModify(ticket, NormalizePrice(entry), tp);
        }
     }
  }

void ObserveSpread()
  {
   int spr = (int)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   if(g_spreadCount < MAX_SPREADS)
     {
      g_spreads[g_spreadCount++] = (double)spr;
     }
   else
     {
      g_spreads[g_spreadPos] = (double)spr;
      g_spreadPos = (g_spreadPos + 1) % MAX_SPREADS;
     }
  }

double MedianSpread()
  {
   if(g_spreadCount <= 0)
      return (double)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   double tmp[];
   ArrayResize(tmp, g_spreadCount);
   for(int i = 0; i < g_spreadCount; i++)
      tmp[i] = g_spreads[i];
   ArraySort(tmp);
   return tmp[g_spreadCount / 2];
  }

string SpreadBlockReason()
  {
   int spr = (int)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   if(spr > InpMaxSpreadPoints)
      return "spread_too_wide";
   double med = MedianSpread();
   if(med > 0.0 && spr >= med * InpSpreadSpikeMult)
      return "spread_spike";
   return "";
  }

bool LoadCandles(ENUM_TIMEFRAMES tf, int bars, Candle &out[], int &n)
  {
   MqlRates rates[];
   int copied = CopyRates(InpSymbol, tf, 0, bars, rates);
   if(copied < 40)
      return false;
   ArraySetAsSeries(rates, false);
   n = copied - 1;
   if(n > MAX_BARS)
      n = MAX_BARS;
   for(int i = 0; i < n; i++)
     {
      out[i].time  = rates[i].time;
      out[i].open  = rates[i].open;
      out[i].high  = rates[i].high;
      out[i].low   = rates[i].low;
      out[i].close = rates[i].close;
     }
   return true;
  }

double CalcATR(const Candle &c[], const int n, const int period)
  {
   if(n < 2)
      return 0.0;
   int start = MathMax(1, n - period);
   double sum = 0.0;
   int cnt = 0;
   for(int i = start; i < n; i++)
     {
      double tr = c[i].high - c[i].low;
      double a = MathAbs(c[i].high - c[i - 1].close);
      double b = MathAbs(c[i].low - c[i - 1].close);
      if(a > tr) tr = a;
      if(b > tr) tr = b;
      sum += tr;
      cnt++;
     }
   return (cnt > 0) ? sum / cnt : 0.0;
  }

double Efficiency(const Candle &c[], const int n, const int period)
  {
   if(n < period + 1)
      return 0.0;
   int start = n - period;
   double net = MathAbs(c[n - 1].close - c[start].open);
   double path = 0.0;
   for(int i = start; i < n; i++)
      path += (c[i].high - c[i].low);
   if(path <= 0.0)
      return 0.0;
   return net / path;
  }

void DetectSwings(const Candle &c[], const int n, const int left, Swing &sw[], int &count)
  {
   count = 0;
   if(left < 1 || n < 2 * left + 1)
      return;
   for(int i = left; i < n - left; i++)
     {
      bool isHigh = true;
      bool isLow = true;
      for(int j = i - left; j <= i + left; j++)
        {
         if(j == i)
            continue;
         if(c[i].high <= c[j].high)
            isHigh = false;
         if(c[i].low >= c[j].low)
            isLow = false;
        }
      if(isHigh && count < MAX_SWINGS)
        {
         sw[count].kind = KIND_HIGH;
         sw[count].index = i;
         sw[count].time = c[i].time;
         sw[count].price = c[i].high;
         count++;
        }
      if(isLow && count < MAX_SWINGS)
        {
         sw[count].kind = KIND_LOW;
         sw[count].index = i;
         sw[count].time = c[i].time;
         sw[count].price = c[i].low;
         count++;
        }
     }
  }

int LastSwing(const Swing &sw[], const int nSw, const int kind, const int before, const int nth, Swing &out)
  {
   int found = 0;
   for(int i = nSw - 1; i >= 0; i--)
     {
      if(sw[i].kind != kind || sw[i].index >= before)
         continue;
      found++;
      if(found == nth)
        {
         out = sw[i];
         return 1;
        }
     }
   return 0;
  }

int ClassifyTrend(const Swing &sw[], const int nSw, const int before)
  {
   Swing h1, h2, l1, l2;
   if(!LastSwing(sw, nSw, KIND_HIGH, before, 1, h1))
      return TREND_RANGE;
   if(!LastSwing(sw, nSw, KIND_HIGH, before, 2, h2))
      return TREND_RANGE;
   if(!LastSwing(sw, nSw, KIND_LOW, before, 1, l1))
      return TREND_RANGE;
   if(!LastSwing(sw, nSw, KIND_LOW, before, 2, l2))
      return TREND_RANGE;
   bool hh = h1.price > h2.price;
   bool hl = l1.price > l2.price;
   bool lh = h1.price < h2.price;
   bool ll = l1.price < l2.price;
   if(hh && hl)
      return TREND_BULL;
   if(lh && ll)
      return TREND_BEAR;
   return TREND_RANGE;
  }

bool ConfirmedLast(const Swing &sw[], const int nSw, const int kind, const int nConfirm, const int before, Swing &out)
  {
   for(int i = nSw - 1; i >= 0; i--)
     {
      if(sw[i].kind != kind)
         continue;
      if(sw[i].index >= before)
         continue;
      if(sw[i].index + nConfirm >= before)
         continue;
      out = sw[i];
      return true;
     }
   return false;
  }

void DetectEvents(const Candle &c[], const int n, const int nInt, const int nExt,
                  const Swing &swI[], const int nI, const Swing &swE[], const int nE,
                  Event &ev[], int &nEv)
  {
   nEv = 0;
   int start = MathMax(2 * nExt + 1, 2 * nInt + 1);
   for(int i = start; i < n; i++)
     {
      int trend = ClassifyTrend(swE, nE, i);
      Swing ih, il, eh, el;
      bool hasIH = ConfirmedLast(swI, nI, KIND_HIGH, nInt, i, ih);
      bool hasIL = ConfirmedLast(swI, nI, KIND_LOW, nInt, i, il);
      bool hasEH = ConfirmedLast(swE, nE, KIND_HIGH, nExt, i, eh);
      bool hasEL = ConfirmedLast(swE, nE, KIND_LOW, nExt, i, el);
      int et = 0, dir = 0;
      double level = 0.0;
      if(trend == TREND_BEAR && hasEH && c[i].close > eh.price)
        { et = EVT_MSS; dir = DIR_BUY; level = eh.price; }
      else if(trend == TREND_BULL && hasEL && c[i].close < el.price)
        { et = EVT_MSS; dir = DIR_SELL; level = el.price; }
      else if(trend == TREND_BEAR && hasIH && c[i].close > ih.price)
        { et = EVT_CHOCH; dir = DIR_BUY; level = ih.price; }
      else if(trend == TREND_BULL && hasIL && c[i].close < il.price)
        { et = EVT_CHOCH; dir = DIR_SELL; level = il.price; }
      else if(trend == TREND_BULL && hasIH && c[i].close > ih.price)
        { et = EVT_BOS; dir = DIR_BUY; level = ih.price; }
      else if(trend == TREND_BEAR && hasIL && c[i].close < il.price)
        { et = EVT_BOS; dir = DIR_SELL; level = il.price; }
      else if(trend == TREND_RANGE)
        {
         if(hasEH && c[i].close > eh.price)
           { et = EVT_MSS; dir = DIR_BUY; level = eh.price; }
         else if(hasEL && c[i].close < el.price)
           { et = EVT_MSS; dir = DIR_SELL; level = el.price; }
        }
      if(et != 0 && nEv < MAX_EVENTS)
        {
         ev[nEv].type = et;
         ev[nEv].direction = dir;
         ev[nEv].index = i;
         ev[nEv].time = c[i].time;
         ev[nEv].level = level;
         ev[nEv].close = c[i].close;
         nEv++;
        }
     }
  }

void DetectOBs(const Candle &c[], const int n, const Event &ev[], const int nEv,
               const double minImpulse, Zone &obs[], int &nOb)
  {
   nOb = 0;
   for(int e = 0; e < nEv; e++)
     {
      if(ev[e].type != EVT_BOS && ev[e].type != EVT_MSS)
         continue;
      int start = MathMax(0, ev[e].index - InpObLookback);
      int obi = -1;
      for(int j = ev[e].index - 1; j >= start; j--)
        {
         if(ev[e].direction == DIR_BUY && c[j].close < c[j].open)
           { obi = j; break; }
         if(ev[e].direction == DIR_SELL && c[j].close >= c[j].open)
           { obi = j; break; }
        }
      if(obi < 0)
         continue;
      bool seen = false;
      for(int k = 0; k < nOb; k++)
         if(obs[k].index == obi)
            seen = true;
      if(seen)
         continue;
      if(MathAbs(c[ev[e].index].close - c[obi].close) < minImpulse)
         continue;
      bool mitigated = false;
      for(int j = obi + 1; j < n; j++)
        {
         if(ev[e].direction == DIR_BUY && c[j].close < c[obi].low)
           { mitigated = true; break; }
         if(ev[e].direction == DIR_SELL && c[j].close > c[obi].high)
           { mitigated = true; break; }
        }
      if(mitigated || nOb >= MAX_ZONES)
         continue;
      obs[nOb].direction = ev[e].direction;
      obs[nOb].index = obi;
      obs[nOb].time = c[obi].time;
      obs[nOb].low = c[obi].low;
      obs[nOb].high = c[obi].high;
      nOb++;
     }
  }

void DetectFVGs(const Candle &c[], const int n, const double minSize, Zone &g[], int &ng)
  {
   ng = 0;
   for(int i = 2; i < n; i++)
     {
      if(c[i].low > c[i - 2].high && (c[i].low - c[i - 2].high) >= minSize)
        {
         double lo = c[i - 2].high;
         double hi = c[i].low;
         bool filled = false;
         for(int j = i + 1; j < n; j++)
            if(c[j].low <= lo)
              { filled = true; break; }
         if(!filled && ng < MAX_ZONES)
           {
            g[ng].direction = DIR_BUY;
            g[ng].index = i;
            g[ng].time = c[i].time;
            g[ng].low = lo;
            g[ng].high = hi;
            ng++;
           }
        }
      else if(c[i].high < c[i - 2].low && (c[i - 2].low - c[i].high) >= minSize)
        {
         double lo = c[i].high;
         double hi = c[i - 2].low;
         bool filled = false;
         for(int j = i + 1; j < n; j++)
            if(c[j].high >= hi)
              { filled = true; break; }
         if(!filled && ng < MAX_ZONES)
           {
            g[ng].direction = DIR_SELL;
            g[ng].index = i;
            g[ng].time = c[i].time;
            g[ng].low = lo;
            g[ng].high = hi;
            ng++;
           }
        }
     }
  }

void BuildPools(const Swing &sw[], const int nSw, const double tol, Pool &p[], int &np)
  {
   np = 0;
   bool used[];
   ArrayResize(used, nSw);
   for(int u = 0; u < nSw; u++)
      used[u] = false;

   int kinds[2];
   kinds[0] = KIND_LOW;
   kinds[1] = KIND_HIGH;
   for(int kk = 0; kk < 2; kk++)
     {
      int kind = kinds[kk];
      for(int i = 0; i < nSw; i++)
        {
         if(used[i] || sw[i].kind != kind)
            continue;
         int members = 1;
         double sum = sw[i].price;
         int last = sw[i].index;
         used[i] = true;
         for(int j = i + 1; j < nSw; j++)
           {
            if(used[j] || sw[j].kind != kind)
               continue;
            if(MathAbs(sw[j].price - sw[i].price) <= tol)
              {
               used[j] = true;
               members++;
               sum += sw[j].price;
               if(sw[j].index > last)
                  last = sw[j].index;
              }
           }
         if(np < MAX_SWEEPS)
           {
            p[np].kind = kind;
            p[np].price = sum / members;
            p[np].index = last;
            p[np].equal_liq = (members >= 2);
            p[np].members = members;
            np++;
           }
        }
     }
  }

void DetectSweeps(const Candle &c[], const int n, const Pool &p[], const int np, Sweep &s[], int &ns)
  {
   ns = 0;
   for(int i = 0; i < n; i++)
     {
      for(int k = 0; k < np; k++)
        {
         if(p[k].index >= i)
            continue;
         if(ns >= MAX_SWEEPS)
            return;
         if(p[k].kind == KIND_LOW && c[i].low < p[k].price && c[i].close > p[k].price)
           {
            s[ns].direction = DIR_BUY;
            s[ns].index = i;
            s[ns].time = c[i].time;
            s[ns].swept = p[k].price;
            s[ns].wick = c[i].low;
            s[ns].close = c[i].close;
            s[ns].equal_liq = p[k].equal_liq;
            ns++;
           }
         else if(p[k].kind == KIND_HIGH && c[i].high > p[k].price && c[i].close < p[k].price)
           {
            s[ns].direction = DIR_SELL;
            s[ns].index = i;
            s[ns].time = c[i].time;
            s[ns].swept = p[k].price;
            s[ns].wick = c[i].high;
            s[ns].close = c[i].close;
            s[ns].equal_liq = p[k].equal_liq;
            ns++;
           }
        }
     }
  }

bool LoadAnalysis(ENUM_TIMEFRAMES tf, int bars, Analysis &a)
  {
   ZeroMemory(a);
   if(!LoadCandles(tf, bars, a.candles, a.n))
      return false;
   DetectSwings(a.candles, a.n, InpSwingInternal, a.swingsI, a.nSwI);
   DetectSwings(a.candles, a.n, InpSwingExternal, a.swingsE, a.nSwE);
   a.trend = ClassifyTrend(a.swingsE, a.nSwE, a.n);
   DetectEvents(a.candles, a.n, InpSwingInternal, InpSwingExternal,
                a.swingsI, a.nSwI, a.swingsE, a.nSwE, a.events, a.nEv);
   double a14 = CalcATR(a.candles, a.n, InpAtrPeriod);
   DetectOBs(a.candles, a.n, a.events, a.nEv, InpObImpulseAtr * a14, a.obs, a.nOb);
   DetectFVGs(a.candles, a.n, (InpFvgMinAtrMultX100 / 100.0) * a14, a.fvgs, a.nFvg);
   Pool pools[];
   ArrayResize(pools, MAX_SWEEPS);
   int np = 0;
   BuildPools(a.swingsI, a.nSwI, (InpEqualAtrMultX100 / 100.0) * a14, pools, np);
   DetectSweeps(a.candles, a.n, pools, np, a.sweeps, a.nSwp);
   return true;
  }

bool RecentEvent(const Analysis &a, const int dir, const int maxAge, int &typeOut)
  {
   int last = a.n - 1;
   typeOut = 0;
   for(int i = a.nEv - 1; i >= 0; i--)
     {
      if(a.events[i].direction != dir)
         continue;
      int age = last - a.events[i].index;
      if(age >= 0 && age <= maxAge)
        {
         if(a.events[i].type > typeOut)
            typeOut = a.events[i].type;
        }
     }
   return (typeOut != 0);
  }

bool RecentSweep(const Analysis &a, const int dir, const int lookback, Sweep &out)
  {
   int last = a.n - 1;
   for(int i = a.nSwp - 1; i >= 0; i--)
     {
      if(a.sweeps[i].direction != dir)
         continue;
      int age = last - a.sweeps[i].index;
      if(age >= 0 && age <= lookback)
        {
         out = a.sweeps[i];
         return true;
        }
     }
   return false;
  }

bool InteractingZone(const Analysis &a, const Zone &z[], const int nz, const int dir, const int maxAge, Zone &out)
  {
   if(a.n <= 0)
      return false;
   Candle last = a.candles[a.n - 1];
   int lasti = a.n - 1;
   for(int i = nz - 1; i >= 0; i--)
     {
      if(z[i].direction != dir)
         continue;
      if(lasti - z[i].index > maxAge)
         continue;
      bool overlap = (last.low <= z[i].high && last.high >= z[i].low);
      bool inside = (last.close >= z[i].low && last.close <= z[i].high);
      if(!overlap && !inside)
         continue;
      if(dir == DIR_BUY && last.close < z[i].low)
         continue;
      if(dir == DIR_SELL && last.close > z[i].high)
         continue;
      out = z[i];
      return true;
     }
   return false;
  }

bool ConditionsPoor(const Analysis &m15, const double spreadPts, double &atr14, double &atrRatio, double &eff)
  {
   atr14 = CalcATR(m15.candles, m15.n, InpAtrPeriod);
   double slow = CalcATR(m15.candles, m15.n, InpAtrSlow);
   atrRatio = (slow > 0.0) ? atr14 / slow : 1.0;
   eff = Efficiency(m15.candles, m15.n, InpAtrPeriod);
   double med = MedianSpread();
   double sprRatio = (med > 0.0) ? spreadPts / med : 1.0;
   bool choppy = (eff < 0.18 && atrRatio <= 1.05);
   bool lowv = (atrRatio < 0.60);
   bool extreme = (atrRatio > 2.20);
   bool spike = (sprRatio >= InpSpreadSpikeMult);
   return (choppy || lowv || extreme || spike);
  }

double ScoreSetup(const int dir, const Analysis &h1, const Analysis &m30, const Analysis &m15,
                  const bool hasSweep, const bool equalSweep, const bool hasOB, const bool hasFVG,
                  const int m15Type, const bool poor, const double atrRatio, const double eff)
  {
   double total = 0.0;
   int want = (dir == DIR_BUY) ? TREND_BULL : TREND_BEAR;
   if(h1.trend == want)
      total += InpW_H1;
   else if(h1.trend != TREND_RANGE)
      total -= 25.0;

   int m30type = 0;
   bool m30ev = RecentEvent(m30, dir, InpEventAgeM30, m30type);
   if(m30.trend == want || m30ev)
      total += InpW_M30;
   if(hasSweep)
     {
      total += InpW_Sweep;
      if(equalSweep)
         total += 3.0;
     }
   if(hasOB)
      total += InpW_OB;
   if(hasFVG)
      total += InpW_FVG;
   if(m15Type == EVT_BOS)
      total += InpW_BOS;
   if(m15Type == EVT_CHOCH)
      total += InpW_CHOCH;
   if(m15Type == EVT_MSS)
      total += InpW_MSS;
   if(poor)
      total += InpW_Poor;
   else if(eff >= 0.30 && atrRatio >= 0.8 && atrRatio <= 1.8)
      total += InpW_Good;
   return total;
  }

bool BuildSetup(const Analysis &h1, const Analysis &m30, const Analysis &m15,
                int &direction, double &score, string &reason,
                double &sl, double &tp, double &lots)
  {
   score = 0.0;
   if(h1.trend == TREND_RANGE)
     { reason = "h1_ranging"; return false; }

   direction = (h1.trend == TREND_BULL) ? DIR_BUY : DIR_SELL;

   int dummy = 0;
   bool m30ok = (m30.trend == h1.trend) || RecentEvent(m30, direction, InpEventAgeM30, dummy);
   if(!m30ok)
     { reason = "m30_no_confirmation"; return false; }

   Sweep sweep;
   bool hasSweep = RecentSweep(m15, direction, InpSweepLookback, sweep);
   if(!hasSweep)
      hasSweep = RecentSweep(m30, direction, MathMax(3, InpSweepLookback / 2), sweep);
   if(!hasSweep)
     { reason = "no_recent_liquidity_sweep"; return false; }

   Zone ob, fvg;
   bool hasOB = InteractingZone(m15, m15.obs, m15.nOb, direction, InpObMaxAge, ob);
   if(!hasOB)
      hasOB = InteractingZone(m30, m30.obs, m30.nOb, direction, InpObMaxAge, ob);
   bool hasFVG = InteractingZone(m15, m15.fvgs, m15.nFvg, direction, InpObMaxAge, fvg);
   if(!hasFVG)
      hasFVG = InteractingZone(m30, m30.fvgs, m30.nFvg, direction, InpObMaxAge, fvg);
   if(!hasOB && !hasFVG)
     { reason = "no_ob_or_fvg_interaction"; return false; }

   int m15type = 0;
   if(!RecentEvent(m15, direction, InpEventAgeM15, m15type))
     { reason = "no_m15_structure_confirmation"; return false; }

   double atr14, atrRatio, eff;
   int spr = (int)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   bool poor = ConditionsPoor(m15, (double)spr, atr14, atrRatio, eff);
   score = ScoreSetup(direction, h1, m30, m15, true, sweep.equal_liq, hasOB, hasFVG, m15type, poor, atrRatio, eff);
   if(score < InpMinScore)
     { reason = "score_below_min"; return false; }

   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double entry = (direction == DIR_BUY) ? ask : bid;
   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   int stops = (int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = MathMax(50 * point, stops * point);
   double buffer = InpSlBufferAtr * atr14;

   if(direction == DIR_BUY)
     {
      sl = sweep.wick;
      if(hasOB && ob.low < sl)
         sl = ob.low;
      if(hasFVG && fvg.low < sl)
         sl = fvg.low;
      sl -= buffer;
      if(entry - sl < minDist)
         sl = entry - minDist;
      if(entry - sl <= 0.0)
        { reason = "invalid_sl"; return false; }
      tp = entry + InpRewardRatio * (entry - sl);
     }
   else
     {
      sl = sweep.wick;
      if(hasOB && ob.high > sl)
         sl = ob.high;
      if(hasFVG && fvg.high > sl)
         sl = fvg.high;
      sl += buffer;
      if(sl - entry < minDist)
         sl = entry + minDist;
      if(sl - entry <= 0.0)
        { reason = "invalid_sl"; return false; }
      tp = entry - InpRewardRatio * (sl - entry);
     }

   lots = LotsFromBalance();
   if(lots <= 0.0)
     { reason = "lots_zero"; return false; }

   reason = "take_setup";
   return true;
  }

//+------------------------------------------------------------------+
