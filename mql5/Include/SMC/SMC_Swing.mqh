//+------------------------------------------------------------------+
//| SMC_Swing.mqh — Swing high / low detection                       |
//+------------------------------------------------------------------+
#ifndef SMC_SWING_MQH
#define SMC_SWING_MQH
#include "SMC_Types.mqh"

//+------------------------------------------------------------------+
//| With AS_SERIES: index 0 = newest bar, higher index = older bar    |
//+------------------------------------------------------------------+
bool IsSwingHigh(const double &high[], int i, int lookback, int total)
  {
   if(i < lookback || i + lookback >= total)
      return false;

   double h = high[i];
   for(int j = i - lookback; j <= i + lookback; j++)
     {
      if(j == i)
         continue;
      if(high[j] >= h)
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
bool IsSwingLow(const double &low[], int i, int lookback, int total)
  {
   if(i < lookback || i + lookback >= total)
      return false;

   double l = low[i];
   for(int j = i - lookback; j <= i + lookback; j++)
     {
      if(j == i)
         continue;
      if(low[j] <= l)
         return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
int FindSwingHighs(const double &high[], int lookback, int total,
                   int &outIndices[], double &outPrices[], int maxSwings = 50)
  {
   ArrayResize(outIndices, 0);
   ArrayResize(outPrices, 0);
   int count = 0;

   for(int i = lookback; i < total - lookback; i++)
     {
      if(IsSwingHigh(i, lookback, total))
        {
         if(count < maxSwings)
           {
            ArrayResize(outIndices, count + 1);
            ArrayResize(outPrices, count + 1);
            outIndices[count] = i;
            outPrices[count]  = high[i];
            count++;
           }
        }
     }
   return count;
  }

//+------------------------------------------------------------------+
int FindSwingLows(const double &low[], int lookback, int total,
                  int &outIndices[], double &outPrices[], int maxSwings = 50)
  {
   ArrayResize(outIndices, 0);
   ArrayResize(outPrices, 0);
   int count = 0;

   for(int i = lookback; i < total - lookback; i++)
     {
      if(IsSwingLow(i, lookback, total))
        {
         if(count < maxSwings)
           {
            ArrayResize(outIndices, count + 1);
            ArrayResize(outPrices, count + 1);
            outIndices[count] = i;
            outPrices[count]  = low[i];
            count++;
           }
        }
     }
   return count;
  }

//+------------------------------------------------------------------+
//| Most recent swing older than barIndex (higher series index)      |
//+------------------------------------------------------------------+
int GetSwingOlderThanBar(const int &indices[], int count, int barIndex)
  {
   int result  = -1;
   int bestIdx = INT_MAX;
   for(int i = 0; i < count; i++)
     {
      if(indices[i] > barIndex && indices[i] < bestIdx)
        {
         bestIdx = indices[i];
         result  = i;
        }
     }
   return result;
  }

//+------------------------------------------------------------------+
//| Get two most recent swings (lowest series indices)               |
//+------------------------------------------------------------------+
bool GetTwoMostRecentSwings(const int &indices[], const double &prices[],
                            int count, int &idx1, int &idx2,
                            double &price1, double &price2)
  {
   idx1 = -1;
   idx2 = -1;
   if(count < 2)
      return false;

   int best1 = INT_MAX;
   int best2 = INT_MAX;

   for(int i = 0; i < count; i++)
     {
      if(indices[i] < best1)
        {
         best2 = best1;
         idx2  = idx1;
         price2 = price1;
         best1 = indices[i];
         idx1  = i;
         price1 = prices[i];
        }
      else if(indices[i] < best2)
        {
         best2 = indices[i];
         idx2  = i;
         price2 = prices[i];
        }
     }

   return (idx1 >= 0 && idx2 >= 0);
  }

#endif
