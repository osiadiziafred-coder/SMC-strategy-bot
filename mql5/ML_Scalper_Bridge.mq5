//+------------------------------------------------------------------+
//|                                         ML_Scalper_Bridge.mq5     |
//|   MQL5 execution + protection layer for the Python ML scalper.    |
//|                                                                  |
//|   This EA NEVER invents BUY/SELL signals. It only executes        |
//|   commands written by the Python brain to:                        |
//|       Common\Files\ml_scalper_bridge\command.json                 |
//|   and reports state back to:                                      |
//|       Common\Files\ml_scalper_bridge\status.json                  |
//|                                                                  |
//|   Broker-side checks: symbol, spread, lot size, margin, SL        |
//|   distance, trading permission, max positions, Python heartbeat,  |
//|   duplicate command ids, daily-loss / consecutive-loss halt,      |
//|   emergency protection. Open trades are still managed if Python   |
//|   goes silent.                                                    |
//+------------------------------------------------------------------+
#property copyright "ML Scalper"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input string InpBridgeSubfolder      = "ml_scalper_bridge";
input long   InpMagicNumber          = 990075;
input int    InpPythonTimeoutSec     = 30;
input double InpMaxSpreadPoints      = 80.0;
input double InpBreakevenBufferPts   = 20.0;
input double InpTrailDistancePts     = 300.0;
input int    InpTimerSeconds         = 1;
input bool   InpAllowTrading         = true;
input int    InpMaxPositions         = 1;
input double InpMinMarginLevelPct    = 200.0;
input double InpMaxDailyLossPercent  = 3.0;
input int    InpMaxConsecutiveLosses = 3;
input bool   InpEmergencyCloseOnDisconnect = false; // keep managing by default

CTrade   trade;
string   g_commandPath;
string   g_statusPath;
string   g_lastExecutedId = "";
double   g_lastHeartbeatValue = -1.0;
datetime g_lastHeartbeatLocal = 0;
string   g_lastError = "";
double   g_dailyPnl = 0.0;
int      g_tradesToday = 0;
int      g_consecutiveLosses = 0;

int OnInit()
{
   g_commandPath = InpBridgeSubfolder + "\\command.json";
   g_statusPath  = InpBridgeSubfolder + "\\status.json";
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);
   g_lastHeartbeatLocal = TimeLocal();
   EventSetTimer(MathMax(1, InpTimerSeconds));
   Print("ML_Scalper_Bridge initialised. Command file: Common\\Files\\", g_commandPath);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   UpdateRiskStats();
   string js = ReadCommonFile(g_commandPath);
   ProcessCommand(js);
   ManageOpenPositions();
   WriteStatus();
}

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

bool TradingPermissionOk()
{
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return false;
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return false;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
      return false;
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return false;
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(mode == SYMBOL_TRADE_MODE_DISABLED)
      return false;
   return true;
}

void ProcessCommand(const string js)
{
   if(StringLen(js) < 2) return;

   bool pythonAlive = PythonIsAlive(js);

   string id = JsonGetString(js, "id");
   string action = JsonGetString(js, "action");
   if(id == "" || action == "") return;
   if(id == g_lastExecutedId) return;
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

   if(action == "BUY" || action == "SELL")
   {
      if(!InpAllowTrading)      { g_lastError = "trading disabled"; g_lastExecutedId = id; return; }
      if(!pythonAlive)          { g_lastError = "python stale - entry rejected"; g_lastExecutedId = id; return; }
      if(!TradingPermissionOk()){ g_lastError = "trading not permitted"; g_lastExecutedId = id; return; }
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

void ExecuteEntry(const string id, const string action, const string js)
{
   if(RobotPositionCount() >= InpMaxPositions)
   {
      g_lastError = "entry rejected: max positions";
      g_lastExecutedId = id;
      return;
   }

   if(g_consecutiveLosses >= InpMaxConsecutiveLosses)
   {
      g_lastError = "entry rejected: consecutive-loss halt";
      g_lastExecutedId = id;
      return;
   }

   double startBalance = AccountInfoDouble(ACCOUNT_BALANCE) - g_dailyPnl;
   if(startBalance <= 0.0) startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(g_dailyPnl < 0.0 && startBalance > 0.0)
   {
      double lossPct = (-g_dailyPnl / startBalance) * 100.0;
      if(lossPct >= InpMaxDailyLossPercent)
      {
         g_lastError = "entry rejected: daily-loss halt";
         g_lastExecutedId = id;
         return;
      }
   }

   double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
   if(marginLevel > 0.0 && marginLevel < InpMinMarginLevelPct)
   {
      g_lastError = "entry rejected: margin level";
      g_lastExecutedId = id;
      return;
   }

   double lots = JsonGetDouble(js, "lots", 0.0);
   double sl   = JsonGetDouble(js, "sl", 0.0);
   double tp   = JsonGetDouble(js, "tp", 0.0);
   lots = NormalizeLots(lots);
   if(lots <= 0.0) { g_lastError = "invalid lots"; g_lastExecutedId = id; return; }

   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID)) / _Point;
   if(spread > InpMaxSpreadPoints)
   {
      g_lastError = "spread too wide: " + DoubleToString(spread, 1);
      g_lastExecutedId = id;
      return;
   }

   double price = (action == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                    : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(action == "BUY" && !(sl < price && tp > price))
   { g_lastError = "invalid BUY sl/tp"; g_lastExecutedId = id; return; }
   if(action == "SELL" && !(sl > price && tp < price))
   { g_lastError = "invalid SELL sl/tp"; g_lastExecutedId = id; return; }

   double stopLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double freezeLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL) * _Point;
   double minDist = MathMax(stopLevel, freezeLevel);
   if(MathAbs(price - sl) < minDist || MathAbs(tp - price) < minDist)
   {
      g_lastError = "sl/tp inside broker stop/freeze level";
      g_lastExecutedId = id;
      return;
   }

   MqlTradeRequest req;
   MqlTradeCheckResult chk;
   ZeroMemory(req);
   ZeroMemory(chk);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.volume = lots;
   req.type = (action == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price = price;
   req.sl = sl;
   req.tp = tp;
   req.deviation = 30;
   req.magic = InpMagicNumber;
   req.comment = "ML-SCALP";
   if(!OrderCheck(req, chk))
   {
      g_lastError = "margin/order check failed: " + IntegerToString((int)chk.retcode) + " " + chk.comment;
      g_lastExecutedId = id;
      return;
   }

   bool ok = false;
   if(action == "BUY")
      ok = trade.Buy(lots, _Symbol, price, sl, tp, "ML-SCALP");
   else
      ok = trade.Sell(lots, _Symbol, price, sl, tp, "ML-SCALP");

   if(ok)
      g_lastError = "";
   else
      g_lastError = "order failed: " + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultComment();

   g_lastExecutedId = id;
}

void ExecuteModify(const string id, const string js)
{
   if(!SelectRobotPosition()) { g_lastExecutedId = id; return; }
   double sl = JsonGetDouble(js, "sl", PositionGetDouble(POSITION_SL));
   double tp = JsonGetDouble(js, "tp", PositionGetDouble(POSITION_TP));
   if(trade.PositionModify(_Symbol, sl, tp))
      g_lastError = "";
   else
      g_lastError = "modify failed: " + IntegerToString((int)trade.ResultRetcode());
   g_lastExecutedId = id;
}

void ExecuteClose(const string id)
{
   if(SelectRobotPosition())
   {
      if(!trade.PositionClose(_Symbol))
         g_lastError = "close failed: " + IntegerToString((int)trade.ResultRetcode());
      else
         g_lastError = "";
   }
   g_lastExecutedId = id;
}

int VolumeDigits()
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   int digits = 0;
   while(step < 0.999999 && digits < 8)
   {
      step *= 10.0;
      digits++;
   }
   return digits;
}

