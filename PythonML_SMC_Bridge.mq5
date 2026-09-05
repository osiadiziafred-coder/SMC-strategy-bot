#property copyright "Python ML SMC Robot"
#property version   "3.04"
#property description "SMC dual-pair PRO. Trades only A+ setups (skill 85+) on V75 and V50 (1s)."

//+------------------------------------------------------------------+
//| PythonML_SMC_Bridge.mq5                                          |
//| PICK TRADES when BOTH pairs print an aligned SMC setup:          |
//|   Volatility 75 Index  AND  Volatility 50 (1s) Index             |
//| Setup = BOS/CHoCH/MSS + liquidity sweep (or EQ sweep extra)      |
//|         + Order Block or FVG tap                                 |
//| Python command.json still works. Overlay stays on the chart chat.|
//| Common\Files\smc_bridge\command.json  /  status.json             |
//+------------------------------------------------------------------+

#include <Trade/Trade.mqh>

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
#define OBJ_PREFIX    "SMCBR_"

input string InpSymbol1            = "Volatility 75 Index";
input string InpSymbol2            = "Volatility 50 (1s) Index";
input ENUM_TIMEFRAMES InpTf1       = PERIOD_M5;
input ENUM_TIMEFRAMES InpTf2       = PERIOD_M1;
input int    InpMagic              = 20250824;
input int    InpMaxSpreadPoints    = 300;
input int    InpSlippagePoints     = 40;
input double InpDefaultBeR         = 1.0;
input double InpDefaultTrailR      = 1.5;
input bool   InpTrailEnabled       = true;
input double InpTrailLockR         = 0.50;
input double InpBeBufferPoints     = 0.0;
input bool   InpProtectIfPythonLost = true;
input int    InpPythonTimeoutSec   = 45;
input string InpFolder             = "smc_bridge";
input bool   InpAutoTrade          = true;
input bool   InpRequireBothPairs   = true;
input double InpLot1               = 0.0;
input double InpLot2               = 0.0;
input double InpRiskReward         = 2.0;
input int    InpMinConfluence      = 4;
input int    InpRecentBars         = 40;
input int    InpCooldownBars       = 8;
input bool   InpRequireSweep       = true;
input double InpSlAtrMult          = 0.05;
input bool   InpShowSmcChat        = true;
input bool   InpDrawSmcObjects     = true;
input bool   InpLogSmcEvents       = true;
input int    InpLookback           = 250;
input int    InpSwingLeft          = 2;
input int    InpSwingRight         = 2;
input double InpEqualAtrMult       = 0.15;
input int    InpDrawMaxFvg         = 6;
input int    InpDrawMaxOb          = 5;
input int    InpDrawMaxEvents      = 10;
input int    InpDrawMaxSweeps      = 8;
input bool   InpProSkill          = true;
input int    InpMinSkillScore     = 85;
input ENUM_TIMEFRAMES InpBiasTf1  = PERIOD_H1;
input ENUM_TIMEFRAMES InpBiasTf2  = PERIOD_M5;
input double InpRiskPercent       = 0.50;
input double InpMaxDailyLossPct   = 3.0;
input int    InpMaxTradesPerDay   = 4;
input double InpMinEfficiency     = 0.28;
input double InpPdBuyMax          = 0.45;
input double InpPdSellMin         = 0.55;
input bool   InpRequireHtf        = true;
input bool   InpRequirePd         = true;
input bool   InpRequireChoChSeq   = true;
input bool   InpRequireDisplace   = true;

CTrade   trade;
string   g_sym1 = "";
string   g_sym2 = "";
string   g_lastId = "";
datetime g_lastPython = 0;
double   g_beR = 1.0;
double   g_trailR = 1.5;
bool     g_trailOn = true;
double   g_trailLock = 0.50;
int      g_lastRetcode = 0;
string   g_lastError = "";
ulong    g_lastTicket = 0;
string   g_lastResultJson = "";
double   g_trackRisk[];
ulong    g_trackTicket[];
datetime g_lastBar1 = 0;
datetime g_lastBar2 = 0;
int      g_loggedEvt1 = -1;
int      g_loggedEvt2 = -1;
int      g_loggedSwp1 = -1;
int      g_loggedSwp2 = -1;
string   g_chat1 = "";
string   g_chat2 = "";
string   g_smcJson1 = "";
string   g_smcJson2 = "";
uint     g_lastDashMs = 0;
string   g_pickStatus = "waiting for setup on both pairs";
datetime g_closeTime1 = 0;
datetime g_closeTime2 = 0;
bool     g_hadPos1 = false;
bool     g_hadPos2 = false;
double   g_dayStartEquity = 0.0;
datetime g_dayStamp = 0;
int      g_dayTrades = 0;

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
   bool              equal_extra;
   int               members;
  };

struct Pool
  {
   int               kind;
   double            price;
   int               index;
   bool              equal;
   int               members;
  };

struct BarSet
  {
   int               n;
   datetime          t[];
   double            o[];
   double            h[];
   double            l[];
   double            c[];
  };

struct TradeSetup
  {
   bool              valid;
   int               direction;
   double            sl;
   double            tp;
   int               confluence;
   int               zone_kind;
   bool              eq_extra;
   string            why;
   int               skill;
   string            missing;
   double            pd;
   double            er;
  };

TradeSetup g_setup1;
TradeSetup g_setup2;

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   g_beR = InpDefaultBeR;
   g_trailR = InpDefaultTrailR;
   g_trailOn = InpTrailEnabled;
   g_trailLock = InpTrailLockR;

   g_sym1 = ResolveSymbol(InpSymbol1, 1);
   g_sym2 = ResolveSymbol(InpSymbol2, 2);
   if(_Symbol != "")
     {
      int chart_kind = SymbolFamily(_Symbol);
      if(chart_kind == 1 && g_sym1 == "")
         g_sym1 = _Symbol;
      if(chart_kind == 2 && g_sym2 == "")
         g_sym2 = _Symbol;
      if(chart_kind == 1)
         g_sym1 = _Symbol;
      if(chart_kind == 2)
         g_sym2 = _Symbol;
     }

   if(g_sym1 == "" && g_sym2 == "")
     {
      Print("Cannot select Volatility 75 Index or Volatility 50 (1s) Index. Enable them in Market Watch.");
      return INIT_FAILED;
     }
   if(g_sym1 != "" && !SymbolSelect(g_sym1, true))
      g_sym1 = "";
   if(g_sym2 != "" && !SymbolSelect(g_sym2, true))
      g_sym2 = "";
   if(g_sym1 == "" && g_sym2 == "")
      return INIT_FAILED;

   FolderCreate(InpFolder, FILE_COMMON);
   ClearSetup(g_setup1);
   ClearSetup(g_setup2);
   ResetDayIfNeeded();
   WriteStatus("init", 0, "ready");
   RefreshSmc(true);
   MaybeAutoTrade();
   UpdateChat();
   Print("SMC dual-pair bot ready on ",
         (g_sym1 != "" ? g_sym1 : "-"),
         " / ",
         (g_sym2 != "" ? g_sym2 : "-"),
         ". Picks BUY/SELL when both pairs have an aligned SMC setup.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, OBJ_PREFIX);
   Comment("");
   WriteStatus("deinit", reason, "stopped");
  }

void OnTick()
  {
   ResetDayIfNeeded();
   ReadAndExecuteCommand();
   if(InpAutoTrade || InpProtectIfPythonLost || PythonFresh())
     {
      if(g_sym1 != "")
         LocalManageSymbol(g_sym1);
      if(g_sym2 != "")
         LocalManageSymbol(g_sym2);
     }
   NotePositionLifecycle();
   RefreshSmc(false);
   MaybeAutoTrade();
   uint now = GetTickCount();
   if(now - g_lastDashMs >= 400)
     {
      UpdateChat();
      g_lastDashMs = now;
     }
   WriteStatus("tick", g_lastRetcode, g_lastError);
  }

bool PythonFresh()
  {
   if(g_lastPython == 0)
      return false;
   return ((TimeCurrent() - g_lastPython) <= InpPythonTimeoutSec);
  }

int SymbolFamily(const string name)
  {
   string k = KeyOf(name);
   if(StringFind(k, "1hz50") >= 0)
      return 2;
   if(StringFind(k, "vol") >= 0 && StringFind(k, "50") >= 0 && StringFind(k, "1s") >= 0)
      return 2;
   if(k == "r75" || k == "vol75" || k == "v75")
      return 1;
   if(StringFind(k, "vol") >= 0 && StringFind(k, "75") >= 0 &&
      StringFind(k, "1s") < 0 && StringFind(k, "1hz") < 0)
      return 1;
   return 0;
  }

