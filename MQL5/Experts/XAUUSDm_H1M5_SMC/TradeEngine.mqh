#ifndef XAUUSDM_SMC_TRADE_MQH
#define XAUUSDM_SMC_TRADE_MQH

#include <Trade/Trade.mqh>

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

#endif
