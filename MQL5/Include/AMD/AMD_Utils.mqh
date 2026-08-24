#ifndef AMD_UTILS_MQH
#define AMD_UTILS_MQH

#include "AMD_Config.mqh"

//+------------------------------------------------------------------+
//| Shared helpers: time windows, ATR, spread, volume, swings        |
//+------------------------------------------------------------------+

int TimeToMinutes(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return(dt.hour * 60 + dt.min);
  }

int MinutesOfDay(const int hour, const int minute)
  {
   return(hour * 60 + minute);
  }

bool TimeInWindow(const datetime t, const int startH, const int startM,
                  const int endH, const int endM)
  {
   const int nowMin = TimeToMinutes(t);
   const int start  = MinutesOfDay(startH, startM);
   const int end    = MinutesOfDay(endH, endM);
   if(start == end)
      return(true);
   if(start < end)
      return(nowMin >= start && nowMin < end);
   return(nowMin >= start || nowMin < end);
  }

datetime DateFloor(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return(StructToTime(dt));
  }

datetime MakeDateTime(const datetime dayRef, const int hour, const int minute)
  {
   MqlDateTime dt;
   TimeToStruct(DateFloor(dayRef), dt);
   dt.hour = hour;
   dt.min  = minute;
   dt.sec  = 0;
   return(StructToTime(dt));
  }

// Find the session window that contains `now`, or the most recently
// completed window if `now` is outside the session.
bool GetSessionBounds(const datetime now,
                      const int startH, const int startM,
                      const int endH, const int endM,
                      datetime &tStart, datetime &tEnd)
  {
   const int start = MinutesOfDay(startH, startM);
   const int end   = MinutesOfDay(endH, endM);
   const datetime day = DateFloor(now);
   const int nowMin = TimeToMinutes(now);

   if(start == end)
     {
      tStart = day;
      tEnd   = day + 24 * 60 * 60;
      return(true);
     }

   if(start < end)
     {
      datetime todayStart = day + start * 60;
      datetime todayEnd   = day + end * 60;
      if(nowMin >= start)
        {
         tStart = todayStart;
         tEnd   = todayEnd;
        }
      else
        {
         tStart = todayStart - 24 * 60 * 60;
         tEnd   = todayEnd - 24 * 60 * 60;
        }
      return(true);
     }

   // Overnight window, e.g. 20:00 -> 08:00
   if(nowMin >= start)
     {
      tStart = day + start * 60;
      tEnd   = day + 24 * 60 * 60 + end * 60;
     }
   else
     {
      tStart = day - 24 * 60 * 60 + start * 60;
      tEnd   = day + end * 60;
     }
   return(true);
  }

bool IsNewBar(const string symbol, const ENUM_TIMEFRAMES tf, datetime &lastBarTime)
  {
   datetime t[];
   if(CopyTime(symbol, tf, 0, 1, t) < 1)
      return(false);
   if(t[0] != lastBarTime)
     {
      lastBarTime = t[0];
      return(true);
     }
   return(false);
  }

double PointSize(const string symbol)
  {
   double p = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(p <= 0.0)
      p = _Point;
   return(p);
  }

double PointsToPrice(const string symbol, const double points)
  {
   return(points * PointSize(symbol));
  }

double PriceToPoints(const string symbol, const double priceDist)
  {
   const double p = PointSize(symbol);
   if(p <= 0.0)
      return(0.0);
   return(priceDist / p);
  }

int SymbolDigits(const string symbol)
  {
   return((int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
  }

double NormalizePrice(const string symbol, const double price)
  {
   return(NormalizeDouble(price, SymbolDigits(symbol)));
  }

double CurrentSpreadPoints(const string symbol)
  {
   const long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   return((double)spread);
  }

double CurrentAtr(const string symbol, const ENUM_TIMEFRAMES tf, const int period)
  {
   const int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE)
      return(0.0);
   double buf[];
   if(CopyBuffer(handle, 0, 0, 1, buf) < 1)
     {
      IndicatorRelease(handle);
      return(0.0);
     }
   const double v = buf[0];
   IndicatorRelease(handle);
   return(v);
  }

double AverageAtr(const string symbol, const ENUM_TIMEFRAMES tf, const int period, const int lookback)
  {
   const int handle = iATR(symbol, tf, period);
   if(handle == INVALID_HANDLE)
      return(0.0);
   double buf[];
   const int n = MathMax(lookback, 1);
   if(CopyBuffer(handle, 0, 0, n, buf) < n)
     {
      IndicatorRelease(handle);
      return(0.0);
     }
   double sum = 0.0;
   for(int i = 0; i < n; i++)
      sum += buf[i];
   IndicatorRelease(handle);
   return(sum / n);
  }

bool IsSwingHigh(const MqlRates &rates[], const int i, const int strength, const int total)
  {
   if(i < strength || i + strength >= total)
      return(false);
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i].high <= rates[i - k].high)
         return(false);
      if(rates[i].high <= rates[i + k].high)
         return(false);
     }
   return(true);
  }