string KeyOf(string name)
  {
   StringToLower(name);
   string out = "";
   int n = StringLen(name);
   for(int i = 0; i < n; i++)
     {
      ushort ch = StringGetCharacter(name, i);
      if((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9'))
         out += ShortToString(ch);
     }
   return out;
  }

string ResolveSymbol(const string requested, const int which)
  {
   string tries[];
   ArrayResize(tries, 0);
   PushAlias(tries, requested);
   if(which == 1)
     {
      PushAlias(tries, "Volatility 75 Index");
      PushAlias(tries, "Volatility 75");
      PushAlias(tries, "Vol 75 Index");
      PushAlias(tries, "VOL75");
      PushAlias(tries, "V75");
      PushAlias(tries, "R_75");
      PushAlias(tries, "Volatility75");
      PushAlias(tries, "Volatility_75_Index");
     }
   else
     {
      PushAlias(tries, "Volatility 50 (1s) Index");
      PushAlias(tries, "Volatility 50 (1s)");
      PushAlias(tries, "Volatility 50 Index 1s");
      PushAlias(tries, "Volatility 50 1s Index");
      PushAlias(tries, "1HZ50V");
      PushAlias(tries, "VOL50_1s");
      PushAlias(tries, "V50_1s");
      PushAlias(tries, "Vol 50 1s");
     }

   for(int i = 0; i < ArraySize(tries); i++)
     {
      if(tries[i] == "")
         continue;
      if(SymbolSelect(tries[i], true))
         return tries[i];
     }

   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string s = SymbolName(i, false);
      if(SymbolFamily(s) == which)
        {
         if(SymbolSelect(s, true))
            return s;
        }
     }
   return "";
  }

void PushAlias(string &tries[], const string value)
  {
   if(value == "")
      return;
   int n = ArraySize(tries);
   ArrayResize(tries, n + 1);
   tries[n] = value;
  }

bool IsOurSymbol(const string symbol)
  {
   return ((g_sym1 != "" && symbol == g_sym1) || (g_sym2 != "" && symbol == g_sym2));
  }

string DefaultTradeSymbol()
  {
   if(_Symbol == g_sym1 || _Symbol == g_sym2)
      return _Symbol;
   if(g_sym1 != "")
      return g_sym1;
   return g_sym2;
  }

ENUM_TIMEFRAMES TfFor(const string symbol)
  {
   if(symbol == _Symbol)
      return (ENUM_TIMEFRAMES)_Period;
   if(symbol == g_sym1)
      return InpTf1;
   return InpTf2;
  }

ENUM_ORDER_TYPE_FILLING DetectFilling(const string symbol)
  {
   long mode = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if((mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }

void ReadAndExecuteCommand()
  {
   string path = InpFolder + "\\command.json";
   if(!FileIsExist(path, FILE_COMMON))
      return;
   int h = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   string raw = "";
   while(!FileIsEnding(h))
      raw += FileReadString(h);
   FileClose(h);
   if(StringLen(raw) < 8)
      return;

   string action = JsonString(raw, "action");
   string id = JsonString(raw, "id");
   if(id == "")
     {
      g_lastError = "missing_command_id";
      return;
     }
   if(id == g_lastId)
      return;

   if(action == "HEARTBEAT" || action == "NONE")
     {
      g_lastPython = TimeCurrent();
      g_lastId = id;
      g_lastError = "heartbeat";
      g_lastRetcode = 0;
      return;
     }

   if((action == "BUY" || action == "SELL") && !PythonFresh())
     {
      WriteResult(id, false, 0, 0.0, 0.0, 0.0, "python_disconnected");
      g_lastId = id;
      return;
     }

   g_lastPython = TimeCurrent();
   string symbol = JsonString(raw, "symbol");
   if(symbol == "")
      symbol = DefaultTradeSymbol();
   else
     {
      string resolved = symbol;
      int fam = SymbolFamily(symbol);
      if(fam == 1 && g_sym1 != "")
         resolved = g_sym1;
      else if(fam == 2 && g_sym2 != "")
         resolved = g_sym2;
      else if(SymbolSelect(symbol, true))
         resolved = symbol;
      symbol = resolved;
     }
   if(!IsOurSymbol(symbol))
     {
      WriteResult(id, false, 0, 0.0, 0.0, 0.0, "symbol_not_allowed");
      g_lastId = id;
      return;
     }

   double lots = JsonNumber(raw, "lots");
   double sl = JsonNumber(raw, "sl");
   double tp = JsonNumber(raw, "tp");
   double be = JsonNumber(raw, "breakeven_r");
   if(be > 0.0)
      g_beR = be;
   double tr = JsonNumber(raw, "trail_start_r");
   if(tr > 0.0)
      g_trailR = tr;
   if(HasJsonKey(raw, "trail_enabled"))
      g_trailOn = JsonFlag(raw, "trail_enabled", g_trailOn);

   string err = BrokerBlockReason(symbol, lots, sl, tp, action);
   if(err != "" && (action == "BUY" || action == "SELL"))
     {
      WriteResult(id, false, 0, 0.0, sl, tp, err);
      g_lastId = id;
      return;
     }

   bool ok = false;
   ulong ticket = 0;
   double price = 0.0;
   trade.SetTypeFilling(DetectFilling(symbol));
   if(action == "BUY" || action == "SELL")
     {
      if(CountOurPositions(symbol) >= 1)
        {
         WriteResult(id, false, 0, 0.0, sl, tp, "max_positions");
         g_lastId = id;
         return;
        }
      price = (action == "BUY") ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                : SymbolInfoDouble(symbol, SYMBOL_BID);
      sl = NormalizePrice(symbol, sl);
      tp = NormalizePrice(symbol, tp);
      lots = NormalizeVolume(symbol, lots);
      if(action == "BUY")
         ok = trade.Buy(lots, symbol, price, sl, tp, "SMC-AI");
      else
         ok = trade.Sell(lots, symbol, price, sl, tp, "SMC-AI");
      g_lastRetcode = (int)trade.ResultRetcode();
      ticket = trade.ResultOrder();
      if(ok)
        {
         price = trade.ResultPrice();
         RememberRisk(ticket, MathAbs(price - sl));
        }
      g_lastTicket = ticket;
      g_lastError = ok ? "filled" : trade.ResultRetcodeDescription();
      WriteResult(id, ok, ticket, price, sl, tp, g_lastError);
     }
   else if(action == "MODIFY")
     {
      ticket = (ulong)JsonNumber(raw, "ticket");
      if(!PositionSelectByTicket(ticket))
        {
         WriteResult(id, false, ticket, 0.0, sl, tp, "ticket_not_found");
         g_lastId = id;
         return;
        }
      double curSl = PositionGetDouble(POSITION_SL);
      double curTp = PositionGetDouble(POSITION_TP);
      long type = PositionGetInteger(POSITION_TYPE);
      sl = NormalizePrice(symbol, sl);
      tp = (tp > 0.0) ? NormalizePrice(symbol, tp) : curTp;
      if(!SlIsImprovement(type, sl, curSl))
        {
         WriteResult(id, false, ticket, 0.0, sl, tp, "sl_would_loosen");
         g_lastId = id;
         return;
        }
      ok = trade.PositionModify(ticket, sl, tp);
      g_lastRetcode = (int)trade.ResultRetcode();
      g_lastError = ok ? "modified" : trade.ResultRetcodeDescription();
      WriteResult(id, ok, ticket, PositionGetDouble(POSITION_PRICE_OPEN), sl, tp, g_lastError);
     }
   else if(action == "CLOSE")
     {
      ticket = (ulong)JsonNumber(raw, "ticket");
      ok = trade.PositionClose(ticket);
      g_lastRetcode = (int)trade.ResultRetcode();
      g_lastError = ok ? "closed" : trade.ResultRetcodeDescription();
      ForgetRisk(ticket);
      WriteResult(id, ok, ticket, 0.0, 0.0, 0.0, g_lastError);
     }
   g_lastId = id;
  }

string BrokerBlockReason(const string symbol, const double lots, const double sl, const double tp, const string action)
  {
   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT) && !SymbolSelect(symbol, true))
      return "symbol_missing";
   long mode = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED)
      return "trading_disabled";
   long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && spread > InpMaxSpreadPoints)
      return "spread_too_wide";
   if(action != "BUY" && action != "SELL")
      return "";
   if(lots <= 0.0)
      return "invalid_lot";
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(lots + 1e-12 < vmin || lots - 1e-12 > vmax)
      return "lot_outside_broker_limits";
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0 || ask < bid)
      return "invalid_quote";
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int stops = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freeze = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double need = MathMax(stops, freeze) * point;
   if(action == "BUY")
     {
      if(sl <= 0.0 || tp <= 0.0)
         return "invalid_sl_tp";
      if(ask - sl < need)
         return "sl_too_close";
      if(tp - ask < need)
         return "tp_too_close";
      if(sl >= ask)
         return "invalid_sl";
     }
   else
     {
      if(sl <= 0.0 || tp <= 0.0)
         return "invalid_sl_tp";
      if(sl - bid < need)
         return "sl_too_close";
      if(bid - tp < need)
         return "tp_too_close";
      if(sl <= bid)
         return "invalid_sl";
     }
   double margin = 0.0;
   ENUM_ORDER_TYPE ot = (action == "BUY" ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   if(!OrderCalcMargin(ot, symbol, lots, (action == "BUY" ? ask : bid), margin))
      return "margin_calc_failed";
   if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
      return "insufficient_margin";
   return "";
  }

