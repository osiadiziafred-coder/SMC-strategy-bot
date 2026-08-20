//+------------------------------------------------------------------+
//|                                                    fredfxV2.mq5  |
//| SMC Expert Advisor for XAUUSDm                                   |
//| Order Blocks + BOS + MSS + CHoCH + FVG | M5 M15 H1 | RR 1:2     |
//+------------------------------------------------------------------+
#property copyright "fredfxV2"
#property link      ""
#property version   "2.02"
#property description "fredfxV2 — SMC robot for XAUUSDm. H1 bias, M5/M15/H1 entries,"
#property description "Order Block + FVG retest, 1:2 RR, one position only, trail XL up,"
#property description "lot starts 0.01, first +0.01 at $150, then +0.01 every $100."

#include <Trade/Trade.mqh>

//--- inputs
input group "=== fredfxV2 core ==="
input string            InpSymbol            = "XAUUSDm";
input string            InpCommentPrefix     = "fredfxV2";
input ulong             InpMagic             = 20250819;
input int               InpMaxPositions      = 1;        // one live position only
input double            InpRiskReward        = 2.0;
input int               InpMaxTradesPerDay   = 24;
input bool              InpOnePerTimeframe   = true;
input bool              InpTradeNews         = true;     // kept for the spec; news is not blocked
input int               InpSlippagePoints    = 30;

input group "=== Lot sizing (balance tiers) ==="
input double            InpStartingLot           = 0.01;   // StartingLot
input double            InpBalanceStep           = 100.00; // BalanceStep
input double            InpLotIncrease           = 0.01;   // LotIncrease
input double            InpFirstIncreaseBalance  = 150.00; // FirstIncreaseBalance

input group "=== Trailing XL (SL) ==="
input double            InpTrailActivateR    = 1.0;
input bool              InpTrailToBE         = true;
input double            InpBEBuffer          = 0.05;
input double            InpTrailDistanceR    = 1.0;

input group "=== SMC detection ==="
input int               InpSwingLength       = 5;
input int               InpBarsToScan        = 300;
input double            InpFvgMinSize        = 0.20;
input int               InpObLookback        = 12;
input double            InpDispBodyAtr       = 1.2;
input int               InpAtrPeriod         = 14;
input int               InpMinScore          = 55;
input bool              InpCloseBreak        = true;
input double            InpZonePad           = 0.05;

input group "=== Safety ==="
input int               InpMaxSpreadPoints   = 0;        // 0 = off

//+------------------------------------------------------------------+
enum ENUM_FF_DIR
  {
   FF_NONE = 0,
   FF_BULL = 1,
   FF_BEAR = -1
  };

enum ENUM_FF_KIND
  {
   FF_KIND_NONE  = 0,
   FF_KIND_BOS   = 1,
   FF_KIND_CHOCH = 2,
   FF_KIND_MSS   = 3
  };

struct FFSwing
  {
   int      index;
   double   price;
   bool     isHigh;
  };

struct FFEvent
  {
   int      index;
   int      kind;
   int      dir;
   double   level;
   int      broken;
   bool     displacement;
  };

struct FFZone
  {
   int      index;
   int      dir;
   double   top;
   double   bottom;
   bool     mitigated;
   int      origin;
  };

struct FFSetup
  {
   ENUM_TIMEFRAMES tf;
   int      dir;          // FF_BULL / FF_BEAR
   int      kind;
   double   entry;
   double   sl;
   double   tp;
   int      score;
   bool     inOb;
   bool     inFvg;
   string   reason;
  };

