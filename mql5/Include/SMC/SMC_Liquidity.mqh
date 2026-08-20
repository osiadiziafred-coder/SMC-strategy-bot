//+------------------------------------------------------------------+
//| SMC_Liquidity.mqh — Liquidity sweep detection                    |
//+------------------------------------------------------------------+
#ifndef SMC_LIQUIDITY_MQH
#define SMC_LIQUIDITY_MQH
#include "SMC_Swing.mqh"

//+------------------------------------------------------------------+
bool DetectLiquiditySweep(const double &high[], const double &low[],
                          const double &close[], int swingLookback,
                          double tolerance, int total, SLiquiditySweep &out)
  {
   out.found = false;

   if(total < swingLookback * 2 + 10)
      return false;

   int highIdx[], lowIdx[];
   double highPrices[], lowPrices[];
   int highCount = FindSwingHighs(high, swingLookback, total, highIdx, highPrices);
   int lowCount  = FindSwingLows(low, swingLookback, total, lowIdx, lowPrices);

   // Check last 5 closed bars (indices 1..5, series: 0 = forming bar)
   int checkTo = MathMin(5, total - swingLookback - 2);

   for(int i = 1; i <= checkTo; i++)
     {
      // Bullish sweep: wick below swing low, close back above
      int lastLowIdx = GetSwingOlderThanBar(lowIdx, lowCount, i);
      if(lastLowIdx >= 0)
        {
         double targetLow = lowPrices[lastLowIdx];
         if(low[i] < targetLow - tolerance && close[i] > targetLow)
           {
            out.found       = true;
            out.direction   = SMC_DIR_BULLISH;
            out.sweepIndex  = i;
            out.sweepPrice  = low[i];
            out.sweptLevel  = targetLow;
            return true;
           }
        }

      // Bearish sweep: wick above swing high, close back below
      int lastHighIdx = GetSwingOlderThanBar(highIdx, highCount, i);
      if(lastHighIdx >= 0)
        {
         double targetHigh = highPrices[lastHighIdx];
         if(high[i] > targetHigh + tolerance && close[i] < targetHigh)
           {
            out.found       = true;
            out.direction   = SMC_DIR_BEARISH;
            out.sweepIndex  = i;
            out.sweepPrice  = high[i];
            out.sweptLevel  = targetHigh;
            return true;
           }
        }
     }

   return false;
  }

#endif