void LocalManageSymbol(const string symbol)
  {
   double beBuffer = InpBeBufferPoints * SymbolInfoDouble(symbol, SYMBOL_POINT);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      long type = PositionGetInteger(POSITION_TYPE);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double risk = TrackedRisk(ticket, MathAbs(entry - sl));
      if(risk <= 0.0)
         continue;

      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      int stops = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
      int freeze = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
      double need = MathMax(stops, freeze) * point;

      if(type == POSITION_TYPE_BUY)
        {
         double fav = bid - entry;
         double be = NormalizePrice(symbol, entry + beBuffer);
         if(fav >= g_beR * risk && SlIsImprovement(type, be, sl) && bid - be >= need)
            SafeModify(ticket, be, tp, "breakeven");
         sl = PositionGetDouble(POSITION_SL);
         if(g_trailOn && fav >= g_trailR * risk)
           {
            double trail = NormalizePrice(symbol, bid - g_trailLock * risk);
            if(SlIsImprovement(type, trail, sl) && bid - trail >= need)
               SafeModify(ticket, trail, tp, "trail");
           }
        }
      else
        {
         double fav = entry - ask;
         double be = NormalizePrice(symbol, entry - beBuffer);
         if(fav >= g_beR * risk && SlIsImprovement(type, be, sl) && be - ask >= need)
            SafeModify(ticket, be, tp, "breakeven");
         sl = PositionGetDouble(POSITION_SL);
         if(g_trailOn && fav >= g_trailR * risk)
           {
            double trail = NormalizePrice(symbol, ask + g_trailLock * risk);
            if(SlIsImprovement(type, trail, sl) && trail - ask >= need)
               SafeModify(ticket, trail, tp, "trail");
           }
        }
     }
  }

bool SlIsImprovement(const long type, const double newSl, const double curSl)
  {
   if(newSl <= 0.0)
      return false;
   if(curSl <= 0.0)
      return true;
   if(type == POSITION_TYPE_BUY)
      return (newSl > curSl + 1e-8);
   return (newSl < curSl - 1e-8);
  }

void SafeModify(const ulong ticket, const double sl, const double tp, const string why)
  {
   if(!trade.PositionModify(ticket, sl, tp))
     {
      g_lastRetcode = (int)trade.ResultRetcode();
      g_lastError = why + "_failed";
      return;
     }
   g_lastRetcode = (int)trade.ResultRetcode();
   g_lastError = why;
   g_lastTicket = ticket;
   Print("SL modify ", why, " ticket=", ticket, " sl=", sl, " tp=", tp);
  }

void RememberRisk(const ulong ticket, const double risk)
  {
   int n = ArraySize(g_trackTicket);
   ArrayResize(g_trackTicket, n + 1);
   ArrayResize(g_trackRisk, n + 1);
   g_trackTicket[n] = ticket;
   g_trackRisk[n] = risk;
  }

double TrackedRisk(const ulong ticket, const double fallback)
  {
   for(int i = 0; i < ArraySize(g_trackTicket); i++)
      if(g_trackTicket[i] == ticket && g_trackRisk[i] > 0.0)
         return g_trackRisk[i];
   RememberRisk(ticket, fallback);
   return fallback;
  }

void ForgetRisk(const ulong ticket)
  {
   int n = ArraySize(g_trackTicket);
   for(int i = 0; i < n; i++)
     {
      if(g_trackTicket[i] == ticket)
        {
         g_trackTicket[i] = g_trackTicket[n - 1];
         g_trackRisk[i] = g_trackRisk[n - 1];
         ArrayResize(g_trackTicket, n - 1);
         ArrayResize(g_trackRisk, n - 1);
         return;
        }
     }
  }

int CountOurPositions(const string symbol)
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      n++;
     }
   return n;
  }

double NormalizePrice(const string symbol, const double price)
  {
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
  }

double NormalizeVolume(const string symbol, double lots)
  {
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0)
      step = 0.01;
   lots = MathFloor(lots / step + 1e-8) * step;
   lots = MathMax(vmin, MathMin(vmax, lots));
   int digits = 2;
   if(step < 0.001 - 1e-12)
      digits = 4;
   else if(step < 0.01 - 1e-12)
      digits = 3;
   else if(step < 0.1 - 1e-12)
      digits = 2;
   else if(step < 1.0 - 1e-12)
      digits = 1;
   else
      digits = 0;
   return NormalizeDouble(lots, digits);
  }

void ClearSetup(TradeSetup &s)
  {
   s.valid = false;
   s.direction = DIR_NONE;
   s.sl = 0.0;
   s.tp = 0.0;
   s.confluence = 0;
   s.zone_kind = 0;
   s.eq_extra = false;
   s.why = "none";
   s.skill = 0;
   s.missing = "";
   s.pd = 0.5;
   s.er = 0.0;
  }

bool PriceInZone(const double bar_low, const double bar_high, const Zone &z)
  {
   return (bar_low <= z.high && bar_high >= z.low);
  }

bool IsRecentIndex(const int index, const int last, const int lookback)
  {
   int dist = last - index;
   return (dist >= 0 && dist <= lookback);
  }

ENUM_TIMEFRAMES BiasTfFor(const string symbol)
  {
   if(symbol == g_sym1)
      return InpBiasTf1;
   return InpBiasTf2;
  }

void ResetDayIfNeeded()
  {
   datetime day = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   if(day == g_dayStamp && g_dayStartEquity > 0.0)
      return;
   g_dayStamp = day;
   g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayTrades = 0;
  }

string DailyBlockReason()
  {
   if(InpMaxTradesPerDay > 0 && g_dayTrades >= InpMaxTradesPerDay)
      return "max_trades_today";
   if(g_dayStartEquity > 0.0 && InpMaxDailyLossPct > 0.0)
     {
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      double loss_pct = 100.0 * (g_dayStartEquity - equity) / g_dayStartEquity;
      if(loss_pct >= InpMaxDailyLossPct)
         return "daily_loss_cap";
     }
   return "";
  }

double CalcEr(const BarSet &bars, const int period)
  {
   if(bars.n < period + 1 || period <= 0)
      return 0.0;
   double net = MathAbs(bars.c[bars.n - 1] - bars.c[bars.n - 1 - period]);
   double path = 0.0;
   for(int i = bars.n - period; i < bars.n; i++)
      path += MathAbs(bars.c[i] - bars.c[i - 1]);
   if(path <= 1e-12)
      return 0.0;
   return net / path;
  }

double PdRatio(const BarSet &bars, const int lookback)
  {
   int last = bars.n - 1;
   if(last < 0)
      return 0.5;
   int start = last - lookback;
   if(start < 0)
      start = 0;
   double hh = MaxOf(bars.h, start, last + 1);
   double ll = MinOf(bars.l, start, last + 1);
   if(hh - ll <= 1e-12)
      return 0.5;
   return (bars.c[last] - ll) / (hh - ll);
  }

bool PdOk(const int direction, const double ratio)
  {
   if(direction == DIR_BULL)
      return (ratio <= InpPdBuyMax);
   if(direction == DIR_BEAR)
      return (ratio >= InpPdSellMin);
   return false;
  }

bool ChoChAfterSweep(const Event &events[], const Sweep &sweeps[],
                     const int bias, const int last, int &sweep_i, int &event_i)
  {
   sweep_i = -1;
   event_i = -1;
   for(int i = 0; i < ArraySize(sweeps); i++)
     {
      if(sweeps[i].direction != bias)
         continue;
      if(!IsRecentIndex(sweeps[i].index, last, InpRecentBars))
         continue;
      sweep_i = i;
     }
   if(sweep_i < 0)
      return false;
   for(int e = 0; e < ArraySize(events); e++)
     {
      if(events[e].direction != bias)
         continue;
      if(events[e].kind != KIND_CHOCH && events[e].kind != KIND_MSS)
         continue;
      if(events[e].index > sweeps[sweep_i].index &&
         IsRecentIndex(events[e].index, last, InpRecentBars))
        {
         event_i = e;
         return true;
        }
     }
   return false;
  }

int SkillScore(const bool has_sweep, const bool eq_extra, const bool choch_after,
               const bool displacement, const bool zone_tap, const bool pd_aligned,
               const bool htf_aligned, const bool trending, string &missing)
  {
   int score = 0;
   missing = "";
   if(has_sweep)
      score += 15;
   else
      missing += "sweep,";
   if(eq_extra)
      score += 10;
   else
      missing += "eq_extra,";
   if(choch_after)
      score += 20;
   else
      missing += "choch_after_sweep,";
   if(displacement)
      score += 10;
   else
      missing += "displacement,";
   if(zone_tap)
      score += 15;
   else
      missing += "ob_fvg_tap,";
   if(pd_aligned)
      score += 10;
   else
      missing += "premium_discount,";
   if(htf_aligned)
      score += 15;
   else
      missing += "htf_bias,";
   if(trending)
      score += 5;
   else
      missing += "chop,";
   int n = StringLen(missing);
   if(n > 0 && StringGetCharacter(missing, n - 1) == ',')
      missing = StringSubstr(missing, 0, n - 1);
   return score;
  }

double LotsByRisk(const string symbol, const double sl_distance)
  {
   if(sl_distance <= 0.0 || InpRiskPercent <= 0.0)
      return 0.0;
   double tick_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tick_size <= 0.0 || tick_value <= 0.0)
      return 0.0;
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * (InpRiskPercent / 100.0);
   double ticks = sl_distance / tick_size;
   if(ticks <= 0.0)
      return 0.0;
   double lots = risk_money / (ticks * tick_value);
   return NormalizeVolume(symbol, lots);
  }

