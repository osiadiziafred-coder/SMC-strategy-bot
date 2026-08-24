#ifndef AMD_LIQUIDITY_MQH
#define AMD_LIQUIDITY_MQH

#include "AMD_Utils.mqh"

//+------------------------------------------------------------------+
//| Liquidity pools: session extremes, swings, equal highs/lows      |
//+------------------------------------------------------------------+
class CLiquidityEngine
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;

public:
   SLiquidityLevel   bsl[];            // buy-side (above highs)
   SLiquidityLevel   ssl[];            // sell-side (below lows)
   int               bslCount;
   int               sslCount;

                     CLiquidityEngine(void) { bslCount = 0; sslCount = 0; }

   void              Init(const SAmdConfig &cfg, const string symbol)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      bslCount = 0;
      sslCount = 0;
      ArrayResize(bsl, 0);
      ArrayResize(ssl, 0);
     }

   void              Reset(void)
     {
      bslCount = 0;
      sslCount = 0;
      ArrayResize(bsl, 0);
      ArrayResize(ssl, 0);
     }

   void              AddLevel(const double price, const datetime tFormed,
                              const bool buySide, const string label)
     {
      SLiquidityLevel lvl;
      lvl.price        = price;
      lvl.tFormed      = tFormed;
      lvl.buySide      = buySide;
      lvl.swept        = false;
      lvl.tSwept       = 0;
      lvl.sweepExtreme = 0;
      lvl.label        = label;
      if(buySide)
        {
         const int n = ArraySize(bsl);
         ArrayResize(bsl, n + 1);
         bsl[n] = lvl;
         bslCount = n + 1;
        }
      else
        {
         const int n = ArraySize(ssl);
         ArrayResize(ssl, n + 1);
         ssl[n] = lvl;
         sslCount = n + 1;
        }
     }

   void              BuildFromRange(const SSessionRange &range, const MqlRates &ltf[], const int total)
     {
      Reset();
      if(range.high <= 0.0 || range.low <= 0.0)
         return;

      AddLevel(range.high, range.tEnd, true,  "Session High BSL");
      AddLevel(range.low,  range.tEnd, false, "Session Low SSL");

      // Recent fractal swings as additional liquidity
      const int strength = MathMax(m_cfg.swingStrength, 1);
      const int look     = MathMin(m_cfg.equalLookback, total - strength - 1);
      double swingHighs[];
      datetime swingHighT[];
      double swingLows[];
      datetime swingLowT[];
      int sh = 0, sl = 0;
      ArrayResize(swingHighs, 0);
      ArrayResize(swingLows, 0);

      for(int i = strength; i <= look; i++)
        {
         if(IsSwingHigh(ltf, i, strength, total))
           {
            const int n = ArraySize(swingHighs);
            ArrayResize(swingHighs, n + 1);
            ArrayResize(swingHighT, n + 1);
            swingHighs[n] = ltf[i].high;
            swingHighT[n] = ltf[i].time;
            AddLevel(ltf[i].high, ltf[i].time, true, "Swing High BSL");
            sh++;
           }
         if(IsSwingLow(ltf, i, strength, total))
           {
            const int n = ArraySize(swingLows);
            ArrayResize(swingLows, n + 1);
            ArrayResize(swingLowT, n + 1);
            swingLows[n] = ltf[i].low;
            swingLowT[n] = ltf[i].time;
            AddLevel(ltf[i].low, ltf[i].time, false, "Swing Low SSL");
            sl++;
           }
        }

      const double tol = PointsToPrice(m_symbol, m_cfg.equalTolerancePoints);
      MarkEqualLevels(swingHighs, swingHighT, true,  tol, "Equal Highs BSL");
      MarkEqualLevels(swingLows,  swingLowT,  false, tol, "Equal Lows SSL");
     }

   void              MarkEqualLevels(const double &prices[], const datetime &times[],
                                     const bool buySide, const double tol, const string label)
     {
      const int n = ArraySize(prices);
      for(int i = 0; i < n; i++)
        {
         for(int j = i + 1; j < n; j++)
           {
            if(MathAbs(prices[i] - prices[j]) <= tol)
              {
               const double mid = 0.5 * (prices[i] + prices[j]);
               AddLevel(mid, MathMax(times[i], times[j]), buySide, label);
              }
           }
        }
     }

   bool              DetectSweep(const MqlRates &bar, const SSessionRange &range, SSweepEvent &sweep) const
     {
      if(!range.valid)
         return(false);

      const double buffer = PointsToPrice(m_symbol, m_cfg.sweepBufferPoints);
      const double minRun = PointsToPrice(m_symbol, m_cfg.minSweepPoints);
      const double askHigh = bar.high;
      const double bidLow  = bar.low;

      // Buy-side sweep (high taken) => potential SELL setup
      if(askHigh > range.high + buffer && (askHigh - range.high) >= minRun)
        {
         sweep.active        = true;
         sweep.setupDir      = DIR_SELL;
         sweep.level         = range.high;
         sweep.extreme       = askHigh;
         sweep.tSweep        = bar.time;
         sweep.sweepOpen     = bar.open;
         sweep.sweepClose    = bar.close;
         sweep.sweepHigh     = bar.high;
         sweep.sweepLow      = bar.low;
         sweep.returned      = SweepReturned(bar, range, true);
         sweep.tReturned     = (sweep.returned ? bar.time : 0);
         return(true);
        }

      // Sell-side sweep (low taken) => potential BUY setup
      if(bidLow < range.low - buffer && (range.low - bidLow) >= minRun)
        {
         sweep.active        = true;
         sweep.setupDir      = DIR_BUY;
         sweep.level         = range.low;
         sweep.extreme       = bidLow;
         sweep.tSweep        = bar.time;
         sweep.sweepOpen     = bar.open;
         sweep.sweepClose    = bar.close;
         sweep.sweepHigh     = bar.high;
         sweep.sweepLow      = bar.low;
         sweep.returned      = SweepReturned(bar, range, false);
         sweep.tReturned     = (sweep.returned ? bar.time : 0);
         return(true);
        }
      return(false);
     }

   bool              SweepReturned(const MqlRates &bar, const SSessionRange &range, const bool sweptHigh) const
     {
      switch(m_cfg.sweepReturnMode)
        {
         case RETURN_WICK_ONLY:
            if(sweptHigh)
               return(bar.close < bar.high && bar.close <= range.high);
            return(bar.close > bar.low && bar.close >= range.low);
         case RETURN_THROUGH_LEVEL:
            if(sweptHigh)
               return(bar.close < range.high);
            return(bar.close > range.low);
         default: // RETURN_INSIDE_RANGE
            if(sweptHigh)
               return(bar.close <= range.high && bar.close >= range.low);
            return(bar.close >= range.low && bar.close <= range.high);
        }
     }

   bool              UpdateReturn(const MqlRates &bar, const SSessionRange &range, SSweepEvent &sweep) const
     {
      if(!sweep.active || sweep.returned)
         return(sweep.returned);
      const bool sweptHigh = (sweep.setupDir == DIR_SELL);
      if(sweep.setupDir == DIR_SELL && bar.high > sweep.extreme)
         sweep.extreme = bar.high;
      if(sweep.setupDir == DIR_BUY && bar.low < sweep.extreme)
         sweep.extreme = bar.low;
      if(SweepReturned(bar, range, sweptHigh))
        {
         sweep.returned  = true;
         sweep.tReturned = bar.time;
        }
      return(sweep.returned);
     }

   double            NextLiquidityTarget(const ENUM_TRADE_DIR dir, const double entry,
                                         const SSessionRange &range) const
     {
      if(dir == DIR_BUY)
        {
         // Draw on buy-side: range high, then nearest BSL above entry
         double target = range.high;
         for(int i = 0; i < bslCount; i++)
           {
            if(bsl[i].price > entry + PointsToPrice(m_symbol, 10.0))
              {
               if(target <= entry || bsl[i].price < target)
                  target = bsl[i].price;
              }
           }
         if(target <= entry)
            target = range.high;
         return(target);
        }
      if(dir == DIR_SELL)
        {
         double target = range.low;
         for(int i = 0; i < sslCount; i++)
           {
            if(ssl[i].price < entry - PointsToPrice(m_symbol, 10.0))
              {
               if(target >= entry || ssl[i].price > target)
                  target = ssl[i].price;
              }
           }
         if(target >= entry)
            target = range.low;
         return(target);
        }
      return(0.0);
     }
  };

#endif