CTrade         g_trade;
string         g_symbol     = "XAUUSDm";
datetime       g_lastBarM5  = 0;
datetime       g_lastBarM15 = 0;
datetime       g_lastBarH1  = 0;
int            g_digits     = 2;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_symbol = InpSymbol;
   StringTrimLeft(g_symbol);
   StringTrimRight(g_symbol);
   if(StringLen(g_symbol) < 1)
      g_symbol = "XAUUSDm";
   if(!SymbolSelect(g_symbol, true))
     {
      Print("fredfxV2: cannot select ", g_symbol, " — add it to Market Watch.");
      return(INIT_FAILED);
     }

   g_digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints((uint)InpSlippagePoints);
   g_trade.SetAsyncMode(false);
   ApplyFilling();

   Print("====================================================");
   Print("fredfxV2  SMC XAUUSDm robot");
   Print("Symbol ", g_symbol, " | Timeframes used: M5 M15 H1");
   Print("RR 1:", DoubleToString(InpRiskReward, 0),
         " | max ", InpMaxPositions, " positions");
   Print("Lots: start ", DoubleToString(InpStartingLot, 2),
         " | first +", DoubleToString(InpLotIncrease, 2),
         " at $", DoubleToString(InpFirstIncreaseBalance, 2),
         " then +", DoubleToString(InpLotIncrease, 2),
         " per $", DoubleToString(InpBalanceStep, 2));
   Print("Trail XL up at ", DoubleToString(InpTrailActivateR, 1), "R  | one position only");
   Print("====================================================");
   if(InpMaxPositions > 1 &&
      AccountInfoInteger(ACCOUNT_MARGIN_MODE) != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
      Print("Warning: this account is not hedging. Raise InpMaxPositions only on a hedging account.");
   if(StringFind(g_symbol, "XAU") < 0)
      Print("Warning: trading ", g_symbol, " — fredfxV2 was designed for XAUUSDm.");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Comment("");
  }

void OnTick()
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ||
      !MQLInfoInteger(MQL_TRADE_ALLOWED))
      return;

   TrailOpenPositions();

   bool fresh = false;
   if(IsNewBar(PERIOD_M5,  g_lastBarM5))  fresh = true;
   if(IsNewBar(PERIOD_M15, g_lastBarM15)) fresh = true;
   if(IsNewBar(PERIOD_H1,  g_lastBarH1))  fresh = true;
   if(fresh)
      ScanAndTrade();

   Dashboard();
  }