void EvaluateSetup(const BarSet &bars, const int bias,
                   const Event &events[], const Sweep &sweeps[],
                   const Zone &fvgs[], const Zone &obs[],
                   const int htf_bias, TradeSetup &out)
  {
   ClearSetup(out);
   out.direction = bias;
   if(bars.n < 5 || bias == DIR_NONE)
     {
      out.why = "no_bias";
      return;
     }
   int last = bars.n - 1;
   int score = 1;
   string reasons = "bias";
   bool has_bos = false;
   bool has_rev = false;
   bool has_struct = false;
   for(int i = 0; i < ArraySize(events); i++)
     {
      if(events[i].direction != bias)
         continue;
      if(!IsRecentIndex(events[i].index, last, InpRecentBars))
         continue;
      has_struct = true;
      if(events[i].kind == KIND_BOS)
         has_bos = true;
      if(events[i].kind == KIND_CHOCH || events[i].kind == KIND_MSS)
         has_rev = true;
     }
   if(has_bos)
     {
      score++;
      reasons += "+BOS";
     }
   if(has_rev)
     {
      score++;
      reasons += "+CHoCH/MSS";
     }
   else if(has_struct && !has_bos)
     {
      score++;
      reasons += "+structure";
     }

   Sweep best_sweep;
   best_sweep.index = -1;
   best_sweep.direction = DIR_NONE;
   best_sweep.swept_price = 0.0;
   best_sweep.wick = 0.0;
   best_sweep.equal_extra = false;
   best_sweep.members = 0;
   bool have_sweep = false;
   for(int i = 0; i < ArraySize(sweeps); i++)
     {
      if(sweeps[i].direction != bias)
         continue;
      if(!IsRecentIndex(sweeps[i].index, last, InpRecentBars))
         continue;
      have_sweep = true;
      best_sweep = sweeps[i];
     }
   if(!have_sweep && InpRequireSweep)
     {
      out.confluence = score;
      out.why = "no_sweep";
      return;
     }
   if(have_sweep)
     {
      score++;
      reasons += "+sweep";
      if(best_sweep.equal_extra)
        {
         score++;
         reasons += "+eq_sweep_extra";
         out.eq_extra = true;
        }
     }

   int best_zone = -1;
   int best_kind = 0;
   double best_d = 1e100;
   double px = bars.c[last];
   for(int pass = 0; pass < 2; pass++)
     {
      int n = (pass == 0 ? ArraySize(fvgs) : ArraySize(obs));
      for(int i = 0; i < n; i++)
        {
         Zone z;
         if(pass == 0)
            z = fvgs[i];
         else
            z = obs[i];
         if(z.mitigated || z.direction != bias)
            continue;
         if(!PriceInZone(bars.l[last], bars.h[last], z))
            continue;
         double mid = 0.5 * (z.low + z.high);
         double d = MathMin(MathAbs(px - z.low), MathMin(MathAbs(px - z.high), MathAbs(px - mid)));
         if(d < best_d)
           {
            best_d = d;
            best_zone = i;
            best_kind = z.kind;
            out.zone_kind = z.kind;
           }
        }
     }
   if(best_zone < 0)
     {
      out.confluence = score;
      out.why = "no_zone_tap";
      return;
     }
   Zone zone;
   if(best_kind == ZONE_FVG)
      zone = fvgs[best_zone];
   else
      zone = obs[best_zone];
   score++;
   reasons += (zone.kind == ZONE_OB ? "+OB" : "+FVG");

   double buf = CalcAtr(bars, 14) * InpSlAtrMult;
   double sl = 0.0;
   double tp = 0.0;
   if(bias == DIR_BULL)
     {
      sl = zone.low;
      if(have_sweep)
         sl = MathMin(sl, best_sweep.wick);
      sl -= buf;
      double risk = px - sl;
      if(risk <= 0.0)
        {
         out.why = "bad_sl";
         return;
        }
      tp = px + InpRiskReward * risk;
     }
   else
     {
      sl = zone.high;
      if(have_sweep)
         sl = MathMax(sl, best_sweep.wick);
      sl += buf;
      double risk = sl - px;
      if(risk <= 0.0)
        {
         out.why = "bad_sl";
         return;
        }
      tp = px - InpRiskReward * risk;
     }
   out.confluence = score;
   out.sl = sl;
   out.tp = tp;

   int sweep_i = -1;
   int event_i = -1;
   bool seq_ok = ChoChAfterSweep(events, sweeps, bias, last, sweep_i, event_i);
   bool displace = false;
   if(seq_ok && event_i >= 0)
      displace = IsDisplacement(bars, events[event_i].index);
   out.pd = PdRatio(bars, InpRecentBars);
   bool pd_aligned = PdOk(bias, out.pd);
   out.er = CalcEr(bars, 20);
   bool trending = (out.er >= InpMinEfficiency);
   bool htf_ok = (htf_bias == bias);
   if(!InpRequireHtf)
      htf_ok = true;
   out.skill = SkillScore(have_sweep, out.eq_extra, seq_ok, displace, true,
                          pd_aligned, htf_ok, trending, out.missing);

   if(score < InpMinConfluence)
     {
      out.why = "confluence_" + IntegerToString(score);
      return;
     }
   if(InpProSkill)
     {
      if(InpRequireChoChSeq && !seq_ok)
        {
         out.why = "need_choch_after_sweep";
         return;
        }
      if(InpRequireDisplace && !displace)
        {
         out.why = "need_displacement";
         return;
        }
      if(InpRequirePd && !pd_aligned)
        {
         out.why = "need_premium_discount";
         return;
        }
      if(InpRequireHtf && !htf_ok)
        {
         out.why = "htf_mismatch";
         return;
        }
      if(!trending)
        {
         out.why = "chop";
         return;
        }
      if(out.skill < InpMinSkillScore)
        {
         out.why = "skill_" + IntegerToString(out.skill);
         return;
        }
     }
   out.valid = true;
   out.why = reasons + "+skill" + IntegerToString(out.skill);
  }

double LotFor(const string symbol, const int which)
  {
   double lots = (which == 1 ? InpLot1 : InpLot2);
   if(lots <= 0.0)
      lots = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   return NormalizeVolume(symbol, lots);
  }

bool InCooldown(const string symbol, const datetime closed_at)
  {
   if(closed_at <= 0)
      return false;
   int elapsed = (int)((TimeCurrent() - closed_at) / PeriodSeconds(TfFor(symbol)));
   return (elapsed < InpCooldownBars);
  }

void NotePositionLifecycle()
  {
   bool p1 = (g_sym1 != "" && CountOurPositions(g_sym1) > 0);
   bool p2 = (g_sym2 != "" && CountOurPositions(g_sym2) > 0);
   if(g_hadPos1 && !p1)
      g_closeTime1 = TimeCurrent();
   if(g_hadPos2 && !p2)
      g_closeTime2 = TimeCurrent();
   g_hadPos1 = p1;
   g_hadPos2 = p2;
  }

void ExecuteSetupTrade(const string symbol, const int which, const TradeSetup &setup)
  {
   if(symbol == "" || !setup.valid)
      return;
   if(CountOurPositions(symbol) >= 1)
      return;
   datetime closed_at = (which == 1 ? g_closeTime1 : g_closeTime2);
   if(InCooldown(symbol, closed_at))
     {
      g_lastError = "cooldown";
      return;
     }
   string action = (setup.direction == DIR_BULL ? "BUY" : "SELL");
   double price = (setup.direction == DIR_BULL)
                  ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                  : SymbolInfoDouble(symbol, SYMBOL_BID);
   double sl = setup.sl;
   double tp = setup.tp;
   if(setup.direction == DIR_BULL)
     {
      double risk = price - sl;
      if(risk <= 0.0)
         return;
      tp = price + InpRiskReward * risk;
     }
   else
     {
      double risk = sl - price;
      if(risk <= 0.0)
         return;
      tp = price - InpRiskReward * risk;
     }
   sl = NormalizePrice(symbol, sl);
   tp = NormalizePrice(symbol, tp);
   double lots = LotFor(symbol, which);
   if(InpRiskPercent > 0.0)
     {
      double risk_lots = LotsByRisk(symbol, MathAbs(price - sl));
      if(risk_lots > 0.0)
         lots = risk_lots;
     }
   string err = BrokerBlockReason(symbol, lots, sl, tp, action);
   if(err != "")
     {
      g_lastError = err;
      Print("Setup trade blocked ", symbol, " ", err);
      return;
     }
   trade.SetTypeFilling(DetectFilling(symbol));
   bool ok = false;
   if(setup.direction == DIR_BULL)
      ok = trade.Buy(lots, symbol, price, sl, tp, "SMC-SETUP");
   else
      ok = trade.Sell(lots, symbol, price, sl, tp, "SMC-SETUP");
   g_lastRetcode = (int)trade.ResultRetcode();
   ulong ticket = trade.ResultOrder();
   if(ok)
     {
      price = trade.ResultPrice();
      RememberRisk(ticket, MathAbs(price - sl));
      g_lastError = "picked_" + action;
      g_dayTrades++;
      Print("PICK ", action, " ", symbol, " lots=", lots, " sl=", sl, " tp=", tp,
            " why=", setup.why, " confluence=", setup.confluence, " skill=", setup.skill);
     }
   else
      g_lastError = trade.ResultRetcodeDescription();
   g_lastTicket = ticket;
  }

