#property copyright "Python ML SMC Robot"
#property version   "2.00"
#property description "MQL5 execution bridge only. Python decides. Do not paste Python here."

//+------------------------------------------------------------------+
//| Execution bridge. Python writes command.json, this EA executes.  |
//| File -> Open Data Folder -> MQL5\Experts                         |
//| Also uses Common\Files\smc_bridge for Python IPC                 |
//+------------------------------------------------------------------+

#include <Trade/Trade.mqh>
#include <Files/File.mqh>

input string InpSymbol            = "XAUUSDm";
input int    InpMagic             = 20250824;
input int    InpMaxSpreadPoints   = 80;
input int    InpSlippagePoints    = 40;
input double InpDefaultBeR        = 1.0;
input double InpDefaultTrailR     = 1.5;
input bool   InpManageIfPythonLost = true;
input int    InpPythonTimeoutSec  = 45;
input string InpFolder            = "smc_bridge";

CTrade trade;
string g_lastId = "";
datetime g_lastPython = 0;
double g_beR = 1.0;
double g_trailR = 1.5;
bool   g_trailOn = true;

int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   if(!SymbolSelect(InpSymbol, true))
     {
      Print("Cannot select ", InpSymbol);
      return INIT_FAILED;
     }
   FolderCreate(InpFolder, FILE_COMMON);
   WriteStatus("init", 0, "ready");
   Print("SMC execution bridge ready. Python is the decision engine.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   WriteStatus("deinit", reason, "stopped");
  }

void OnTick()
  {
   ReadAndExecuteCommand();
   if(InpManageIfPythonLost)
      LocalManage();
   WriteStatus("tick", 0, "ok");
  }

void ReadAndExecuteCommand()
  {
   string path = InpFolder + "\\command.json";
   if(!FileIsExist(path, FILE_COMMON))
      return;
   int h = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
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
   if(id == "" || id == g_lastId)
      return;
   if(action == "HEARTBEAT" || action == "NONE")
     {
      g_lastPython = TimeCurrent();
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
      ticket = trade.ResultOrder();
      if(ok)
         price = trade.ResultPrice();
      WriteResult(id, ok, ticket, price, sl, tp,
                  ok ? "filled" : IntegerToString(trade.ResultRetcode()));
     }
   else if(action == "MODIFY")
     {
      ticket = (ulong)JsonNumber(raw, "ticket");
      ok = trade.PositionModify(ticket, NormalizePrice(symbol, sl), NormalizePrice(symbol, tp));
      WriteResult(id, ok, ticket, 0.0, sl, tp, ok ? "modified" : "modify_failed");
     }
   else if(action == "CLOSE")
     {
      ticket = (ulong)JsonNumber(raw, "ticket");
      ok = trade.PositionClose(ticket);
      WriteResult(id, ok, ticket, 0.0, 0.0, 0.0, ok ? "closed" : "close_failed");
     }
   g_lastId = id;
  }

string BrokerBlockReason(const string symbol, const double lots, const double sl, const double tp, const string action)
  {
   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT))
      return "symbol_missing";
   if(!SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE))
      return "trading_disabled";
   long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   if(spread > InpMaxSpreadPoints)
      return "spread_too_wide";
   if(action != "BUY" && action != "SELL")
      return "";
   if(lots <= 0.0)
      return "invalid_lot";
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0)
      return "invalid_quote";
   int stops = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double need = stops * point;
   if(action == "BUY" && (ask - sl < need || tp - ask < need))
      return "invalid_stops";
   if(action == "SELL" && (sl - bid < need || bid - tp < need))
      return "invalid_stops";
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
      double risk = MathAbs(entry - sl);
      if(risk <= 0.0)
         continue;
      if(type == POSITION_TYPE_BUY)
        {
         double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
         if(bid - entry >= g_beR * risk && sl < entry)
            trade.PositionModify(ticket, NormalizePrice(InpSymbol, entry), tp);
        }
      else
        {
         double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
         if(entry - ask >= g_beR * risk && (sl == 0.0 || sl > entry))
            trade.PositionModify(ticket, NormalizePrice(InpSymbol, entry), tp);
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
   string extra = StringFormat(
      "\"last_result\":{\"id\":\"%s\",\"ok\":%s,\"ticket\":%I64u,\"price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"error\":\"%s\"},",
      id, (ok ? "true" : "false"), ticket, price, sl, tp, msg);
   WriteStatusRaw(extra);
  }

void WriteStatus(const string phase, const int code, const string msg)
  {
   string extra = StringFormat("\"phase\":\"%s\",\"code\":%d,\"message\":\"%s\",", phase, code, msg);
   WriteStatusRaw(extra);
  }

void WriteStatusRaw(const string extra)
  {
   double bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   long spread = SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
   int npos = CountOurPositions(InpSymbol);
   string python_ok = ((TimeCurrent() - g_lastPython) <= InpPythonTimeoutSec || g_lastPython == 0) ? "true" : "false";
   string json = StringFormat(
      "{%s\"connected\":true,\"python_fresh\":%s,\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"spread\":%d,\"positions\":%d,\"last_command_id\":\"%s\",\"time\":\"%s\"}",
      extra, python_ok, InpSymbol, bid, ask, (int)spread, npos, g_lastId, TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   string path = InpFolder + "\\status.json";
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, json);
   FileClose(h);
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
   string chunk = StringSubstr(raw, colon + 1, 24);
   StringReplace(chunk, ",", " ");
   StringReplace(chunk, "}", " ");
   StringReplace(chunk, "]", " ");
   StringTrimLeft(chunk);
   StringTrimRight(chunk);
   return StringToDouble(chunk);
  }

//+------------------------------------------------------------------+