//+------------------------------------------------------------------+
//| Filling mode                                                       |
//+------------------------------------------------------------------+
void ApplyFilling()
  {
   long mode = SymbolInfoInteger(g_symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      g_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      g_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else
      g_trade.SetTypeFilling(ORDER_FILLING_RETURN);
  }

bool IsNewBar(ENUM_TIMEFRAMES tf, datetime &saved)
  {
   datetime t = iTime(g_symbol, tf, 0);
   if(t == 0)
      return(false);
   if(saved == 0)
     {
      saved = t;
      return(false);   // skip the bar that is already open when the EA starts
     }
   if(t != saved)
     {
      saved = t;
      return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Lot size from current balance (shrinks after drawdown too)         |
//| $0–$149.99 = StartingLot; first +LotIncrease at FirstIncreaseBalance |
//| then +LotIncrease every extra BalanceStep.                         |
//+------------------------------------------------------------------+
double NormalizeVolume(double lots)
  {
   double vmin = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   if(vmin <= 0.0)
      vmin = step;
   if(vmax < vmin)
      vmax = vmin;
   lots = MathMax(vmin, MathMin(vmax, lots));
   lots = MathFloor(lots / step + 1e-8) * step;
   if(lots < vmin)
      lots = vmin;
   if(lots > vmax)
      lots = vmax;
   int vdigits = 2;
   if(step < 0.01)
      vdigits = 3;
   if(step < 0.001)
      vdigits = 4;
   return(NormalizeDouble(lots, vdigits));
  }

double LotFromBalance(const double balance)
  {
   double lots = InpStartingLot;
   if(InpBalanceStep > 0.0 && InpLotIncrease > 0.0 &&
      balance + 1e-8 >= InpFirstIncreaseBalance)
     {
      int extra = (int)MathFloor((balance - InpFirstIncreaseBalance) / InpBalanceStep + 1e-8) + 1;
      if(extra < 1)
         extra = 1;
      lots = InpStartingLot + extra * InpLotIncrease;
     }
   return(lots);
  }

double LotSize()
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0.0)
      return(0.0);
   return(NormalizeVolume(LotFromBalance(balance)));
  }

double StopPad()
  {
   double point = SymbolInfoDouble(g_symbol, SYMBOL_POINT);
   int stops = (int)SymbolInfoInteger(g_symbol, SYMBOL_TRADE_STOPS_LEVEL);
   return(MathMax(InpZonePad, stops * point));
  }

double NP(const double price)
  {
   return(NormalizeDouble(price, g_digits));
  }

string KindName(const int kind)
  {
   if(kind == FF_KIND_MSS)
      return("MSS");
   if(kind == FF_KIND_CHOCH)
      return("CHOCH");
   if(kind == FF_KIND_BOS)
      return("BOS");
   return("NA");
  }

string TfTag(const ENUM_TIMEFRAMES tf)
  {
   if(tf == PERIOD_M5)
      return("M5");
   if(tf == PERIOD_M15)
      return("M15");
   if(tf == PERIOD_H1)
      return("H1");
   return("TF");
  }

string RiskKey(const ulong ticket)
  {
   return("FFV2R_" + IntegerToString((long)ticket));
  }
string BeKey(const ulong ticket)
  {
   return("FFV2B_" + IntegerToString((long)ticket));
  }

void StoreRisk(const ulong ticket, const double risk, const bool be)
  {
   GlobalVariableSet(RiskKey(ticket), risk);
   GlobalVariableSet(BeKey(ticket), be ? 1.0 : 0.0);
  }

double LoadRisk(const ulong ticket, const double fallback)
  {
   string k = RiskKey(ticket);
   if(GlobalVariableCheck(k))
      return(GlobalVariableGet(k));
   return(fallback);
  }

bool LoadBE(const ulong ticket)
  {
   string k = BeKey(ticket);
   if(GlobalVariableCheck(k))
      return(GlobalVariableGet(k) > 0.5);
   return(false);
  }

//+------------------------------------------------------------------+
ulong LatestOurPosition()
  {
   datetime newest = 0;
   ulong found = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      datetime t = (datetime)PositionGetInteger(POSITION_TIME);
      if(t >= newest)
        {
         newest = t;
         found = ticket;
        }
     }
   return(found);
  }

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
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      n++;
     }
   return(n);
  }

bool HasTfPosition(const ENUM_TIMEFRAMES tf)
  {
   string tag = "|" + TfTag(tf) + "|";
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      if(StringFind(PositionGetString(POSITION_COMMENT), tag) >= 0)
         return(true);
     }
   return(false);
  }

int TradesToday()
  {
   datetime from = iTime(g_symbol, PERIOD_D1, 0);
   if(from <= 0)
      from = TimeCurrent() - 86400;
   if(!HistorySelect(from, TimeCurrent()))
      return(0);
   int n = 0;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != g_symbol)
         continue;
      if((ulong)HistoryDealGetInteger(deal, DEAL_MAGIC) != InpMagic)
         continue;
      if(HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      n++;
     }
   return(n);
  }