double NormalizeLots(double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   lots = MathFloor(lots / step + 1e-9) * step;
   if(lots < vmin) lots = vmin;
   if(lots > vmax) lots = vmax;
   return NormalizeDouble(lots, VolumeDigits());
}

void ManageOpenPositions()
{
   if(!SelectRobotPosition())
   {
      if(InpEmergencyCloseOnDisconnect && (TimeLocal() - g_lastHeartbeatLocal) > InpPythonTimeoutSec)
         return;
      return;
   }

   if(InpEmergencyCloseOnDisconnect && (TimeLocal() - g_lastHeartbeatLocal) > InpPythonTimeoutSec)
   {
      trade.PositionClose(_Symbol);
      g_lastError = "emergency close: python disconnected";
      return;
   }

   long   type   = PositionGetInteger(POSITION_TYPE);
   double open   = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl     = PositionGetDouble(POSITION_SL);
   double tp     = PositionGetDouble(POSITION_TP);

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
      if(profit >= riskDist)
      {
         double beSl = open + buffer;
         if(beSl > newSl) newSl = beSl;
      }
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

void UpdateRiskStats()
{
   datetime from = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   if(!HistorySelect(from, TimeCurrent() + 60))
      return;

   g_dailyPnl = 0.0;
   g_tradesToday = 0;
   g_consecutiveLosses = 0;

   int deals = HistoryDealsTotal();
   double lastPnl = 0.0;
   bool countingStreak = true;
   int streak = 0;

   for(int i = deals - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagicNumber) continue;
      if(HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double pnl = HistoryDealGetDouble(ticket, DEAL_PROFIT)
                 + HistoryDealGetDouble(ticket, DEAL_SWAP)
                 + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      datetime t = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      if(t >= from)
      {
         g_dailyPnl += pnl;
         g_tradesToday++;
      }
      if(countingStreak)
      {
         if(pnl < 0.0)
            streak++;
         else
            countingStreak = false;
      }
      lastPnl = pnl;
   }
   g_consecutiveLosses = streak;
   lastPnl = lastPnl;
}

void WriteStatus()
{
   string positions = "[]";
   if(SelectRobotPosition())
   {
      string ptype = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      positions = "[{" +
         "\"symbol\":\"" + _Symbol + "\"," +
         "\"type\":\"" + ptype + "\"," +
         "\"volume\":" + DoubleToString(PositionGetDouble(POSITION_VOLUME), VolumeDigits()) + "," +
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
         ", \"equity\": " + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) +
         ", \"margin_free\": " + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + "},\n";
   js += "  \"risk\": {\"daily_pnl\": " + DoubleToString(g_dailyPnl, 2) +
         ", \"consecutive_losses\": " + IntegerToString(g_consecutiveLosses) +
         ", \"trades_today\": " + IntegerToString(g_tradesToday) + "},\n";
   js += "  \"positions\": " + positions + ",\n";
   js += "  \"error\": \"" + g_lastError + "\"\n";
   js += "}\n";

   WriteCommonFile(g_statusPath, js);
}
//+------------------------------------------------------------------+
