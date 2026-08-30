#property copyright "Python ML SMC Robot"
#property version   "3.01"
#property description "MQL5 safety bridge only. Python decides. Do not paste Python here."

//+------------------------------------------------------------------+
//| PythonML_SMC_Bridge.mq5                                          |
//| TWO PROGRAMS:                                                    |
//|   Python = ML/SMC brain (H1/M30/M15, BOS/MSS/CHoCH/OB/FVG,       |
//|            liquidity, score, lots, command.json)                 |
//|   This EA = execute + protect only (never invent BUY/SELL)       |
//| Common\Files\smc_bridge\command.json  /  status.json             |
//+------------------------------------------------------------------+

#include <Trade/Trade.mqh>

input string InpSymbol             = "XAUUSDm";
input int    InpMagic              = 20250824;
input int    InpMaxSpreadPoints    = 80;
input int    InpSlippagePoints     = 40;
input double InpDefaultBeR         = 1.0;
input double InpDefaultTrailR      = 1.5;
input bool   InpTrailEnabled       = true;
input double InpTrailLockR         = 0.50;
input double InpBeBufferPoints     = 0.0;
input bool   InpProtectIfPythonLost = true;
input int    InpPythonTimeoutSec   = 45;
input string InpFolder             = "smc_bridge";

CTrade   trade;
string   g_lastId = "";
datetime g_lastPython = 0;
double   g_beR = 1.0;
double   g_trailR = 1.5;
bool     g_trailOn = true;
double   g_trailLock = 0.50;
double   g_beBuffer = 0.0;
int      g_lastRetcode = 0;
string   g_lastError = "";
ulong    g_lastTicket = 0;
string   g_lastResultJson = "";
double   g_trackRisk[];
ulong    g_trackTicket[];

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   g_beR = InpDefaultBeR;
   g_trailR = InpDefaultTrailR;
   g_trailOn = InpTrailEnabled;
   g_trailLock = InpTrailLockR;
   g_beBuffer = InpBeBufferPoints * SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   if(!SymbolSelect(InpSymbol, true))
     {
      Print("Cannot select ", InpSymbol);
      return INIT_FAILED;
     }
   FolderCreate(InpFolder, FILE_COMMON);
   WriteStatus("init", 0, "ready");
   Print("Python ML SMC bridge ready. Decisions come from Python only.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   WriteStatus("deinit", reason, "stopped");
  }

void OnTick()
  {
   ReadAndExecuteCommand();
   if(InpProtectIfPythonLost || PythonFresh())
      LocalManage();
   WriteStatus("tick", g_lastRetcode, g_lastError);
  }

bool PythonFresh()
  {
   if(g_lastPython == 0)
      return false;
   return ((TimeCurrent() - g_lastPython) <= InpPythonTimeoutSec);
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
      symbol = InpSymbol;
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
   if(spread > InpMaxSpreadPoints)
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

void LocalManage()
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
      double risk = TrackedRisk(ticket, MathAbs(entry - sl));
      if(risk <= 0.0)
         continue;

      double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
      double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
      int stops = (int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL);
      int freeze = (int)SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_FREEZE_LEVEL);
      double need = MathMax(stops, freeze) * point;

      if(type == POSITION_TYPE_BUY)
        {
         double fav = bid - entry;
         double be = NormalizePrice(InpSymbol, entry + g_beBuffer);
         if(fav >= g_beR * risk && SlIsImprovement(type, be, sl) && bid - be >= need)
            SafeModify(ticket, be, tp, "breakeven");
         sl = PositionGetDouble(POSITION_SL);
         if(g_trailOn && fav >= g_trailR * risk)
           {
            double trail = NormalizePrice(InpSymbol, bid - g_trailLock * risk);
            if(SlIsImprovement(type, trail, sl) && bid - trail >= need)
               SafeModify(ticket, trail, tp, "trail");
           }
        }
      else
        {
         double fav = entry - ask;
         double be = NormalizePrice(InpSymbol, entry - g_beBuffer);
         if(fav >= g_beR * risk && SlIsImprovement(type, be, sl) && be - ask >= need)
            SafeModify(ticket, be, tp, "breakeven");
         sl = PositionGetDouble(POSITION_SL);
         if(g_trailOn && fav >= g_trailR * risk)
           {
            double trail = NormalizePrice(InpSymbol, ask + g_trailLock * risk);
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
   return NormalizeDouble(lots, 2);
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

void WriteStatusRaw(const string extra)
  {
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   long spread = SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   int npos = CountOurPositions(InpSymbol);
   double posSl = 0.0, posTp = 0.0, posPnl = 0.0;
   ulong posTicket = g_lastTicket;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
         continue;
      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      posTicket = ticket;
      posSl = PositionGetDouble(POSITION_SL);
      posTp = PositionGetDouble(POSITION_TP);
      posPnl = PositionGetDouble(POSITION_PROFIT);
      break;
     }
   string python_ok = PythonFresh() ? "true" : "false";
   string trail_ok = g_trailOn ? "true" : "false";
   string json = StringFormat(
      "{%s\"connected\":true,\"python_fresh\":%s,\"trail_on\":%s,\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread\":%d,\"positions\":%d,\"ticket\":%I64u,\"sl\":%.5f,\"tp\":%.5f,\"profit\":%.2f,\"last_command_id\":\"%s\",\"retcode\":%d,\"error\":\"%s\",\"time\":\"%s\"}",
      extra, python_ok, trail_ok, InpSymbol, bid, ask, (int)spread, npos, posTicket, posSl, posTp, posPnl,
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