//+------------------------------------------------------------------+
//| Trailing XL: at 1R move SL to BE, then trail with price            |
//+------------------------------------------------------------------+
void TrailOpenPositions()
  {
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != g_symbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      long type = PositionGetInteger(POSITION_TYPE);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      double price = (type == POSITION_TYPE_BUY) ? bid : ask;
      double origRisk = LoadRisk(ticket, MathAbs(entry - sl));
      if(origRisk <= 0.0)
         continue;

      double openProfit = (type == POSITION_TYPE_BUY) ? (price - entry) : (entry - price);
      double rMult = openProfit / origRisk;
      double newSl = sl;
      bool   be    = LoadBE(ticket);

      if(InpTrailToBE && rMult >= InpTrailActivateR)
        {
         if(type == POSITION_TYPE_BUY)
            newSl = MathMax(newSl, entry + InpBEBuffer);
         else
            newSl = (sl == 0.0 ? entry - InpBEBuffer : MathMin(newSl, entry - InpBEBuffer));
         be = true;
        }

      if(be && rMult >= InpTrailActivateR)
        {
         double dist = origRisk * InpTrailDistanceR;
         if(type == POSITION_TYPE_BUY)
           {
            double cand = price - dist;
            if(cand > newSl && cand < price)
               newSl = cand;
           }
         else
           {
            double cand = price + dist;
            if((newSl == 0.0 || cand < newSl) && cand > price)
               newSl = cand;
           }
        }

      newSl = NP(newSl);
      bool better = false;
      if(type == POSITION_TYPE_BUY && newSl > sl + SymbolInfoDouble(g_symbol, SYMBOL_POINT) * 0.5)
         better = true;
      if(type == POSITION_TYPE_SELL && (sl == 0.0 || newSl < sl - SymbolInfoDouble(g_symbol, SYMBOL_POINT) * 0.5))
         better = true;
      if(!better)
        {
         StoreRisk(ticket, origRisk, be);
         continue;
        }
      if(g_trade.PositionModify(ticket, newSl, tp))
        {
         StoreRisk(ticket, origRisk, be);
         Print("fredfxV2 trailed XL ticket=", ticket, " SL -> ", newSl);
        }
     }
  }

//+------------------------------------------------------------------+
bool LoadRates(const ENUM_TIMEFRAMES tf, MqlRates &rates[])
  {
   int want = MathMax(InpBarsToScan, InpSwingLength * 8 + 20);
   int copied = CopyRates(g_symbol, tf, 1, want, rates);   // skip forming bar
   if(copied < InpSwingLength * 2 + 10)
      return(false);
   ArraySetAsSeries(rates, false);                         // 0 = oldest
   return(true);
  }

void ComputeAtr(const MqlRates &r[], const int n, double &atr[])
  {
   ArrayResize(atr, n);
   double trSum = 0.0;
   for(int i = 0; i < n; i++)
     {
      double prev = (i == 0 ? r[i].close : r[i - 1].close);
      double tr = MathMax(r[i].high - r[i].low,
                          MathMax(MathAbs(r[i].high - prev), MathAbs(r[i].low - prev)));
      atr[i] = tr;
      trSum += tr;
      if(i >= InpAtrPeriod)
        {
         trSum -= atr[i - InpAtrPeriod];
         atr[i] = trSum / InpAtrPeriod;
        }
      else
         atr[i] = trSum / (i + 1);
     }
  }

int DetectSwings(const MqlRates &r[], const int n, const int length, FFSwing &sw[])
  {
   ArrayResize(sw, 0);
   for(int i = length; i < n - length; i++)
     {
      double leftH = r[i - length].high;
      double leftL = r[i - length].low;
      for(int k = i - length + 1; k < i; k++)
        {
         if(r[k].high > leftH)
            leftH = r[k].high;
         if(r[k].low < leftL)
            leftL = r[k].low;
        }
      double rightH = r[i + 1].high;
      double rightL = r[i + 1].low;
      for(int k = i + 2; k <= i + length; k++)
        {
         if(r[k].high > rightH)
            rightH = r[k].high;
         if(r[k].low < rightL)
            rightL = r[k].low;
        }
      if(r[i].high > leftH && r[i].high >= rightH)
        {
         int sz = ArraySize(sw);
         ArrayResize(sw, sz + 1);
         sw[sz].index = i;
         sw[sz].price = r[i].high;
         sw[sz].isHigh = true;
        }
      if(r[i].low < leftL && r[i].low <= rightL)
        {
         int sz = ArraySize(sw);
         ArrayResize(sw, sz + 1);
         sw[sz].index = i;
         sw[sz].price = r[i].low;
         sw[sz].isHigh = false;
        }
     }
   return(ArraySize(sw));
  }

