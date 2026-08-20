//+------------------------------------------------------------------+
//| SMC_Structure.mqh — MSS/CHoCH detection and H1 bias              |
//+------------------------------------------------------------------+
#ifndef SMC_STRUCTURE_MQH
#define SMC_STRUCTURE_MQH
#include "SMC_Swing.mqh"

//+------------------------------------------------------------------+
ENUM_SMC_BIAS DetermineBias(const double &high[], const double &low[],
                            int swingLookback, int total)
  {
   int highIdx[], lowIdx[];
   double highPrices[], lowPrices[];
   int highCount = FindSwingHighs(high, swingLookback, total, highIdx, highPrices);
   int lowCount  = FindSwingLows(low, swingLookback, total, lowIdx, lowPrices);

   int h1, h2, l1, l2;
   double hp1, hp2, lp1, lp2;

   if(!GetTwoMostRecentSwings(highIdx, highPrices, highCount, h1, h2, hp1, hp2))
      return SMC_BIAS_NEUTRAL;
   if(!GetTwoMostRecentSwings(lowIdx, lowPrices, lowCount, l1, l2, lp1, lp2))
      return SMC_BIAS_NEUTRAL;

   bool hh = hp1 > hp2;
   bool hl = lp1 > lp2;
   bool lh = hp1 < hp2;
   bool ll = lp1 < lp2;

   if(hh && hl)
      return SMC_BIAS_BULLISH;
   if(lh && ll)
      return SMC_BIAS_BEARISH;
   return SMC_BIAS_NEUTRAL;
  }

//+------------------------------------------------------------------+
bool DetectStructureShift(const double &high[], const double &low[],
                          const double &close[], int afterIndex,
                          int swingLookback, int total,
                          SStructureShift &out)
  {
   out.found = false;

   if(total < swingLookback * 2 + 10)
      return false;

   int highIdx[], lowIdx[];
   double highPrices[], lowPrices[];
   int highCount = FindSwingHighs(high, swingLookback, total, highIdx, highPrices);
   int lowCount  = FindSwingLows(low, swingLookback, total, lowIdx, lowPrices);

   // Scan bars newer than sweep (lower series index = more recent)
   for(int i = afterIndex - 1; i >= 1; i--)
     {
      // Bullish CHoCH: close breaks above recent swing high
      int lastHighIdx = GetSwingOlderThanBar(highIdx, highCount, i);
      if(lastHighIdx >= 0)
        {
         double lastHigh = highPrices[lastHighIdx];
         if(close[i] > lastHigh && close[i + 1] <= lastHigh)
           {
            out.found      = true;
            out.direction  = SMC_DIR_BULLISH;
            out.shiftIndex = i;
            out.breakLevel = lastHigh;
            return true;
           }
        }

      // Bearish CHoCH: close breaks below recent swing low
      int lastLowIdx = GetSwingOlderThanBar(lowIdx, lowCount, i);
      if(lastLowIdx >= 0)
        {
         double lastLow = lowPrices[lastLowIdx];
         if(close[i] < lastLow && close[i + 1] >= lastLow)
           {
            out.found      = true;
            out.direction  = SMC_DIR_BEARISH;
            out.shiftIndex = i;
            out.breakLevel = lastLow;
            return true;
           }
        }
     }

   return false;
  }

#endif