void MaybeAutoTrade()
  {
   if(!InpAutoTrade)
     {
      g_pickStatus = "auto trade off";
      return;
     }
   string day_block = DailyBlockReason();
   if(day_block != "")
     {
      g_pickStatus = day_block;
      return;
     }
   bool t1 = false;
   bool t2 = false;
   int direction = DIR_NONE;
   if(InpRequireBothPairs)
     {
      if(!g_setup1.valid && !g_setup2.valid)
         g_pickStatus = "waiting for setup on both pairs";
      else if(!g_setup1.valid)
         g_pickStatus = "waiting for Volatility 75 setup";
      else if(!g_setup2.valid)
         g_pickStatus = "waiting for Volatility 50 (1s) setup";
      else if(g_setup1.direction != g_setup2.direction)
         g_pickStatus = "pairs not aligned";
      else
        {
         t1 = true;
         t2 = true;
         direction = g_setup1.direction;
         int sk = g_setup1.skill;
         if(g_setup2.skill < sk)
            sk = g_setup2.skill;
         g_pickStatus = "PICK " + (direction == DIR_BULL ? "BUY" : "SELL") +
                        " on both pairs  SKILL " + IntegerToString(sk) + "/100";
        }
     }
   else
     {
      t1 = g_setup1.valid;
      t2 = g_setup2.valid;
      if(t1 && t2 && g_setup1.direction != g_setup2.direction)
        {
         t1 = false;
         t2 = false;
         g_pickStatus = "pairs not aligned";
        }
      else if(t1 || t2)
        {
         direction = (t1 ? g_setup1.direction : g_setup2.direction);
         g_pickStatus = "PICK " + (direction == DIR_BULL ? "BUY" : "SELL");
        }
      else
         g_pickStatus = "no setup";
     }
   if(t1)
      ExecuteSetupTrade(g_sym1, 1, g_setup1);
   if(t2)
      ExecuteSetupTrade(g_sym2, 2, g_setup2);
  }

void RefreshSmc(const bool force)
  {
   if(g_sym1 != "")
      RefreshSmcSymbol(g_sym1, 1, force);
   if(g_sym2 != "")
      RefreshSmcSymbol(g_sym2, 2, force);
  }

void RefreshSmcSymbol(const string symbol, const int which, const bool force)
  {
   ENUM_TIMEFRAMES tf = TfFor(symbol);
   datetime bar = iTime(symbol, tf, 0);
   bool is_new = true;
   if(!force)
     {
      if(which == 1 && bar == g_lastBar1)
         is_new = false;
      if(which == 2 && bar == g_lastBar2)
         is_new = false;
     }
   if(!is_new && !InpAutoTrade)
      return;
   if(is_new)
     {
      if(which == 1)
         g_lastBar1 = bar;
      else
         g_lastBar2 = bar;
     }

   BarSet bars;
   if(!LoadBars(symbol, tf, bars))
     {
      if(which == 1)
        {
         ClearSetup(g_setup1);
         g_chat1 = symbol + "  waiting for bars";
         g_smcJson1 = "\"symbol\":\"" + JsonEsc(symbol) + "\",\"bias\":\"flat\"";
        }
      else
        {
         ClearSetup(g_setup2);
         g_chat2 = symbol + "  waiting for bars";
         g_smcJson2 = "\"symbol\":\"" + JsonEsc(symbol) + "\",\"bias\":\"flat\"";
        }
      return;
     }

   Event events[];
   Sweep sweeps[];
   Zone fvgs[];
   Zone obs[];
   Pool equals[];
   DetectStructure(bars, events);
   DetectSweepsAndEquals(bars, sweeps, equals);
   DetectFvg(bars, fvgs);
   DetectOrderBlocks(bars, events, obs);
   int bias = InferBias(bars, events);
   int htf_bias = DIR_NONE;
   BarSet htf;
   if(LoadBars(symbol, BiasTfFor(symbol), htf))
     {
      Event he[];
      DetectStructure(htf, he);
      htf_bias = InferBias(htf, he);
     }
   TradeSetup setup;
   EvaluateSetup(bars, bias, events, sweeps, fvgs, obs, htf_bias, setup);

   string chat = BuildChat(symbol, bars, bias, events, sweeps, fvgs, obs);
   chat += "  SETUP: " + (setup.valid ? ("YES " + DirName(setup.direction) + " " + setup.why)
                                     : ("no (" + setup.why + ")")) + "\n";
   chat += "  SKILL: " + IntegerToString(setup.skill) + "/100 " +
           (setup.valid ? "PASS" : "WAIT") + "  missing " +
           (setup.missing != "" ? setup.missing : "none") + "\n";
   chat += "  HTF " + DirName(htf_bias) + "  PD " + DoubleToString(setup.pd, 2) +
           "  ER " + DoubleToString(setup.er, 2) + "\n";
   string js = BuildSmcJson(symbol, bars, bias, events, sweeps, fvgs, obs);
   js += StringFormat(",\"setup\":%s,\"setup_dir\":\"%s\",\"setup_why\":\"%s\",\"confluence\":%d",
                      (setup.valid ? "true" : "false"), DirName(setup.direction),
                      setup.why, setup.confluence);
   if(which == 1)
     {
      g_setup1 = setup;
      g_chat1 = chat;
      g_smcJson1 = js;
      if(is_new)
         MaybeLogNew(symbol, events, sweeps, g_loggedEvt1, g_loggedSwp1);
     }
   else
     {
      g_setup2 = setup;
      g_chat2 = chat;
      g_smcJson2 = js;
      if(is_new)
         MaybeLogNew(symbol, events, sweeps, g_loggedEvt2, g_loggedSwp2);
     }

   if((is_new || force) && InpDrawSmcObjects && symbol == _Symbol)
      DrawSmc(_Symbol, bars, events, sweeps, fvgs, obs, equals);
  }

bool LoadBars(const string symbol, const ENUM_TIMEFRAMES tf, BarSet &bars)
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int n = CopyRates(symbol, tf, 0, InpLookback, rates);
   if(n < 30)
      return false;
   bars.n = n;
   ArrayResize(bars.t, n);
   ArrayResize(bars.o, n);
   ArrayResize(bars.h, n);
   ArrayResize(bars.l, n);
   ArrayResize(bars.c, n);
   for(int i = 0; i < n; i++)
     {
      bars.t[i] = rates[i].time;
      bars.o[i] = rates[i].open;
      bars.h[i] = rates[i].high;
      bars.l[i] = rates[i].low;
      bars.c[i] = rates[i].close;
     }
   return true;
  }

double MaxOf(const double &a[], const int from, const int to_exclusive)
  {
   double m = a[from];
   for(int i = from + 1; i < to_exclusive; i++)
      if(a[i] > m)
         m = a[i];
   return m;
  }

double MinOf(const double &a[], const int from, const int to_exclusive)
  {
   double m = a[from];
   for(int i = from + 1; i < to_exclusive; i++)
      if(a[i] < m)
         m = a[i];
   return m;
  }

int DetectSwings(const BarSet &bars, Swing &swings[])
  {
   ArrayResize(swings, 0);
   int n = bars.n;
   int left = InpSwingLeft;
   int right = InpSwingRight;
   if(n < left + right + 1)
      return 0;
   for(int i = left; i < n - right; i++)
     {
      if(bars.h[i] > MaxOf(bars.h, i - left, i) && bars.h[i] >= MaxOf(bars.h, i + 1, i + right + 1))
         PushSwing(swings, i, bars.h[i], SWING_HIGH);
      if(bars.l[i] < MinOf(bars.l, i - left, i) && bars.l[i] <= MinOf(bars.l, i + 1, i + right + 1))
         PushSwing(swings, i, bars.l[i], SWING_LOW);
     }
   return ArraySize(swings);
  }

void PushSwing(Swing &swings[], const int index, const double price, const int kind)
  {
   int k = ArraySize(swings);
   ArrayResize(swings, k + 1);
   swings[k].index = index;
   swings[k].price = price;
   swings[k].kind = kind;
  }

double CalcAtr(const BarSet &bars, const int period)
  {
   if(bars.n < 2)
      return 0.0;
   double sum = 0.0;
   int count = 0;
   int start = MathMax(1, bars.n - period);
   for(int i = start; i < bars.n; i++)
     {
      double tr = MathMax(bars.h[i] - bars.l[i],
                          MathMax(MathAbs(bars.h[i] - bars.c[i - 1]), MathAbs(bars.l[i] - bars.c[i - 1])));
      sum += tr;
      count++;
     }
   if(count <= 0)
      return 0.0;
   return sum / count;
  }

bool IsDisplacement(const BarSet &bars, const int index)
  {
   double sum = 0.0;
   int count = 0;
   int start = MathMax(0, index - 10);
   for(int i = start; i < index; i++)
     {
      sum += MathAbs(bars.c[i] - bars.o[i]);
      count++;
     }
   if(count <= 0)
      return true;
   double avg = sum / count;
   return (avg <= 0.0 || MathAbs(bars.c[index] - bars.o[index]) >= avg * 1.5);
  }

void DetectStructure(const BarSet &bars, Event &events[])
  {
   ArrayResize(events, 0);
   Swing swings[];
   DetectSwings(bars, swings);
   int n = bars.n;
   int last_high_i = -1;
   int last_low_i = -1;
   double last_high_p = 0.0;
   double last_low_p = 0.0;
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
   int right = InpSwingRight;

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
         if(bars.c[i] > last_high_p)
           {
            int kind = (trend == DIR_NONE || trend == DIR_BULL) ? KIND_BOS : KIND_CHOCH;
            PushEvent(events, i, kind, DIR_BULL, last_high_p);
            if(kind == KIND_CHOCH && IsDisplacement(bars, i))
               PushEvent(events, i, KIND_MSS, DIR_BULL, last_high_p);
            trend = DIR_BULL;
            used_high[last_high_i] = true;
           }
        }
      if(last_low_i >= 0 && !used_low[last_low_i] && last_low_i < i)
        {
         if(bars.c[i] < last_low_p)
           {
            int kind = (trend == DIR_NONE || trend == DIR_BEAR) ? KIND_BOS : KIND_CHOCH;
            PushEvent(events, i, kind, DIR_BEAR, last_low_p);
            if(kind == KIND_CHOCH && IsDisplacement(bars, i))
               PushEvent(events, i, KIND_MSS, DIR_BEAR, last_low_p);
            trend = DIR_BEAR;
            used_low[last_low_i] = true;
           }
        }
     }
  }