int DetectStructure(const MqlRates &r[], const int n, const double &atr[],
                    const FFSwing &sw[], const int nsw, FFEvent &ev[])
  {
   ArrayResize(ev, 0);
   int lastHi = -1;
   int lastLo = -1;
   double lastHiPx = 0.0;
   double lastLoPx = 0.0;
   int trend = FF_NONE;

   for(int i = 0; i < n; i++)
     {
      for(int s = 0; s < nsw; s++)
        {
         if(sw[s].index + InpSwingLength != i)
            continue;
         if(sw[s].isHigh)
           {
            lastHi = sw[s].index;
            lastHiPx = sw[s].price;
           }
         else
           {
            lastLo = sw[s].index;
            lastLoPx = sw[s].price;
           }
        }

      double bullLvl = InpCloseBreak ? r[i].close : r[i].high;
      double bearLvl = InpCloseBreak ? r[i].close : r[i].low;
      double body = MathAbs(r[i].close - r[i].open);
      bool displaced = (atr[i] > 0.0 && body >= InpDispBodyAtr * atr[i]);

      if(lastHi >= 0 && i > lastHi && bullLvl > lastHiPx)
        {
         int kind = FF_KIND_BOS;
         int dir  = FF_BULL;
         if(trend == FF_BEAR)
            kind = displaced ? FF_KIND_MSS : FF_KIND_CHOCH;
         PushEvent(ev, i, kind, dir, lastHiPx, lastHi, displaced);
         trend = FF_BULL;
         lastHi = -1;
        }
      else if(lastLo >= 0 && i > lastLo && bearLvl < lastLoPx)
        {
         int kind = FF_KIND_BOS;
         int dir  = FF_BEAR;
         if(trend == FF_BULL)
            kind = displaced ? FF_KIND_MSS : FF_KIND_CHOCH;
         PushEvent(ev, i, kind, dir, lastLoPx, lastLo, displaced);
         trend = FF_BEAR;
         lastLo = -1;
        }
     }
   return(ArraySize(ev));
  }

void PushEvent(FFEvent &ev[], const int index, const int kind, const int dir,
               const double level, const int broken, const bool disp)
  {
   int sz = ArraySize(ev);
   ArrayResize(ev, sz + 1);
   ev[sz].index = index;
   ev[sz].kind = kind;
   ev[sz].dir = dir;
   ev[sz].level = level;
   ev[sz].broken = broken;
   ev[sz].displacement = disp;
  }

int DetectFvgs(const MqlRates &r[], const int n, FFZone &z[])
  {
   ArrayResize(z, 0);
   for(int i = 2; i < n; i++)
     {
      if(r[i].low > r[i - 2].high)
        {
         double bottom = r[i - 2].high;
         double top    = r[i].low;
         if(top - bottom >= InpFvgMinSize)
            PushZone(z, i - 1, FF_BULL, top, bottom, FF_KIND_NONE);
        }
      else if(r[i].high < r[i - 2].low)
        {
         double top    = r[i - 2].low;
         double bottom = r[i].high;
         if(top - bottom >= InpFvgMinSize)
            PushZone(z, i - 1, FF_BEAR, top, bottom, FF_KIND_NONE);
        }
     }
   for(int g = 0; g < ArraySize(z); g++)
     {
      for(int j = z[g].index + 2; j < n; j++)
        {
         if(z[g].dir == FF_BULL && r[j].low <= z[g].bottom)
           {
            z[g].mitigated = true;
            break;
           }
         if(z[g].dir == FF_BEAR && r[j].high >= z[g].top)
           {
            z[g].mitigated = true;
            break;
           }
        }
     }
   return(ArraySize(z));
  }

