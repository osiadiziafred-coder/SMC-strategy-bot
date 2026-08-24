#ifndef AMD_SESSIONS_MQH
#define AMD_SESSIONS_MQH

#include "AMD_Utils.mqh"

//+------------------------------------------------------------------+
//| Session clock and accumulation-range builder                     |
//+------------------------------------------------------------------+
class CSessionManager
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;

public:
                     CSessionManager(void) { m_symbol = _Symbol; m_tf = PERIOD_M15; }

   void              Init(const SAmdConfig &cfg, const string symbol, const ENUM_TIMEFRAMES tf)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      m_tf     = tf;
     }

   ENUM_SESSION_KIND CurrentSession(const datetime now) const
     {
      if(TimeInWindow(now, m_cfg.asiaStartHour, m_cfg.asiaStartMinute,
                      m_cfg.asiaEndHour, m_cfg.asiaEndMinute))
         return(SESSION_ASIA);
      if(TimeInWindow(now, m_cfg.londonStartHour, m_cfg.londonStartMinute,
                      m_cfg.londonEndHour, m_cfg.londonEndMinute))
         return(SESSION_LONDON);
      if(TimeInWindow(now, m_cfg.nyStartHour, m_cfg.nyStartMinute,
                      m_cfg.nyEndHour, m_cfg.nyEndMinute))
         return(SESSION_NEWYORK);
      return(SESSION_NONE);
     }

   bool              InAccumulation(const datetime now) const
     {
      return(CurrentSession(now) == SESSION_ASIA);
     }

   bool              InTradeWindow(const datetime now) const
     {
      if(m_cfg.closeFriday && IsFridayCloseTime(now, m_cfg.fridayCloseHour, m_cfg.fridayCloseMinute))
         return(false);
      const ENUM_SESSION_KIND s = CurrentSession(now);
      if(s == SESSION_LONDON && m_cfg.tradeLondon)
         return(true);
      if(s == SESSION_NEWYORK && m_cfg.tradeNewYork)
         return(true);
      return(false);
     }

   bool              AccumulationBounds(const datetime now, datetime &tStart, datetime &tEnd) const
     {
      return(GetSessionBounds(now, m_cfg.asiaStartHour, m_cfg.asiaStartMinute,
                              m_cfg.asiaEndHour, m_cfg.asiaEndMinute, tStart, tEnd));
     }

   bool              BuildRange(const datetime now, SSessionRange &range) const
     {
      datetime tStart, tEnd;
      if(!AccumulationBounds(now, tStart, tEnd))
         return(false);

      range.tStart     = tStart;
      range.tEnd       = tEnd;
      range.name       = "ASIA";
      range.complete   = (now >= tEnd);
      range.valid      = false;
      range.openPrice  = 0;
      range.closePrice = 0;
      range.high       = 0;
      range.low        = 0;
      range.rangeSize  = 0;

      const datetime toTime = (now < tEnd ? now : tEnd - 1);
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      const int copied = CopyRates(m_symbol, m_tf, tStart, toTime, rates);
      if(copied < m_cfg.minAccBars)
         return(false);

      range.high      = rates[copied - 1].high;
      range.low       = rates[copied - 1].low;
      range.openPrice = rates[copied - 1].open;
      range.closePrice= rates[0].close;
      int barsInside  = 0;
      for(int i = 0; i < copied; i++)
        {
         if(rates[i].time < tStart || rates[i].time >= tEnd)
            continue;
         barsInside++;
         if(rates[i].high > range.high)
            range.high = rates[i].high;
         if(rates[i].low < range.low)
            range.low = rates[i].low;
        }
      if(barsInside < m_cfg.minAccBars)
         return(false);

      range.rangeSize = range.high - range.low;
      const double pts = PriceToPoints(m_symbol, range.rangeSize);
      range.valid = (pts >= m_cfg.minRangePoints);
      if(m_cfg.maxRangePoints > 0.0 && pts > m_cfg.maxRangePoints)
         range.valid = false;
      return(true);
     }
  };

#endif