void PushEvent(Event &events[], const int index, const int kind, const int direction, const double broken)
  {
   int k = ArraySize(events);
   ArrayResize(events, k + 1);
   events[k].index = index;
   events[k].kind = kind;
   events[k].direction = direction;
   events[k].broken = broken;
  }

void BuildEqualPools(const BarSet &bars, const Swing &swings[], Pool &pools[])
  {
   ArrayResize(pools, 0);
   double tolerance = InpEqualAtrMult * CalcAtr(bars, 14);
   int kinds[2];
   kinds[0] = SWING_HIGH;
   kinds[1] = SWING_LOW;
   int sc = ArraySize(swings);
   for(int kk = 0; kk < 2; kk++)
     {
      int kind = kinds[kk];
      int idx[];
      ArrayResize(idx, 0);
      for(int s = 0; s < sc; s++)
         if(swings[s].kind == kind)
           {
            int n = ArraySize(idx);
            ArrayResize(idx, n + 1);
            idx[n] = s;
           }
      int m = ArraySize(idx);
      bool used[];
      ArrayResize(used, m);
      for(int u = 0; u < m; u++)
         used[u] = false;
      for(int i = 0; i < m; i++)
        {
         if(used[i])
            continue;
         double sum = swings[idx[i]].price;
         int members = 1;
         int last_index = swings[idx[i]].index;
         used[i] = true;
         for(int j = i + 1; j < m; j++)
           {
            if(used[j])
               continue;
            if(MathAbs(swings[idx[j]].price - swings[idx[i]].price) <= tolerance)
              {
               sum += swings[idx[j]].price;
               members++;
               if(swings[idx[j]].index > last_index)
                  last_index = swings[idx[j]].index;
               used[j] = true;
              }
           }
         int p = ArraySize(pools);
         ArrayResize(pools, p + 1);
         pools[p].kind = kind;
         pools[p].price = sum / members;
         pools[p].index = last_index;
         pools[p].equal = (members >= 2);
         pools[p].members = members;
        }
     }
  }

void DetectSweepsAndEquals(const BarSet &bars, Sweep &sweeps[], Pool &equals[])
  {
   ArrayResize(sweeps, 0);
   ArrayResize(equals, 0);
   Swing swings[];
   DetectSwings(bars, swings);
   Pool pools[];
   BuildEqualPools(bars, swings, pools);
   for(int p = 0; p < ArraySize(pools); p++)
      if(pools[p].equal)
        {
         int k = ArraySize(equals);
         ArrayResize(equals, k + 1);
         equals[k] = pools[p];
        }

   for(int i = 0; i < bars.n; i++)
     {
      bool have = false;
      Sweep best;
      best.index = i;
      best.direction = DIR_NONE;
      best.swept_price = 0.0;
      best.wick = 0.0;
      best.equal_extra = false;
      best.members = 1;
      for(int p = 0; p < ArraySize(pools); p++)
        {
         if(pools[p].index >= i)
            continue;
         bool hit = false;
         int direction = DIR_NONE;
         double wick = 0.0;
         if(pools[p].kind == SWING_LOW && bars.l[i] < pools[p].price && bars.c[i] > pools[p].price)
           {
            hit = true;
            direction = DIR_BULL;
            wick = bars.l[i];
           }
         else if(pools[p].kind == SWING_HIGH && bars.h[i] > pools[p].price && bars.c[i] < pools[p].price)
           {
            hit = true;
            direction = DIR_BEAR;
            wick = bars.h[i];
           }
         if(!hit)
            continue;
         Sweep cand;
         cand.index = i;
         cand.direction = direction;
         cand.swept_price = pools[p].price;
         cand.wick = wick;
         cand.equal_extra = (pools[p].equal && pools[p].members >= 2);
         cand.members = pools[p].members;
         if(!have)
           {
            best = cand;
            have = true;
           }
         else if(cand.equal_extra && !best.equal_extra)
            best = cand;
         else if(MathAbs(cand.wick - cand.swept_price) > MathAbs(best.wick - best.swept_price))
            best = cand;
        }
      if(have)
        {
         int k = ArraySize(sweeps);
         ArrayResize(sweeps, k + 1);
         sweeps[k] = best;
        }
     }
  }

void DetectFvg(const BarSet &bars, Zone &zones[])
  {
   ArrayResize(zones, 0);
   int n = bars.n;
   if(n < 3)
      return;
   for(int i = 1; i < n - 1; i++)
     {
      if(bars.l[i + 1] > bars.h[i - 1])
        {
         Zone z;
         z.start_index = i - 1;
         z.end_index = i + 1;
         z.low = bars.h[i - 1];
         z.high = bars.l[i + 1];
         z.direction = DIR_BULL;
         z.kind = ZONE_FVG;
         z.mitigated = MitigatedAfter(bars.c, n, i + 2, z.low, DIR_BULL);
         PushZone(zones, z);
        }
      else if(bars.h[i + 1] < bars.l[i - 1])
        {
         Zone z;
         z.start_index = i - 1;
         z.end_index = i + 1;
         z.low = bars.h[i + 1];
         z.high = bars.l[i - 1];
         z.direction = DIR_BEAR;
         z.kind = ZONE_FVG;
         z.mitigated = MitigatedAfter(bars.c, n, i + 2, z.high, DIR_BEAR);
         PushZone(zones, z);
        }
     }
  }

bool MitigatedAfter(const double &close[], const int n, const int start, const double level, const int direction)
  {
   if(start >= n)
      return false;
   for(int i = start; i < n; i++)
     {
      if(direction == DIR_BULL && close[i] < level)
         return true;
      if(direction == DIR_BEAR && close[i] > level)
         return true;
     }
   return false;
  }

void PushZone(Zone &zones[], const Zone &z)
  {
   int k = ArraySize(zones);
   ArrayResize(zones, k + 1);
   zones[k] = z;
  }

void DetectOrderBlocks(const BarSet &bars, const Event &events[], Zone &zones[])
  {
   ArrayResize(zones, 0);
   int n = bars.n;
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
            if(bars.c[i] < bars.o[i])
              {
               ob = i;
               break;
              }
        }
      else
        {
         for(int i = events[e].index - 1; i >= start; i--)
            if(bars.c[i] > bars.o[i])
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
      z.low = bars.l[ob];
      z.high = bars.h[ob];
      z.direction = events[e].direction;
      z.kind = ZONE_OB;
      z.mitigated = false;
      if(ob + 1 < n)
        {
         if(events[e].direction == DIR_BULL)
            z.mitigated = MitigatedAfter(bars.c, n, ob + 1, z.low, DIR_BULL);
         else
            z.mitigated = MitigatedAfter(bars.c, n, ob + 1, z.high, DIR_BEAR);
        }
      PushZone(zones, z);
     }
  }

int InferBias(const BarSet &bars, const Event &events[])
  {
   int ec = ArraySize(events);
   if(ec > 0)
      return events[ec - 1].direction;
   int lookback = 10;
   int n = bars.n;
   if(n < lookback + 1)
      return DIR_NONE;
   int last = n - 1;
   int prev = n - lookback - 1;
   if(bars.h[last] > bars.h[prev] && bars.l[last] >= bars.l[prev])
      return DIR_BULL;
   if(bars.l[last] < bars.l[prev] && bars.h[last] <= bars.h[prev])
      return DIR_BEAR;
   if(bars.c[last] > bars.c[prev])
      return DIR_BULL;
   if(bars.c[last] < bars.c[prev])
      return DIR_BEAR;
   return DIR_NONE;
  }

string DirName(const int direction)
  {
   if(direction == DIR_BULL)
      return "BULL";
   if(direction == DIR_BEAR)
      return "BEAR";
   return "FLAT";
  }

string KindName(const int kind)
  {
   if(kind == KIND_BOS)
      return "BOS";
   if(kind == KIND_CHOCH)
      return "CHoCH";
   if(kind == KIND_MSS)
      return "MSS";
   return "?";
  }

int LastEventOf(const Event &events[], const int kind)
  {
   for(int i = ArraySize(events) - 1; i >= 0; i--)
      if(events[i].kind == kind)
         return i;
   return -1;
  }

int LastSweepOf(const Sweep &sweeps[], const bool equal_only)
  {
   for(int i = ArraySize(sweeps) - 1; i >= 0; i--)
     {
      if(equal_only && !sweeps[i].equal_extra)
         continue;
      return i;
     }
   return -1;
  }

int LastLiveZone(const Zone &zones[])
  {
   for(int i = ArraySize(zones) - 1; i >= 0; i--)
      if(!zones[i].mitigated)
         return i;
   return -1;
  }

string FmtTime(const BarSet &bars, const int index)
  {
   if(index < 0 || index >= bars.n)
      return "-";
   return TimeToString(bars.t[index], TIME_DATE|TIME_MINUTES);
  }