int DetectOrderBlocks(const MqlRates &r[], const int n, const FFEvent &ev[], const int nev, FFZone &ob[])
  {
   ArrayResize(ob, 0);
   for(int e = 0; e < nev; e++)
     {
      int start = MathMax(0, ev[e].index - InpObLookback);
      int found = -1;
      for(int i = ev[e].index - 1; i >= start; i--)
        {
         if(ev[e].dir == FF_BULL && r[i].close < r[i].open)
           {
            found = i;
            break;
           }
         if(ev[e].dir == FF_BEAR && r[i].close > r[i].open)
           {
            found = i;
            break;
           }
        }
      if(found < 0)
         continue;
      PushZone(ob, found, ev[e].dir, r[found].high, r[found].low, ev[e].kind);
      int last = ArraySize(ob) - 1;
      for(int j = ev[e].index + 1; j < n; j++)
        {
         if(ob[last].dir == FF_BULL && r[j].low <= ob[last].bottom)
           {
            ob[last].mitigated = true;
            break;
           }
         if(ob[last].dir == FF_BEAR && r[j].high >= ob[last].top)
           {
            ob[last].mitigated = true;
            break;
           }
        }
     }
   return(ArraySize(ob));
  }

void PushZone(FFZone &z[], const int index, const int dir, const double top,
              const double bottom, const int origin)
  {
   int sz = ArraySize(z);
   ArrayResize(z, sz + 1);
   z[sz].index = index;
   z[sz].dir = dir;
   z[sz].top = top;
   z[sz].bottom = bottom;
   z[sz].mitigated = false;
   z[sz].origin = origin;
  }

bool Taps(const double low, const double high, const double bottom, const double top)
  {
   return(high >= bottom && low <= top);
  }

int ScoreSetup(const bool htfOk, const FFEvent &ev, const bool inOb,
               const bool inFvg, const bool recentMss)
  {
   int score = 0;
   if(htfOk)
      score += 25;
   if(ev.kind == FF_KIND_MSS)
      score += 25;
   else if(ev.kind == FF_KIND_CHOCH)
      score += 18;
   else if(ev.kind == FF_KIND_BOS)
      score += 12;
   if(ev.displacement)
      score += 10;
   if(inOb)
      score += 20;
   if(inFvg)
      score += 20;
   if(recentMss)
      score += 5;
   if(score > 100)
      score = 100;
   return(score);
  }

bool BuildSetup(const ENUM_TIMEFRAMES tf, const MqlRates &r[], const int n,
                const FFEvent &ev[], const int nev,
                const FFZone &obs[], const int nob,
                const FFZone &fvgs[], const int nfvg,
                const int htfBias, FFSetup &out)
  {
   if(nev <= 0)
      return(false);
   int bias = ev[nev - 1].dir;
   if(htfBias != FF_NONE && bias != htfBias)
      return(false);

   int last = n - 1;
   double px = r[last].close;
   double lo = r[last].low;
   double hi = r[last].high;

   bool haveOb = false;
   bool haveFvg = false;
   double obTop = 0.0;
   double obBottom = 0.0;
   double fvgTop = 0.0;
   double fvgBottom = 0.0;
   double bestOb = 1e100;
   double bestFvg = 1e100;
   for(int i = 0; i < nob; i++)
     {
      if(obs[i].mitigated || obs[i].dir != bias)
         continue;
      if(!Taps(lo, hi, obs[i].bottom, obs[i].top))
         continue;
      double mid = 0.5 * (obs[i].top + obs[i].bottom);
      double d = MathAbs(mid - px);
      if(d < bestOb)
        {
         bestOb = d;
         obTop = obs[i].top;
         obBottom = obs[i].bottom;
         haveOb = true;
        }
     }
   for(int i = 0; i < nfvg; i++)
     {
      if(fvgs[i].mitigated || fvgs[i].dir != bias)
         continue;
      if(!Taps(lo, hi, fvgs[i].bottom, fvgs[i].top))
         continue;
      double mid = 0.5 * (fvgs[i].top + fvgs[i].bottom);
      double d = MathAbs(mid - px);
      if(d < bestFvg)
        {
         bestFvg = d;
         fvgTop = fvgs[i].top;
         fvgBottom = fvgs[i].bottom;
         haveFvg = true;
        }
     }
   if(!haveOb && !haveFvg)
      return(false);

   double sl = 0.0;
   double pad = StopPad();
   if(bias == FF_BULL)
     {
      double floorPx = px;
      bool set = false;
      if(haveOb)
        {
         floorPx = obBottom;
         set = true;
        }
      if(haveFvg)
        {
         floorPx = set ? MathMin(floorPx, fvgBottom) : fvgBottom;
         set = true;
        }
      sl = (set ? floorPx : px) - pad;
     }
   else
     {
      double ceilPx = px;
      bool set = false;
      if(haveOb)
        {
         ceilPx = obTop;
         set = true;
        }
      if(haveFvg)
        {
         ceilPx = set ? MathMax(ceilPx, fvgTop) : fvgTop;
         set = true;
        }
      sl = (set ? ceilPx : px) + pad;
     }

   bool recentMss = false;
   int from = MathMax(0, nev - 3);
   for(int i = from; i < nev; i++)
      if(ev[i].kind == FF_KIND_MSS && ev[i].dir == bias)
         recentMss = true;

   int score = ScoreSetup(true, ev[nev - 1], haveOb, haveFvg, recentMss);
   if(score < InpMinScore)
      return(false);

   out.tf = tf;
   out.dir = bias;
   out.kind = ev[nev - 1].kind;
   out.entry = px;
   out.sl = sl;
   out.tp = px;
   out.score = score;
   out.inOb = haveOb;
   out.inFvg = haveFvg;
   out.reason = KindName(out.kind);
   out.reason += (bias == FF_BULL ? " bullish" : " bearish");
   if(haveOb)
      out.reason += " + OB retest";
   if(haveFvg)
      out.reason += " + FVG fill";
   out.reason += " + HTF";
   return(true);
  }

