//+------------------------------------------------------------------+
//|                                          SMC_Safety_Bridge.mq5    |
//|   MQL5 safety bridge for the Python ML/SMC brain.                 |
//|                                                                  |
//|   This EA NEVER invents BUY/SELL signals. It only executes        |
//|   commands written by the Python brain to:                        |
//|       Common\Files\smc_bridge\command.json                        |
//|   and reports state back to:                                       |
//|       Common\Files\smc_bridge\status.json                         |
//|                                                                  |
//|   It independently enforces broker-side safety, one-position       |
//|   protection, breakeven and trailing stops, and keeps managing     |
//|   open trades even if the Python process disconnects.              |
//+------------------------------------------------------------------+
#property copyright "SMC ML Robot"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//--- Inputs
input string InpBridgeSubfolder     = "smc_bridge"; // Subfolder under Common\Files
input long   InpMagicNumber         = 990045;       // Magic number for robot trades
input int    InpPythonTimeoutSec    = 30;           // Reject new entries if Python silent longer
input double InpMaxSpreadPoints     = 60.0;         // Max allowed spread (points)
input double InpBreakevenBufferPts  = 20.0;         // Buffer beyond entry for breakeven (points)
input double InpTrailDistancePts    = 300.0;        // Trailing distance (points)
input int    InpTimerSeconds        = 1;            // Poll interval
input bool   InpAllowTrading        = true;         // Master trading switch

//--- Globals
CTrade   trade;
string   g_commandPath;
string   g_statusPath;
string   g_lastExecutedId = "";
double   g_lastHeartbeatValue = -1.0;   // last python heartbeat value seen
datetime g_lastHeartbeatLocal = 0;      // local time we last saw it change
string   g_lastError = "";

