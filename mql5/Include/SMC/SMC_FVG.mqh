//+------------------------------------------------------------------+
//| SMC_FVG.mqh — Fair Value Gap detection                           |
//+------------------------------------------------------------------+
#ifndef SMC_FVG_MQH
#define SMC_FVG_MQH
#include "SMC_Types.mqh"

//+------------------------------------------------------------------+
bool FindNearestFVG(const double &high[], const double &low[],
                    int direction, double currentPrice,
                    double minGap, int afterIndex, int total,
                    SFairValueGap &out)
  {
   out.found = false;

   int startBar = MathMax(2, afterIndex);
   SFairValueGap best;
   best.found = false;

   for(int i = startBar; i < total; i++)
     {
      // Bullish FVG: candle[i-2].high < candle[i].low
      if(low[i] > high[i - 2])
        {
         double gap = low[i] - high[i - 2];
         if(gap >= minGap)
           {
            best.found     = true;
            best.direction = SMC_DIR_BULLISH;
            best.top       = low[i];
            best.bottom    = high[i - 2];
            best.index     = i;
           }
        }

      // Bearish FVG: candle[i-2].low > candle[i].high
      if(high[i] < low[i - 2])
        {
         double gap = low[i - 2] - high[i];
         if(gap >= minGap)
           {
            best.found     = true;
            best.direction = SMC_DIR_BEARISH;
            best.top       = low[i - 2];
            best.bottom    = high[i];
            best.index     = i;
           }
        }
     }

   if(!best.found || best.direction != direction)
      return false;

   // Price inside FVG zone, or use most recent FVG in direction
   if(currentPrice >= best.bottom && currentPrice <= best.top)
     {
      out = best;
      return true;
     }

   // Accept most recent FVG even if price not exactly inside
   out = best;
   return true;
  }

#endif