bool IsSwingLow(const MqlRates &rates[], const int i, const int strength, const int total)
  {
   if(i < strength || i + strength >= total)
      return(false);
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i].low >= rates[i - k].low)
         return(false);
      if(rates[i].low >= rates[i + k].low)
         return(false);
     }
   return(true);
  }

int FindLatestSwingHigh(const MqlRates &rates[], const int strength, const int total,
                        const int fromShift, const int toShift)
  {
   const int start = MathMax(fromShift, strength);
   const int stop  = MathMin(toShift, total - strength - 1);
   for(int i = start; i <= stop; i++)
     {
      if(IsSwingHigh(rates, i, strength, total))
         return(i);
     }
   return(-1);
  }

int FindLatestSwingLow(const MqlRates &rates[], const int strength, const int total,
                       const int fromShift, const int toShift)
  {
   const int start = MathMax(fromShift, strength);
   const int stop  = MathMin(toShift, total - strength - 1);
   for(int i = start; i <= stop; i++)
     {
      if(IsSwingLow(rates, i, strength, total))
         return(i);
     }
   return(-1);
  }

bool DetectFvg(const MqlRates &rates[], const int mid, const int total,
               const bool bullish, double &top, double &bottom)
  {
   if(mid < 1 || mid + 1 >= total)
      return(false);
   if(bullish)
     {
      if(rates[mid - 1].low > rates[mid + 1].high)
        {
         bottom = rates[mid + 1].high;
         top    = rates[mid - 1].low;
         return(top > bottom);
        }
     }
   else
     {
      if(rates[mid - 1].high < rates[mid + 1].low)
        {
         top    = rates[mid + 1].low;
         bottom = rates[mid - 1].high;
         return(top > bottom);
        }
     }
   return(false);
  }

double CandleBody(const MqlRates &bar)
  {
   return(MathAbs(bar.close - bar.open));
  }

bool IsDisplacement(const MqlRates &bar, const double atr, const double mult)
  {
   if(atr <= 0.0)
      return(true);
   return(CandleBody(bar) >= atr * mult);
  }

int CountWeekday(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return(dt.day_of_week); // 0 Sunday ... 5 Friday
  }

bool IsFridayCloseTime(const datetime t, const int hour, const int minute)
  {
   if(CountWeekday(t) != 5)
      return(false);
   return(TimeToMinutes(t) >= MinutesOfDay(hour, minute));
  }

string PhaseToString(const ENUM_AMD_PHASE phase)
  {
   switch(phase)
     {
      case PHASE_IDLE:            return("IDLE");
      case PHASE_ACCUMULATION:    return("ACCUMULATION");
      case PHASE_RANGE_SET:       return("RANGE SET");
      case PHASE_MANIPULATION:    return("MANIPULATION");
      case PHASE_CONFIRMATION:    return("CONFIRMATION");
      case PHASE_IN_TRADE:        return("IN TRADE");
      case PHASE_CYCLE_COMPLETE:  return("CYCLE COMPLETE");
      case PHASE_RANGE_INVALID:   return("RANGE INVALID");
     }
   return("UNKNOWN");
  }

string DirToString(const ENUM_TRADE_DIR dir)
  {
   if(dir == DIR_BUY)
      return("BUY");
   if(dir == DIR_SELL)
      return("SELL");
   return("NONE");
  }

string SessionKindToString(const ENUM_SESSION_KIND kind)
  {
   switch(kind)
     {
      case SESSION_ASIA:     return("ASIA (ACCUMULATION)");
      case SESSION_LONDON:   return("LONDON (MANIPULATION)");
      case SESSION_NEWYORK:  return("NEW YORK (DISTRIBUTION)");
      case SESSION_CUSTOM:   return("CUSTOM");
     }
   return("OFF-SESSION");
  }

string TfToString(const ENUM_TIMEFRAMES tf)
  {
   switch(tf)
     {
      case PERIOD_M15: return("M15");
      case PERIOD_M30: return("M30");
      case PERIOD_H1:  return("H1");
      case PERIOD_H4:  return("H4");
      case PERIOD_D1:  return("D1");
     }
   return(EnumToString(tf));
  }

int ColorLuma(const color clr)
  {
   const int r = (int)(clr & 0xFF);
   const int g = (int)((clr >> 8) & 0xFF);
   const int b = (int)((clr >> 16) & 0xFF);
   return(r + g + b);
  }

void DebugPrint(const SAmdConfig &cfg, const string msg)
  {
   if(cfg.debugLog)
      Print("[AMD] ", msg);
  }

#endif
