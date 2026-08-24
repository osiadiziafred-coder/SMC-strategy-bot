#ifndef AMD_TRADING_MQH
#define AMD_TRADING_MQH

#include <Trade/Trade.mqh>
#include "AMD_Utils.mqh"

//+------------------------------------------------------------------+
//| Execution, position sizing, SL/TP, partials, breakeven           |
//+------------------------------------------------------------------+
class CAmdTrader
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;
   CTrade            m_trade;
   ulong             m_partialTicket;
   bool              m_partialDone;
   bool              m_beDone;

   bool              SelectFilling(void)
     {
      const int filling = (int)SymbolInfoInteger(m_symbol, SYMBOL_FILLING_MODE);
      if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
         m_trade.SetTypeFilling(ORDER_FILLING_IOC);
      else if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
         m_trade.SetTypeFilling(ORDER_FILLING_FOK);
      else
         m_trade.SetTypeFilling(ORDER_FILLING_RETURN);
      return(true);
     }

   double            StopsLevelPrice(void) const
     {
      const long lvl = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
      return(PointsToPrice(m_symbol, (double)lvl));
     }

public:
                     CAmdTrader(void)
     {
      m_symbol        = _Symbol;
      m_partialTicket = 0;
      m_partialDone   = false;
      m_beDone        = false;
     }

   void              Init(const SAmdConfig &cfg, const string symbol)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      m_trade.SetExpertMagicNumber(cfg.magic);
      m_trade.SetDeviationInPoints(20);
      SelectFilling();
      m_partialDone = false;
      m_beDone      = false;
     }

   void              ResetCycleFlags(void)
     {
      m_partialDone = false;
      m_beDone      = false;
      m_partialTicket = 0;
     }

   int               CountOpenPositions(void) const
     {
      int n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_cfg.magic)
            continue;
         n++;
        }
      return(n);
     }

   int               CountTodayDeals(const datetime now) const
     {
      const datetime from = DateFloor(now);
      if(!HistorySelect(from, now + 60))
         return(0);
      int n = 0;
      const int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
        {
         const ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0)
            continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != m_symbol)
            continue;
         if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_cfg.magic)
            continue;
         if((int)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN)
            continue;
         n++;
        }
      return(n);
     }

   double            CalcLot(const double entry, const double sl) const
     {
      if(m_cfg.lotMode == LOT_FIXED)
        {
         double lot = m_cfg.fixedLots;
         return(NormalizeVolume(lot));
        }

      const double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      const double riskMoney = balance * m_cfg.riskPercent / 100.0;
      const double tickSize  = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      const double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      const double slDist    = MathAbs(entry - sl);
      if(tickSize <= 0.0 || tickValue <= 0.0 || slDist <= 0.0 || riskMoney <= 0.0)
         return(0.0);
      const double ticks = slDist / tickSize;
      double lot = riskMoney / (ticks * tickValue);
      lot = NormalizeVolume(lot);
      if(m_cfg.maxLot > 0.0 && lot > m_cfg.maxLot)
         lot = NormalizeVolume(m_cfg.maxLot);
      return(lot);
     }

   double            NormalizeVolume(double lot) const
     {
      const double vmin = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      const double vmax = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      const double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      if(step > 0.0)
         lot = MathFloor(lot / step + 1e-8) * step;
      if(lot < vmin)
         return(0.0);
      if(lot > vmax)
         lot = vmax;
      const int digits = (step >= 1.0 ? 0 : (step >= 0.1 ? 1 : 2));
      return(NormalizeDouble(lot, digits));
     }

   bool              ValidateStops(const ENUM_TRADE_DIR dir, const double entry,
                                   double &sl, double &tp, string &reason) const
     {
      const double minPts = m_cfg.minSlPoints;
      const double maxPts = m_cfg.maxSlPoints;
      double slPts = PriceToPoints(m_symbol, MathAbs(entry - sl));
      const double stops = StopsLevelPrice();

      if(dir == DIR_BUY && sl >= entry)
        {
         reason = "BUY SL must be below entry";
         return(false);
        }
      if(dir == DIR_SELL && sl <= entry)
        {
         reason = "SELL SL must be above entry";
         return(false);
        }

      if(MathAbs(entry - sl) < stops)
        {
         if(dir == DIR_BUY)
            sl = entry - stops;
         else
            sl = entry + stops;
         slPts = PriceToPoints(m_symbol, MathAbs(entry - sl));
        }

      if(minPts > 0.0 && slPts < minPts)
        {
         reason = "SL too tight";
         return(false);
        }
      if(maxPts > 0.0 && slPts > maxPts)
        {
         reason = "SL distance exceeds maximum allowed risk";
         return(false);
        }
      if(tp > 0.0)
        {
         if(dir == DIR_BUY && tp <= entry)
           {
            reason = "BUY TP must be above entry";
            return(false);
           }
         if(dir == DIR_SELL && tp >= entry)
           {
            reason = "SELL TP must be below entry";
            return(false);
           }
         if(MathAbs(tp - entry) < stops)
           {
            reason = "TP inside stops level";
            return(false);
           }
        }
      reason = "";
      return(true);
     }

   double            SlFromSweep(const ENUM_TRADE_DIR dir, const SSweepEvent &sweep) const
     {
      const double buf = PointsToPrice(m_symbol, m_cfg.slBufferPoints);
      if(dir == DIR_BUY)
         return(NormalizePrice(m_symbol, sweep.extreme - buf));
      return(NormalizePrice(m_symbol, sweep.extreme + buf));
     }

   double            TpFromMode(const ENUM_TRADE_DIR dir, const double entry, const double sl,
                                const double liquidityTarget) const
     {
      const double slDist = MathAbs(entry - sl);
      double rrTp = 0.0;
      if(dir == DIR_BUY)
         rrTp = entry + slDist * m_cfg.riskReward;
      else
         rrTp = entry - slDist * m_cfg.riskReward;

      if(m_cfg.tpMode == TP_RISK_REWARD)
         return(NormalizePrice(m_symbol, rrTp));

      double liq = liquidityTarget;
      if(liq <= 0.0)
         return(NormalizePrice(m_symbol, rrTp));

      if(m_cfg.tpMode == TP_LIQUIDITY)
        {
         if(dir == DIR_BUY && liq > entry)
            return(NormalizePrice(m_symbol, liq));
         if(dir == DIR_SELL && liq < entry)
            return(NormalizePrice(m_symbol, liq));
         return(NormalizePrice(m_symbol, rrTp));
        }

      // Hybrid: use the farther of RR and liquidity (more conservative = closer? User asked RR or liquidity)
      // Hybrid uses RR as first objective conceptually; final TP is liquidity if it is beyond RR.
      if(dir == DIR_BUY)
         return(NormalizePrice(m_symbol, MathMax(rrTp, liq)));
      return(NormalizePrice(m_symbol, MathMin(rrTp, liq)));
     }

   bool              OpenTrade(const ENUM_TRADE_DIR dir, const double sl, const double tp,
                               const string comment, string &reason)
     {
      if(dir == DIR_BUY && !m_cfg.allowBuy)
        {
         reason = "Buys disabled";
         return(false);
        }
      if(dir == DIR_SELL && !m_cfg.allowSell)
        {
         reason = "Sells disabled";
         return(false);
        }
      if(CountOpenPositions() >= m_cfg.maxOpenPositions)
        {
         reason = "Max open positions reached";
         return(false);
        }
      if(CountTodayDeals(TimeCurrent()) >= m_cfg.maxTradesPerDay)
        {
         reason = "Max trades per day reached";
         return(false);
        }

      const double entry = (dir == DIR_BUY
                            ? SymbolInfoDouble(m_symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(m_symbol, SYMBOL_BID));
      double slUse = sl;
      double tpUse = tp;
      if(!ValidateStops(dir, entry, slUse, tpUse, reason))
         return(false);

      const double lot = CalcLot(entry, slUse);
      if(lot <= 0.0)
        {
         reason = "Lot size is zero (risk/SL too large for the account)";
         return(false);
        }

      m_trade.SetExpertMagicNumber(m_cfg.magic);
      const string cmt = (comment == "" ? m_cfg.tradeComment : comment);
      bool ok = false;
      if(dir == DIR_BUY)
         ok = m_trade.Buy(lot, m_symbol, 0.0, slUse, tpUse, cmt);
      else
         ok = m_trade.Sell(lot, m_symbol, 0.0, slUse, tpUse, cmt);

      if(!ok)
        {
         reason = "OrderSend failed: " + IntegerToString((int)m_trade.ResultRetcode()) +
                  " " + m_trade.ResultRetcodeDescription();
         return(false);
        }
      m_partialDone = false;
      m_beDone      = false;
      m_partialTicket = m_trade.ResultOrder();
      reason = "";
      return(true);
     }

   void              ManageOpenTrades(void)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_cfg.magic)
            continue;

         const long type   = PositionGetInteger(POSITION_TYPE);
         const double open = PositionGetDouble(POSITION_PRICE_OPEN);
         const double sl   = PositionGetDouble(POSITION_SL);
         const double tp   = PositionGetDouble(POSITION_TP);
         const double vol  = PositionGetDouble(POSITION_VOLUME);
         const double bid  = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         const double ask  = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         const double slDist = MathAbs(open - sl);
         if(slDist <= 0.0)
            continue;

         if(m_cfg.usePartialClose && !m_partialDone && m_cfg.partialClosePercent > 0.0)
           {
            const double trigger = m_cfg.partialCloseRR * slDist;
            bool hit = false;
            if(type == POSITION_TYPE_BUY)
               hit = (bid >= open + trigger);
            else
               hit = (ask <= open - trigger);
            if(hit)
              {
               double closeVol = vol * m_cfg.partialClosePercent / 100.0;
               closeVol = NormalizeVolume(closeVol);
               const double vmin = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
               if(closeVol >= vmin && (vol - closeVol) >= vmin - 1e-8)
                 {
                  if(m_trade.PositionClosePartial(ticket, closeVol))
                    {
                     m_partialDone = true;
                     if(m_cfg.moveBeAfterPartial)
                        MoveToBreakeven(ticket, type, open);
                    }
                 }
               else if(hit && m_cfg.moveBeAfterPartial)
                 {
                  MoveToBreakeven(ticket, type, open);
                  m_partialDone = true;
                 }
              }
           }
         else if(m_cfg.moveBeAfterPartial && m_partialDone && !m_beDone)
            MoveToBreakeven(ticket, type, open);

         if(m_cfg.closeFriday && IsFridayCloseTime(TimeCurrent(), m_cfg.fridayCloseHour, m_cfg.fridayCloseMinute))
            m_trade.PositionClose(ticket);
        }
     }

   bool              HasOpenPosition(void) const
     {
      return(CountOpenPositions() > 0);
     }

private:
   void              MoveToBreakeven(const ulong ticket, const long type, const double open)
     {
      if(m_beDone)
         return;
      const double off = PointsToPrice(m_symbol, m_cfg.beOffsetPoints);
      double newSl = (type == POSITION_TYPE_BUY ? open + off : open - off);
      newSl = NormalizePrice(m_symbol, newSl);
      const double tp = PositionGetDouble(POSITION_TP);
      if(m_trade.PositionModify(ticket, newSl, tp))
         m_beDone = true;
     }
  };

#endif