string BuildChat(const string symbol, const BarSet &bars, const int bias,
                 const Event &events[], const Sweep &sweeps[],
                 const Zone &fvgs[], const Zone &obs[])
  {
   string txt = symbol + "  bias " + DirName(bias) + "\n";
   int kinds[3];
   kinds[0] = KIND_BOS;
   kinds[1] = KIND_CHOCH;
   kinds[2] = KIND_MSS;
   for(int k = 0; k < 3; k++)
     {
      int i = LastEventOf(events, kinds[k]);
      if(i < 0)
         txt += "  " + KindName(kinds[k]) + ": none\n";
      else
         txt += "  " + KindName(kinds[k]) + ": " + DirName(events[i].direction) +
                " " + FmtTime(bars, events[i].index) + "\n";
     }
   int sw = LastSweepOf(sweeps, false);
   if(sw < 0)
      txt += "  Liquidity sweep: none\n";
   else
     {
      string side = (sweeps[sw].direction == DIR_BULL ? "SSL" : "BSL");
      txt += "  Liquidity sweep: " + side + " " + DirName(sweeps[sw].direction) +
             " " + FmtTime(bars, sweeps[sw].index) + "\n";
     }
   int eq = LastSweepOf(sweeps, true);
   if(eq < 0)
      txt += "  Equal-liquidity sweep extra: none\n";
   else
      txt += "  Equal-liquidity sweep extra: " + DirName(sweeps[eq].direction) +
             " (" + IntegerToString(sweeps[eq].members) + " equals) " +
             FmtTime(bars, sweeps[eq].index) + "\n";
   int ob = LastLiveZone(obs);
   if(ob < 0)
      txt += "  Order Block: none\n";
   else
      txt += "  Order Block: " + DirName(obs[ob].direction) + " " +
             DoubleToString(obs[ob].low, 2) + "-" + DoubleToString(obs[ob].high, 2) + "\n";
   int fvg = LastLiveZone(fvgs);
   if(fvg < 0)
      txt += "  FVG: none\n";
   else
      txt += "  FVG: " + DirName(fvgs[fvg].direction) + " " +
             DoubleToString(fvgs[fvg].low, 2) + "-" + DoubleToString(fvgs[fvg].high, 2) + "\n";
   return txt;
  }

string BuildSmcJson(const string symbol, const BarSet &bars, const int bias,
                    const Event &events[], const Sweep &sweeps[],
                    const Zone &fvgs[], const Zone &obs[])
  {
   string bos = "", choch = "", mss = "", sweep = "", eq = "", ob = "", fvg = "";
   int i = LastEventOf(events, KIND_BOS);
   if(i >= 0)
      bos = DirName(events[i].direction) + " " + FmtTime(bars, events[i].index);
   i = LastEventOf(events, KIND_CHOCH);
   if(i >= 0)
      choch = DirName(events[i].direction) + " " + FmtTime(bars, events[i].index);
   i = LastEventOf(events, KIND_MSS);
   if(i >= 0)
      mss = DirName(events[i].direction) + " " + FmtTime(bars, events[i].index);
   i = LastSweepOf(sweeps, false);
   if(i >= 0)
      sweep = (sweeps[i].direction == DIR_BULL ? "SSL " : "BSL ") + DirName(sweeps[i].direction);
   i = LastSweepOf(sweeps, true);
   if(i >= 0)
      eq = "extra " + DirName(sweeps[i].direction) + " " + IntegerToString(sweeps[i].members);
   i = LastLiveZone(obs);
   if(i >= 0)
      ob = DirName(obs[i].direction);
   i = LastLiveZone(fvgs);
   if(i >= 0)
      fvg = DirName(fvgs[i].direction);
   return StringFormat(
      "\"symbol\":\"%s\",\"bias\":\"%s\",\"bos\":\"%s\",\"choch\":\"%s\",\"mss\":\"%s\",\"sweep\":\"%s\",\"eq_sweep\":\"%s\",\"ob\":\"%s\",\"fvg\":\"%s\"",
      JsonEsc(symbol), DirName(bias), bos, choch, mss, sweep, eq, ob, fvg);
  }

void MaybeLogNew(const string symbol, const Event &events[], const Sweep &sweeps[],
                 int &last_evt, int &last_swp)
  {
   if(!InpLogSmcEvents)
      return;
   int ec = ArraySize(events);
   if(ec > 0 && events[ec - 1].index != last_evt)
     {
      last_evt = events[ec - 1].index;
      Print("SMC ", symbol, " ", KindName(events[ec - 1].kind), " ",
            DirName(events[ec - 1].direction), " broken=", events[ec - 1].broken);
     }
   int sc = ArraySize(sweeps);
   if(sc > 0 && sweeps[sc - 1].index != last_swp)
     {
      last_swp = sweeps[sc - 1].index;
      string tag = sweeps[sc - 1].equal_extra ? "Equal-liquidity sweep extra" : "Liquidity sweep";
      Print("SMC ", symbol, " ", tag, " ", DirName(sweeps[sc - 1].direction),
            " members=", sweeps[sc - 1].members);
     }
  }

void UpdateChat()
  {
   if(!InpShowSmcChat)
     {
      Comment("");
      return;
     }
   string py = PythonFresh() ? "FRESH" : "LOST";
   string pos = IntegerToString(CountOurPositions(g_sym1) + CountOurPositions(g_sym2));
   string txt = "Python ML SMC Bridge  3.04  PRO SKILL " + IntegerToString(InpMinSkillScore) + "+\n";
   txt += "Symbols: " + (g_sym1 != "" ? g_sym1 : "-") + "  |  " + (g_sym2 != "" ? g_sym2 : "-") + "\n";
   txt += "Python: " + py + "   positions: " + pos + "   last: " + g_lastError + "\n";
   txt += "TRADE: " + g_pickStatus + "\n";
   txt += "Day trades: " + IntegerToString(g_dayTrades) + "/" + IntegerToString(InpMaxTradesPerDay) +
          "  risk " + DoubleToString(InpRiskPercent, 2) + "%\n";
   txt += "--------------------------------\n";
   txt += (g_chat1 != "" ? g_chat1 : "V75: waiting\n");
   txt += "--------------------------------\n";
   txt += (g_chat2 != "" ? g_chat2 : "V50 (1s): waiting\n");
   txt += "A+ checklist: HTF bias | premium/discount | sweep then CHoCH/MSS | displacement | OB/FVG | not chop\n";
   txt += "Picks only when BOTH pairs print skill " + IntegerToString(InpMinSkillScore) + "+ in the same direction.";
   Comment(txt);
  }

color EventColor(const int kind, const int direction)
  {
   if(kind == KIND_MSS)
      return (direction == DIR_BULL ? clrAqua : clrMagenta);
   if(kind == KIND_CHOCH)
      return clrGold;
   return (direction == DIR_BULL ? clrLime : clrOrangeRed);
  }