//+------------------------------------------------------------------+
int OnInit()
{
   g_commandPath = InpBridgeSubfolder + "\\command.json";
   g_statusPath  = InpBridgeSubfolder + "\\status.json";
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   g_lastHeartbeatLocal = TimeLocal();
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("SMC_Safety_Bridge initialised. Command file: Common\\Files\\", g_commandPath);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//+------------------------------------------------------------------+
void OnTimer()
{
   string js = ReadCommonFile(g_commandPath);
   ProcessCommand(js);
   ManageOpenPositions();
   WriteStatus();
}

//+------------------------------------------------------------------+
//| File helpers (Common folder)                                     |
//+------------------------------------------------------------------+
string ReadCommonFile(const string path)
{
   int handle = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return "";
   string content = "";
   while(!FileIsEnding(handle))
      content += FileReadString(handle);
   FileClose(handle);
   return content;
}

bool WriteCommonFile(const string path, const string content)
{
   int handle = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return false;
   FileWriteString(handle, content);
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| Minimal JSON accessors for the flat command object               |
//+------------------------------------------------------------------+
string JsonGetString(const string js, const string key)
{
   string needle = "\"" + key + "\"";
   int k = StringFind(js, needle);
   if(k < 0) return "";
   int colon = StringFind(js, ":", k + StringLen(needle));
   if(colon < 0) return "";
   int q1 = StringFind(js, "\"", colon + 1);
   if(q1 < 0) return "";
   int q2 = StringFind(js, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(js, q1 + 1, q2 - q1 - 1);
}

double JsonGetDouble(const string js, const string key, const double def=0.0)
{
   string needle = "\"" + key + "\"";
   int k = StringFind(js, needle);
   if(k < 0) return def;
   int colon = StringFind(js, ":", k + StringLen(needle));
   if(colon < 0) return def;
   int i = colon + 1;
   // Skip spaces
   while(i < StringLen(js))
   {
      ushort c = StringGetCharacter(js, i);
      if(c != ' ' && c != '\t' && c != '\n' && c != '\r') break;
      i++;
   }
   int start = i;
   while(i < StringLen(js))
   {
      ushort c = StringGetCharacter(js, i);
      if((c >= '0' && c <= '9') || c == '.' || c == '-' || c == '+' || c == 'e' || c == 'E')
         i++;
      else
         break;
   }
   if(i <= start) return def;
   return (double)StringToDouble(StringSubstr(js, start, i - start));
}

bool JsonGetBool(const string js, const string key, const bool def=false)
{
   string needle = "\"" + key + "\"";
   int k = StringFind(js, needle);
   if(k < 0) return def;
   int colon = StringFind(js, ":", k + StringLen(needle));
   if(colon < 0) return def;
   int t = StringFind(js, "true", colon);
   int f = StringFind(js, "false", colon);
   int brace = StringFind(js, "}", colon);
   if(t >= 0 && (t < brace || brace < 0) && (f < 0 || t < f))
      return true;
   return false;
}

//+------------------------------------------------------------------+
//| Position helpers                                                 |
//+------------------------------------------------------------------+
bool SelectRobotPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         return true;
   }
   return false;
}

int RobotPositionCount()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Python liveness                                                  |
//+------------------------------------------------------------------+
bool PythonIsAlive(const string js)
{
   double hb = JsonGetDouble(js, "heartbeat", -1.0);
   if(hb > 0.0 && hb != g_lastHeartbeatValue)
   {
      g_lastHeartbeatValue = hb;
      g_lastHeartbeatLocal = TimeLocal();
   }
   return (TimeLocal() - g_lastHeartbeatLocal) <= InpPythonTimeoutSec;
}

//+------------------------------------------------------------------+
//| Command processing                                               |
//+------------------------------------------------------------------+
void ProcessCommand(const string js)
{
   if(StringLen(js) < 2) return;

   bool pythonAlive = PythonIsAlive(js);

   string id = JsonGetString(js, "id");
   string action = JsonGetString(js, "action");
   if(id == "" || action == "") return;
   if(id == g_lastExecutedId) return;               // never execute the same id twice
   if(action == "HEARTBEAT" || action == "NONE")
   {
      g_lastExecutedId = id;
      return;
   }

   string symbol = JsonGetString(js, "symbol");
   if(symbol != "" && symbol != _Symbol)
   {
      g_lastError = "symbol mismatch: " + symbol;
      g_lastExecutedId = id;
      return;
   }

   if((action == "BUY" || action == "SELL"))
   {
      if(!InpAllowTrading)      { g_lastError = "trading disabled"; g_lastExecutedId = id; return; }
      if(!pythonAlive)          { g_lastError = "python stale - entry rejected"; g_lastExecutedId = id; return; }
      ExecuteEntry(id, action, js);
   }
   else if(action == "MODIFY")
   {
      ExecuteModify(id, js);
   }
   else if(action == "CLOSE")
   {
      ExecuteClose(id);
   }
}

//+------------------------------------------------------------------+
void ExecuteEntry(const string id, const string action, const string js)
{
   // One-position protection (broker-side).
   if(RobotPositionCount() >= 1)
   {
      g_lastError = "entry rejected: position already open";
      g_lastExecutedId = id;
      return;
   }

   double lots = JsonGetDouble(js, "lots", 0.0);
   double sl   = JsonGetDouble(js, "sl", 0.0);
   double tp   = JsonGetDouble(js, "tp", 0.0);

   lots = NormalizeLots(lots);
   if(lots <= 0.0) { g_lastError = "invalid lots"; g_lastExecutedId = id; return; }

   // Spread check.
   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / _Point;
   if(spread > InpMaxSpreadPoints)
   {
      g_lastError = "spread too wide: " + DoubleToString(spread, 1);
      g_lastExecutedId = id;
      return;
   }

   double price = (action == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                    : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   // Validate SL/TP sides.
   if(action == "BUY" && !(sl < price && tp > price))
   { g_lastError = "invalid BUY sl/tp"; g_lastExecutedId = id; return; }
   if(action == "SELL" && !(sl > price && tp < price))
   { g_lastError = "invalid SELL sl/tp"; g_lastExecutedId = id; return; }

   // Respect broker minimum stop distance.
   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   if(MathAbs(price - sl) < stopLevel || MathAbs(tp - price) < stopLevel)
   {
      g_lastError = "sl/tp inside broker stop level";
      g_lastExecutedId = id;
      return;
   }

   bool ok = false;
   if(action == "BUY")
      ok = trade.Buy(lots, _Symbol, price, sl, tp, "SMC-ML");
   else
      ok = trade.Sell(lots, _Symbol, price, sl, tp, "SMC-ML");

   if(ok)
      g_lastError = "";
   else
      g_lastError = "order failed: " + IntegerToString(trade.ResultRetcode()) + " " + trade.ResultComment();

   g_lastExecutedId = id;   // mark processed regardless, to avoid re-execution
}

//+------------------------------------------------------------------+
void ExecuteModify(const string id, const string js)
{
   if(!SelectRobotPosition()) { g_lastExecutedId = id; return; }
   double sl = JsonGetDouble(js, "sl", PositionGetDouble(POSITION_SL));
   double tp = JsonGetDouble(js, "tp", PositionGetDouble(POSITION_TP));
   if(trade.PositionModify(_Symbol, sl, tp))
      g_lastError = "";
   else
      g_lastError = "modify failed: " + IntegerToString(trade.ResultRetcode());
   g_lastExecutedId = id;
}

//+------------------------------------------------------------------+
void ExecuteClose(const string id)
{
   if(SelectRobotPosition())
   {
      if(!trade.PositionClose(_Symbol))
         g_lastError = "close failed: " + IntegerToString(trade.ResultRetcode());
      else
         g_lastError = "";
   }
   g_lastExecutedId = id;
}

//+------------------------------------------------------------------+
double NormalizeLots(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   lots = MathFloor(lots / step + 1e-9) * step;
   if(lots < vmin) lots = vmin;
   if(lots > vmax) lots = vmax;
   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
//| Trade protection: breakeven + trailing (only tighten).           |
//| Runs every timer tick even if Python is disconnected.            |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   if(!SelectRobotPosition())
      return;

   long   type   = PositionGetInteger(POSITION_TYPE);
   double open   = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl     = PositionGetDouble(POSITION_SL);
   double tp     = PositionGetDouble(POSITION_TP);

   // Recover the initial risk (R) from the 1:2 target so protection works even
   // after an EA restart with no external state.
   double riskDist = (tp != 0.0) ? MathAbs(tp - open) / 2.0 : 0.0;
   if(riskDist <= 0.0)
      return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double buffer = InpBreakevenBufferPts * _Point;
   double trailDist = InpTrailDistancePts * _Point;
   double newSl = sl;

   if(type == POSITION_TYPE_BUY)
   {
      double profit = bid - open;
      // Breakeven at +1R
      if(profit >= riskDist)
      {
         double beSl = open + buffer;
         if(beSl > newSl) newSl = beSl;
      }
      // Trailing after +1.5R, only move up
      if(profit >= 1.5 * riskDist)
      {
         double trailSl = bid - trailDist;
         if(trailSl > newSl) newSl = trailSl;
      }
      if(newSl > sl + _Point*0.5)
         trade.PositionModify(_Symbol, NormalizeDouble(newSl, _Digits), tp);
   }
   else if(type == POSITION_TYPE_SELL)
   {
      double profit = open - ask;
      if(profit >= riskDist)
      {
         double beSl = open - buffer;
         if(sl == 0.0 || beSl < newSl) newSl = beSl;
      }
      if(profit >= 1.5 * riskDist)
      {
         double trailSl = ask + trailDist;
         if(sl == 0.0 || trailSl < newSl) newSl = trailSl;
      }
      if(sl == 0.0 || newSl < sl - _Point*0.5)
         trade.PositionModify(_Symbol, NormalizeDouble(newSl, _Digits), tp);
   }
}

//+------------------------------------------------------------------+
//| Status reporting                                                 |
//+------------------------------------------------------------------+
void WriteStatus()
{
   string positions = "[]";
   if(SelectRobotPosition())
   {
      string ptype = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      positions = "[{" +
         "\"symbol\":\"" + _Symbol + "\"," +
         "\"type\":\"" + ptype + "\"," +
         "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), 2) + "," +
         "\"open\":" + DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), _Digits) + "," +
         "\"sl\":" + DoubleToString(PositionGetDouble(POSITION_SL), _Digits) + "," +
         "\"tp\":" + DoubleToString(PositionGetDouble(POSITION_TP), _Digits) + "," +
         "\"profit\":" + DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) +
         "}]";
   }

   bool pythonAlive = (TimeLocal() - g_lastHeartbeatLocal) <= InpPythonTimeoutSec;

   string js = "{\n";
   js += "  \"heartbeat\": " + IntegerToString((long)TimeGMT()) + ",\n";
   js += "  \"ea_time\": \"" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + "\",\n";
   js += "  \"symbol\": \"" + _Symbol + "\",\n";
   js += "  \"last_executed_id\": \"" + g_lastExecutedId + "\",\n";
   js += "  \"python_alive\": " + (pythonAlive ? "true" : "false") + ",\n";
   js += "  \"account\": {\"balance\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) +
         ", \"equity\": " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "},\n";
   js += "  \"positions\": " + positions + ",\n";
   js += "  \"error\": \"" + g_lastError + "\"\n";
   js += "}\n";

   WriteCommonFile(g_statusPath, js);
}
//+------------------------------------------------------------------+