int AnalyzeTf(const ENUM_TIMEFRAMES tf, const int htfBias, FFSetup &setup, bool &hasSetup, int &outBias)
  {
   hasSetup = false;
   outBias = FF_NONE;
   MqlRates r[];
   if(!LoadRates(tf, r))
      return(0);
   int n = ArraySize(r);
   double atr[];
   ComputeAtr(r, n, atr);
   FFSwing sw[];
   int nsw = DetectSwings(r, n, InpSwingLength, sw);
   FFEvent ev[];
   int nev = DetectStructure(r, n, atr, sw, nsw, ev);
   if(nev > 0)
      outBias = ev[nev - 1].dir;
   FFZone fvgs[];
   int nfvg = DetectFvgs(r, n, fvgs);
   FFZone obs[];
   int nob = DetectOrderBlocks(r, n, ev, nev, obs);
   hasSetup = BuildSetup(tf, r, n, ev, nev, obs, nob, fvgs, nfvg, htfBias, setup);
   return(nev);
  }

//+------------------------------------------------------------------+
void ScanAndTrade()
  {
   if(CountOurPositions() >= InpMaxPositions)
      return;
   if(TradesToday() >= InpMaxTradesPerDay)
      return;
   if(InpMaxSpreadPoints > 0)
     {
      long spread = SymbolInfoInteger(g_symbol, SYMBOL_SPREAD);
      if(spread > InpMaxSpreadPoints)
         return;
     }

   FFSetup dummy;
   dummy.tf = PERIOD_H1;
   dummy.dir = FF_NONE;
   dummy.kind = FF_KIND_NONE;
   dummy.entry = 0.0;
   dummy.sl = 0.0;
   dummy.tp = 0.0;
   dummy.score = 0;
   dummy.inOb = false;
   dummy.inFvg = false;
   dummy.reason = "";
   bool h1Has = false;
   int h1Bias = FF_NONE;
   AnalyzeTf(PERIOD_H1, FF_NONE, dummy, h1Has, h1Bias);
   if(h1Bias == FF_NONE)
      return;

   // H1 first so a tie keeps the higher-timeframe setup
   ENUM_TIMEFRAMES tfs[3];
   tfs[0] = PERIOD_H1;
   tfs[1] = PERIOD_M15;
   tfs[2] = PERIOD_M5;

   FFSetup best;
   best.tf = PERIOD_M5;
   best.dir = FF_NONE;
   best.kind = FF_KIND_NONE;
   best.entry = 0.0;
   best.sl = 0.0;
   best.tp = 0.0;
   best.score = -1;
   best.inOb = false;
   best.inFvg = false;
   best.reason = "";
   bool haveBest = false;

   for(int t = 0; t < 3; t++)
     {
      if(InpOnePerTimeframe && HasTfPosition(tfs[t]))
         continue;

      FFSetup setup;
      setup.tf = tfs[t];
      setup.dir = FF_NONE;
      setup.kind = FF_KIND_NONE;
      setup.entry = 0.0;
      setup.sl = 0.0;
      setup.tp = 0.0;
      setup.score = 0;
      setup.inOb = false;
      setup.inFvg = false;
      setup.reason = "";
      bool has = false;
      int biasIgnored = FF_NONE;
      AnalyzeTf(tfs[t], h1Bias, setup, has, biasIgnored);
      if(!has)
         continue;
      if(!haveBest || setup.score > best.score)
        {
         best = setup;
         haveBest = true;
        }
     }

   if(haveBest)
      OpenSetup(best);
  }