void DrawSmc(const string symbol,
             const BarSet &bars,
             const Event &events[],
             const Sweep &sweeps[],
             const Zone &fvgs[],
             const Zone &obs[],
             const Pool &equals[])
  {
   ObjectsDeleteAll(0, OBJ_PREFIX);
   datetime now = TimeCurrent();
   int pad = PeriodSeconds(TfFor(symbol)) * 8;

   int drawn = 0;
   for(int i = ArraySize(equals) - 1; i >= 0 && drawn < 8; i--)
     {
      string id = OBJ_PREFIX + "EQ" + IntegerToString(i);
      color clr = clrGold;
      if(ObjectCreate(0, id, OBJ_HLINE, 0, 0, equals[i].price))
        {
         ObjectSetInteger(0, id, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, id, OBJPROP_STYLE, STYLE_DASH);
         ObjectSetInteger(0, id, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, id, OBJPROP_BACK, true);
         ObjectSetInteger(0, id, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, id, OBJPROP_HIDDEN, true);
        }
      string lab = OBJ_PREFIX + "EQL" + IntegerToString(i);
      string caption = (equals[i].kind == SWING_HIGH ? "EQH extra x" : "EQL extra x") +
                       IntegerToString(equals[i].members);
      if(ObjectCreate(0, lab, OBJ_TEXT, 0, now, equals[i].price))
        {
         ObjectSetString(0, lab, OBJPROP_TEXT, caption);
         ObjectSetInteger(0, lab, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, lab, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, lab, OBJPROP_SELECTABLE, false);
        }
      drawn++;
     }

   drawn = 0;
   for(int i = ArraySize(fvgs) - 1; i >= 0 && drawn < InpDrawMaxFvg; i--)
     {
      if(fvgs[i].mitigated)
         continue;
      string id = OBJ_PREFIX + "FVG" + IntegerToString(i);
      datetime t1 = bars.t[fvgs[i].start_index];
      datetime t2 = now + pad;
      color clr = (fvgs[i].direction == DIR_BULL ? C'20,140,90' : C'160,40,70');
      if(ObjectCreate(0, id, OBJ_RECTANGLE, 0, t1, fvgs[i].high, t2, fvgs[i].low))
        {
         ObjectSetInteger(0, id, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, id, OBJPROP_STYLE, STYLE_SOLID);
         ObjectSetInteger(0, id, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, id, OBJPROP_FILL, true);
         ObjectSetInteger(0, id, OBJPROP_BACK, true);
         ObjectSetInteger(0, id, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, id, OBJPROP_HIDDEN, true);
        }
      string lab = OBJ_PREFIX + "FVGL" + IntegerToString(i);
      if(ObjectCreate(0, lab, OBJ_TEXT, 0, t1, fvgs[i].high))
        {
         ObjectSetString(0, lab, OBJPROP_TEXT, (fvgs[i].direction == DIR_BULL ? "FVG BULL" : "FVG BEAR"));
         ObjectSetInteger(0, lab, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, lab, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, lab, OBJPROP_SELECTABLE, false);
        }
      drawn++;
     }

   drawn = 0;
   for(int i = ArraySize(obs) - 1; i >= 0 && drawn < InpDrawMaxOb; i--)
     {
      if(obs[i].mitigated)
         continue;
      string id = OBJ_PREFIX + "OB" + IntegerToString(i);
      datetime t1 = bars.t[obs[i].start_index];
      datetime t2 = now + pad;
      color clr = (obs[i].direction == DIR_BULL ? C'30,90,170' : C'150,50,90');
      if(ObjectCreate(0, id, OBJ_RECTANGLE, 0, t1, obs[i].high, t2, obs[i].low))
        {
         ObjectSetInteger(0, id, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, id, OBJPROP_STYLE, STYLE_SOLID);
         ObjectSetInteger(0, id, OBJPROP_WIDTH, 2);
         ObjectSetInteger(0, id, OBJPROP_FILL, true);
         ObjectSetInteger(0, id, OBJPROP_BACK, true);
         ObjectSetInteger(0, id, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, id, OBJPROP_HIDDEN, true);
        }
      string lab = OBJ_PREFIX + "OBL" + IntegerToString(i);
      if(ObjectCreate(0, lab, OBJ_TEXT, 0, t1, obs[i].high))
        {
         ObjectSetString(0, lab, OBJPROP_TEXT,
                         (obs[i].direction == DIR_BULL ? "Order Block BULL" : "Order Block BEAR"));
         ObjectSetInteger(0, lab, OBJPROP_COLOR, clrWhite);
         ObjectSetInteger(0, lab, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, lab, OBJPROP_SELECTABLE, false);
        }
      drawn++;
     }

   drawn = 0;
   for(int i = ArraySize(events) - 1; i >= 0 && drawn < InpDrawMaxEvents; i--)
     {
      datetime t = bars.t[events[i].index];
      double px = events[i].broken;
      color clr = EventColor(events[i].kind, events[i].direction);
      string lab = OBJ_PREFIX + "EV" + IntegerToString(i);
      string txt = KindName(events[i].kind) + (events[i].direction == DIR_BULL ? " BULL" : " BEAR");
      if(ObjectCreate(0, lab, OBJ_TEXT, 0, t, px))
        {
         ObjectSetString(0, lab, OBJPROP_TEXT, txt);
         ObjectSetInteger(0, lab, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, lab, OBJPROP_FONTSIZE, 9);
         ObjectSetInteger(0, lab, OBJPROP_ANCHOR,
                          events[i].direction == DIR_BULL ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
         ObjectSetInteger(0, lab, OBJPROP_SELECTABLE, false);
        }
      string ar = OBJ_PREFIX + "EA" + IntegerToString(i);
      if(ObjectCreate(0, ar, OBJ_ARROW, 0, t, px))
        {
         ObjectSetInteger(0, ar, OBJPROP_ARROWCODE, events[i].direction == DIR_BULL ? 233 : 234);
         ObjectSetInteger(0, ar, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, ar, OBJPROP_WIDTH, 2);
         ObjectSetInteger(0, ar, OBJPROP_SELECTABLE, false);
        }
      drawn++;
     }

   drawn = 0;
   for(int i = ArraySize(sweeps) - 1; i >= 0 && drawn < InpDrawMaxSweeps; i--)
     {
      datetime t = bars.t[sweeps[i].index];
      double px = sweeps[i].wick;
      color clr = sweeps[i].equal_extra ? clrGold : clrOrange;
      string txt = sweeps[i].equal_extra ? "EQ SWEEP EXTRA" : "LIQUIDITY SWEEP";
      txt += (sweeps[i].direction == DIR_BULL ? " SSL" : " BSL");
      string lab = OBJ_PREFIX + "SW" + IntegerToString(i);
      if(ObjectCreate(0, lab, OBJ_TEXT, 0, t, px))
        {
         ObjectSetString(0, lab, OBJPROP_TEXT, txt);
         ObjectSetInteger(0, lab, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, lab, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, lab, OBJPROP_SELECTABLE, false);
        }
      string ln = OBJ_PREFIX + "SL" + IntegerToString(i);
      if(ObjectCreate(0, ln, OBJ_TREND, 0, t, sweeps[i].swept_price, t, sweeps[i].wick))
        {
         ObjectSetInteger(0, ln, OBJPROP_COLOR, clr);
         ObjectSetInteger(0, ln, OBJPROP_WIDTH, sweeps[i].equal_extra ? 3 : 2);
         ObjectSetInteger(0, ln, OBJPROP_RAY_RIGHT, false);
         ObjectSetInteger(0, ln, OBJPROP_SELECTABLE, false);
        }
      drawn++;
     }
   ChartRedraw(0);
  }

void WriteResult(const string id, const bool ok, const ulong ticket,
                 const double price, const double sl, const double tp, const string msg)
  {
   g_lastTicket = ticket;
   g_lastError = msg;
   g_lastResultJson = StringFormat(
      "\"last_result\":{\"id\":\"%s\",\"ok\":%s,\"ticket\":%I64u,\"price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"retcode\":%d,\"error\":\"%s\"},",
      id, (ok ? "true" : "false"), ticket, price, sl, tp, g_lastRetcode, msg);
   WriteStatusRaw(g_lastResultJson);
  }

void WriteStatus(const string phase, const int code, const string msg)
  {
   string extra = StringFormat("\"phase\":\"%s\",\"code\":%d,\"message\":\"%s\",%s",
                              phase, code, msg, g_lastResultJson);
   WriteStatusRaw(extra);
  }

string PosJson(const string symbol)
  {
   int npos = CountOurPositions(symbol);
   double posSl = 0.0, posTp = 0.0, posPnl = 0.0, bid = 0.0, ask = 0.0;
   ulong posTicket = 0;
   long spread = 0;
   if(symbol != "")
     {
      bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol)
            continue;
         if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
            continue;
         posTicket = ticket;
         posSl = PositionGetDouble(POSITION_SL);
         posTp = PositionGetDouble(POSITION_TP);
         posPnl = PositionGetDouble(POSITION_PROFIT);
         break;
        }
     }
   return StringFormat(
      "\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread\":%d,\"positions\":%d,\"ticket\":%I64u,\"sl\":%.5f,\"tp\":%.5f,\"profit\":%.2f",
      JsonEsc(symbol), bid, ask, (int)spread, npos, posTicket, posSl, posTp, posPnl);
  }

void WriteStatusRaw(const string extra)
  {
   string python_ok = PythonFresh() ? "true" : "false";
   string trail_ok = g_trailOn ? "true" : "false";
   string smc1 = (g_smcJson1 != "" ? g_smcJson1 : "\"symbol\":\"\",\"bias\":\"FLAT\"");
   string smc2 = (g_smcJson2 != "" ? g_smcJson2 : "\"symbol\":\"\",\"bias\":\"FLAT\"");
   string json = StringFormat(
      "{%s\"connected\":true,\"python_fresh\":%s,\"trail_on\":%s,\"pick\":\"%s\",\"v75\":{%s},\"v50_1s\":{%s},\"smc_v75\":{%s},\"smc_v50_1s\":{%s},\"last_command_id\":\"%s\",\"retcode\":%d,\"error\":\"%s\",\"time\":\"%s\"}",
      extra, python_ok, trail_ok, g_pickStatus, PosJson(g_sym1), PosJson(g_sym2), smc1, smc2,
      g_lastId, g_lastRetcode, g_lastError, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   AtomicWrite(InpFolder + "\\status.json", json);
  }

void AtomicWrite(const string path, const string body)
  {
   string tmp = path + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, body);
   FileClose(h);
   FileDelete(path, FILE_COMMON);
   FileMove(tmp, FILE_COMMON, path, FILE_COMMON);
  }

string JsonEsc(const string s)
  {
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return out;
  }

string JsonString(const string raw, const string key)
  {
   string token = "\"" + key + "\"";
   int p = StringFind(raw, token);
   if(p < 0)
      return "";
   int colon = StringFind(raw, ":", p);
   int q1 = StringFind(raw, "\"", colon + 1);
   if(q1 < 0)
      return "";
   int q2 = StringFind(raw, "\"", q1 + 1);
   if(q2 < 0)
      return "";
   return StringSubstr(raw, q1 + 1, q2 - q1 - 1);
  }

double JsonNumber(const string raw, const string key)
  {
   string token = "\"" + key + "\"";
   int p = StringFind(raw, token);
   if(p < 0)
      return 0.0;
   int colon = StringFind(raw, ":", p);
   if(colon < 0)
      return 0.0;
   string chunk = StringSubstr(raw, colon + 1, 32);
   StringReplace(chunk, ",", " ");
   StringReplace(chunk, "}", " ");
   StringReplace(chunk, "]", " ");
   StringTrimLeft(chunk);
   StringTrimRight(chunk);
   return StringToDouble(chunk);
  }

bool HasJsonKey(const string raw, const string key)
  {
   return (StringFind(raw, "\"" + key + "\"") >= 0);
  }

bool JsonFlag(const string raw, const string key, const bool fallback)
  {
   if(!HasJsonKey(raw, key))
      return fallback;
   string s = JsonString(raw, key);
   if(s != "")
     {
      StringToLower(s);
      return (s == "true" || s == "1" || s == "yes" || s == "on");
     }
   return (JsonNumber(raw, key) > 0.0);
  }

//+------------------------------------------------------------------+