bool OpenSetup(const FFSetup &setup)
  {
   if(CountOurPositions() >= InpMaxPositions)
      return(false);
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   bool isBuy = (setup.dir == FF_BULL);
   double fill = isBuy ? ask : bid;
   double sl   = setup.sl;
   if(isBuy && sl >= fill)
      sl = fill - StopPad();
   if(!isBuy && sl <= fill)
      sl = fill + StopPad();
   double risk = MathAbs(fill - sl);
   if(risk <= 0.0)
      return(false);
   double tp = isBuy ? (fill + risk * InpRiskReward)
                     : (fill - risk * InpRiskReward);
   sl = NP(sl);
   tp = NP(tp);
   double lots = LotSize();
   if(lots <= 0.0)
      return(false);

   string cmt = InpCommentPrefix + "|" + TfTag(setup.tf) + "|" + KindName(setup.kind);
   ApplyFilling();
   bool ok;
   if(isBuy)
      ok = g_trade.Buy(lots, g_symbol, 0.0, sl, tp, cmt);
   else
      ok = g_trade.Sell(lots, g_symbol, 0.0, sl, tp, cmt);

   if(!ok)
     {
      // retry other filling modes (common on gold brokers)
      ENUM_ORDER_TYPE_FILLING fills[3];
      fills[0] = ORDER_FILLING_IOC;
      fills[1] = ORDER_FILLING_FOK;
      fills[2] = ORDER_FILLING_RETURN;
      ok = false;
      for(int i = 0; i < 3 && !ok; i++)
        {
         g_trade.SetTypeFilling(fills[i]);
         if(isBuy)
            ok = g_trade.Buy(lots, g_symbol, 0.0, sl, tp, cmt);
         else
            ok = g_trade.Sell(lots, g_symbol, 0.0, sl, tp, cmt);
        }
     }
   if(!ok)
     {
      Print("fredfxV2 order failed: ", g_trade.ResultRetcode(), " ", g_trade.ResultRetcodeDescription());
      return(false);
     }

   ulong ticket = LatestOurPosition();
   if(ticket != 0)
      StoreRisk(ticket, risk, false);
   Print("fredfxV2 opened ", (isBuy ? "BUY" : "SELL"), " ", TfTag(setup.tf),
         " lots=", lots, " sl=", sl, " tp=", tp, " score=", setup.score,
         " ", setup.reason);
   return(true);
  }

void Dashboard()
  {
   string s = "fredfxV2  " + g_symbol + "\n";
   s += "Lots: " + DoubleToString(LotSize(), 2);
   s += "   open: " + IntegerToString(CountOurPositions()) + "/" + IntegerToString(InpMaxPositions);
   s += "   today: " + IntegerToString(TradesToday()) + "\n";
   s += "RR 1:" + DoubleToString(InpRiskReward, 0);
   s += "   trail XL at " + DoubleToString(InpTrailActivateR, 1) + "R";
   s += "   news: " + (InpTradeNews ? "ON" : "OFF");
   Comment(s);
  }
//+------------------------------------------------------------------+
