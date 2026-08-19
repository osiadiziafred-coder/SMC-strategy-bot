#ifndef XAUUSDM_SMC_STRUCTURE_MQH
#define XAUUSDM_SMC_STRUCTURE_MQH

SwingPoint g_h1_highs[];
SwingPoint g_h1_lows[];
SwingPoint g_m5_highs[];
SwingPoint g_m5_lows[];
int        g_h1_high_count = 0;
int        g_h1_low_count  = 0;
int        g_m5_high_count = 0;
int        g_m5_low_count  = 0;
bool       g_h1_bullish_bos = false;
bool       g_h1_bearish_bos = false;
bool       g_h1_bullish_mss = false;
bool       g_h1_bearish_mss = false;
bool       g_m5_bullish_bos = false;
bool       g_m5_bearish_bos = false;
bool       g_m5_bullish_mss = false;
bool       g_m5_bearish_mss = false;
bool       g_m5_bullish_disp = false;
bool       g_m5_bearish_disp = false;
int        g_m5_bos_bar = -1;
int        g_m5_mss_bar = -1;
int        g_m5_disp_bar = -1;
double     g_m5_bos_level = 0.0;
double     g_h1_range_high = 0.0;
double     g_h1_range_low  = 0.0;
double     g_atr_h1 = 0.0;
double     g_atr_m5 = 0.0;
datetime   g_h1_bos_time = 0;
datetime   g_h1_mss_time = 0;
datetime   g_m5_bos_time = 0;
datetime   g_m5_mss_time = 0;

bool IsSwingHigh(const MqlRates &rates[], const int i, const int strength)
  {
   int n = ArraySize(rates);
   if(strength < 1)
      return false;
   if(i - strength < 1)
      return false;
   if(i + strength >= n)
      return false;
   double h = rates[i].high;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i - k].high >= h)
         return false;
      if(rates[i + k].high > h)
         return false;
     }
   return true;
  }

bool IsSwingLow(const MqlRates &rates[], const int i, const int strength)
  {
   int n = ArraySize(rates);
   if(strength < 1)
      return false;
   if(i - strength < 1)
      return false;
   if(i + strength >= n)
      return false;
   double l = rates[i].low;
   for(int k = 1; k <= strength; k++)
     {
      if(rates[i - k].low <= l)
         return false;
      if(rates[i + k].low < l)
         return false;
     }
   return true;
  }

int FindSwingHighs(const MqlRates &rates[], const int strength, SwingPoint &out[], const int max_count)
  {
   ArrayResize(out, 0);
   int n = ArraySize(rates);
   int count = 0;
   int start = strength + 1;
   int end = n - 1 - strength;
   for(int i = start; i <= end; i++)
     {
      if(!IsSwingHigh(rates, i, strength))
         continue;
      int idx = count;
      ArrayResize(out, count + 1);
      out[idx].time = rates[i].time;
      out[idx].price = rates[i].high;
      out[idx].bar_index = i;
      out[idx].is_high = true;
      out[idx].broken = false;
      out[idx].valid = true;
      count++;
      if(count >= max_count)
         break;
     }
   return count;
  }

int FindSwingLows(const MqlRates &rates[], const int strength, SwingPoint &out[], const int max_count)
  {
   ArrayResize(out, 0);
   int n = ArraySize(rates);
   int count = 0;
   int start = strength + 1;
   int end = n - 1 - strength;
   for(int i = start; i <= end; i++)
     {
      if(!IsSwingLow(rates, i, strength))
         continue;
      int idx = count;
      ArrayResize(out, count + 1);
      out[idx].time = rates[i].time;
      out[idx].price = rates[i].low;
      out[idx].bar_index = i;
      out[idx].is_high = false;
      out[idx].broken = false;
      out[idx].valid = true;
      count++;
      if(count >= max_count)
         break;
     }
   return count;
  }

void MarkBrokenSwings(const MqlRates &rates[], SwingPoint &highs[], const int high_count, SwingPoint &lows[], const int low_count)
  {
   int n = ArraySize(rates);
   for(int i = 0; i < high_count; i++)
     {
      highs[i].broken = false;
      int bar = highs[i].bar_index;
      for(int j = 1; j < bar && j < n; j++)
        {
         if(rates[j].close > highs[i].price)
           {
            highs[i].broken = true;
            break;
           }
        }
     }
   for(int i = 0; i < low_count; i++)
     {
      lows[i].broken = false;
      int bar = lows[i].bar_index;
      for(int j = 1; j < bar && j < n; j++)
        {
         if(rates[j].close < lows[i].price)
           {
            lows[i].broken = true;
            break;
           }
        }
     }
  }

ENUM_MARKET_BIAS ClassifyHHHL(const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count, const datetime before_time)
  {
   double recent_highs[3];
   double recent_lows[3];
   int hc = 0;
   int lc = 0;
   for(int i = 0; i < high_count && hc < 3; i++)
     {
      if(before_time > 0 && highs[i].time > before_time)
         continue;
      recent_highs[hc++] = highs[i].price;
     }
   for(int i = 0; i < low_count && lc < 3; i++)
     {
      if(before_time > 0 && lows[i].time > before_time)
         continue;
      recent_lows[lc++] = lows[i].price;
     }
   if(hc < 2 || lc < 2)
      return BIAS_NONE;

   bool hh = (recent_highs[0] > recent_highs[1]);
   bool lh = (recent_highs[0] < recent_highs[1]);
   bool hl = (recent_lows[0] > recent_lows[1]);
   bool ll = (recent_lows[0] < recent_lows[1]);

   if(hh && hl)
      return BIAS_BULLISH;
   if(lh && ll)
      return BIAS_BEARISH;
   return BIAS_NONE;
  }

bool FindMostRecentUnbrokenHigh(const SwingPoint &highs[], const int high_count, const int max_bar, SwingPoint &out)
  {
   for(int i = 0; i < high_count; i++)
     {
      if(highs[i].bar_index <= max_bar)
         continue;
      if(highs[i].broken)
         continue;
      out = highs[i];
      return true;
     }
   for(int i = 0; i < high_count; i++)
     {
      if(highs[i].bar_index <= max_bar)
         continue;
      out = highs[i];
      return true;
     }
   return false;
  }

bool FindMostRecentUnbrokenLow(const SwingPoint &lows[], const int low_count, const int max_bar, SwingPoint &out)
  {
   for(int i = 0; i < low_count; i++)
     {
      if(lows[i].bar_index <= max_bar)
         continue;
      if(lows[i].broken)
         continue;
      out = lows[i];
      return true;
     }
   for(int i = 0; i < low_count; i++)
     {
      if(lows[i].bar_index <= max_bar)
         continue;
      out = lows[i];
      return true;
     }
   return false;
  }

bool DetectClosedBreak(const MqlRates &rates[], const double level, const int direction, const int after_older_than_bar, int &break_bar)
  {
   int n = ArraySize(rates);
   int newest = 1;
   int oldest = after_older_than_bar - 1;
   if(oldest < newest)
      return false;
   if(oldest >= n)
      oldest = n - 1;
   for(int i = oldest; i >= newest; i--)
     {
      if(direction > 0 && rates[i].close > level)
        {
         break_bar = i;
         return true;
        }
      if(direction < 0 && rates[i].close < level)
        {
         break_bar = i;
         return true;
        }
     }
   return false;
  }

bool DetectBullishBOSOn(const MqlRates &rates[], const SwingPoint &highs[], const int high_count, const int fresh_bars, int &break_bar, double &level, datetime &break_time)
  {
   break_bar = -1;
   level = 0.0;
   break_time = 0;
   SwingPoint sh;
   ZeroMemory(sh);
   if(!FindMostRecentUnbrokenHigh(highs, high_count, 1, sh) && high_count > 0)
      sh = highs[0];
   else
     if(high_count <= 0)
        return false;
   int bar = -1;
   if(!DetectClosedBreak(rates, sh.price, 1, sh.bar_index, bar))
      return false;
   if(fresh_bars > 0 && bar > fresh_bars)
      return false;
   break_bar = bar;
   level = sh.price;
   break_time = rates[bar].time;
   return true;
  }

bool DetectBearishBOSOn(const MqlRates &rates[], const SwingPoint &lows[], const int low_count, const int fresh_bars, int &break_bar, double &level, datetime &break_time)
  {
   break_bar = -1;
   level = 0.0;
   break_time = 0;
   SwingPoint sl;
   ZeroMemory(sl);
   if(!FindMostRecentUnbrokenLow(lows, low_count, 1, sl) && low_count > 0)
      sl = lows[0];
   else
     if(low_count <= 0)
        return false;
   int bar = -1;
   if(!DetectClosedBreak(rates, sl.price, -1, sl.bar_index, bar))
      return false;
   if(fresh_bars > 0 && bar > fresh_bars)
      return false;
   break_bar = bar;
   level = sl.price;
   break_time = rates[bar].time;
   return true;
  }

bool DetectBullishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBullishBOSOn(g_h1, g_h1_highs, g_h1_high_count, 36, bar, level, t);
   g_h1_bullish_bos = ok;
   if(ok)
      g_h1_bos_time = t;
   return ok;
  }

bool DetectBearishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBearishBOSOn(g_h1, g_h1_lows, g_h1_low_count, 36, bar, level, t);
   g_h1_bearish_bos = ok;
   if(ok)
      g_h1_bos_time = t;
   return ok;
  }

bool DetectBullishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBullishBOSOn(g_h1, g_h1_highs, g_h1_high_count, 40, bar, level, t))
     {
      g_h1_bullish_mss = false;
      return false;
     }
   datetime before = g_h1[bar].time;
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, before);
   bool ok = (prior == BIAS_BEARISH || prior == BIAS_NONE);
   if(prior == BIAS_BULLISH)
      ok = false;
   if(ok)
     {
      bool had_ll = false;
      if(g_h1_low_count >= 2)
         had_ll = (g_h1_lows[0].price < g_h1_lows[1].price) || (prior == BIAS_BEARISH);
      ok = had_ll || (prior == BIAS_BEARISH);
     }
   g_h1_bullish_mss = ok;
   if(ok)
      g_h1_mss_time = t;
   return ok;
  }

bool DetectBearishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBearishBOSOn(g_h1, g_h1_lows, g_h1_low_count, 40, bar, level, t))
     {
      g_h1_bearish_mss = false;
      return false;
     }
   datetime before = g_h1[bar].time;
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, before);
   bool ok = (prior == BIAS_BULLISH);
   if(ok)
     {
      g_h1_bearish_mss = true;
      g_h1_mss_time = t;
      return true;
     }
   g_h1_bearish_mss = false;
   return false;
  }

bool DetectM5BullishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBullishBOSOn(g_m5, g_m5_highs, g_m5_high_count, InpM5ConfirmMaxBars, bar, level, t);
   g_m5_bullish_bos = ok;
   if(ok)
     {
      g_m5_bos_bar = bar;
      g_m5_bos_level = level;
      g_m5_bos_time = t;
     }
   return ok;
  }

bool DetectM5BearishBOS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   bool ok = DetectBearishBOSOn(g_m5, g_m5_lows, g_m5_low_count, InpM5ConfirmMaxBars, bar, level, t);
   g_m5_bearish_bos = ok;
   if(ok)
     {
      g_m5_bos_bar = bar;
      g_m5_bos_level = level;
      g_m5_bos_time = t;
     }
   return ok;
  }

bool DetectM5BullishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBullishBOSOn(g_m5, g_m5_highs, g_m5_high_count, InpM5ConfirmMaxBars, bar, level, t))
     {
      g_m5_bullish_mss = false;
      return false;
     }
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, g_m5[bar].time);
   bool ok = (prior == BIAS_BEARISH);
   g_m5_bullish_mss = ok;
   if(ok)
     {
      g_m5_mss_bar = bar;
      g_m5_mss_time = t;
      g_m5_bos_level = level;
     }
   return ok;
  }

bool DetectM5BearishMSS()
  {
   int bar = -1;
   double level = 0.0;
   datetime t = 0;
   if(!DetectBearishBOSOn(g_m5, g_m5_lows, g_m5_low_count, InpM5ConfirmMaxBars, bar, level, t))
     {
      g_m5_bearish_mss = false;
      return false;
     }
   ENUM_MARKET_BIAS prior = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, g_m5[bar].time);
   bool ok = (prior == BIAS_BULLISH);
   g_m5_bearish_mss = ok;
   if(ok)
     {
      g_m5_mss_bar = bar;
      g_m5_mss_time = t;
      g_m5_bos_level = level;
     }
   return ok;
  }

bool IsDisplacementCandle(const MqlRates &rates[], const int i, const int direction)
  {
   int n = ArraySize(rates);
   if(i < 1 || i >= n)
      return false;
   double body = CandleBody(rates[i]);
   double range = CandleRange(rates[i]);
   if(range <= 0.0)
      return false;
   double avg = AverageBody(rates, i, 20);
   if(avg <= 0.0)
      avg = range;
   if(body < InpDisplacementFactor * avg)
      return false;
   if(direction > 0)
     {
      if(!IsBullishCandle(rates[i]))
         return false;
      if((rates[i].close - rates[i].low) < 0.55 * range)
         return false;
     }
   else
     {
      if(!IsBearishCandle(rates[i]))
         return false;
      if((rates[i].high - rates[i].close) < 0.55 * range)
         return false;
     }
   return true;
  }

bool DetectM5Displacement(const int direction, int &disp_bar)
  {
   disp_bar = -1;
   int max_bar = InpM5ConfirmMaxBars;
   int n = ArraySize(g_m5);
   if(n < 5)
      return false;
   for(int i = 1; i <= max_bar && i < n; i++)
     {
      if(IsDisplacementCandle(g_m5, i, direction))
        {
         disp_bar = i;
         return true;
        }
     }
   return false;
  }

bool IsRejectionCandle(const MqlRates &r, const int direction)
  {
   double range = CandleRange(r);
   if(range <= 0.0)
      return false;
   if(direction > 0)
     {
      double lower = MathMin(r.open, r.close) - r.low;
      if(lower < 0.45 * range)
         return false;
      if(r.close < (r.low + 0.5 * range))
         return false;
      return true;
     }
   double upper = r.high - MathMax(r.open, r.close);
   if(upper < 0.45 * range)
      return false;
   if(r.close > (r.high - 0.5 * range))
      return false;
   return true;
  }

ENUM_MARKET_BIAS GetM5Bias()
  {
   ENUM_MARKET_BIAS seq = ClassifyHHHL(g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count, 0);
   if(g_m5_bullish_mss)
      return BIAS_BULLISH;
   if(g_m5_bearish_mss)
      return BIAS_BEARISH;
   if(g_m5_bullish_bos && seq != BIAS_BEARISH)
      return BIAS_BULLISH;
   if(g_m5_bearish_bos && seq != BIAS_BULLISH)
      return BIAS_BEARISH;
   return seq;
  }

ENUM_MARKET_BIAS GetH1Bias()
  {
   if(!UseMarketStructure)
      return BIAS_NONE;

   ENUM_MARKET_BIAS seq = ClassifyHHHL(g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, 0);

   bool bull_mss = DetectBullishMSS();
   bool bear_mss = DetectBearishMSS();
   bool bull_bos = DetectBullishBOS();
   bool bear_bos = DetectBearishBOS();

   if(bull_mss && !bear_mss)
      return BIAS_BULLISH;
   if(bear_mss && !bull_mss)
      return BIAS_BEARISH;

   if(seq == BIAS_BULLISH)
      return BIAS_BULLISH;
   if(seq == BIAS_BEARISH)
      return BIAS_BEARISH;

   if(bull_bos && !bear_bos)
      return BIAS_BULLISH;
   if(bear_bos && !bull_bos)
      return BIAS_BEARISH;

   return BIAS_NONE;
  }

void UpdateH1Range()
  {
   g_h1_range_high = 0.0;
   g_h1_range_low = 0.0;
   int n = ArraySize(g_h1);
   int look = MathMin(40, n - 1);
   if(look < 5)
      return;
   g_h1_range_high = g_h1[1].high;
   g_h1_range_low = g_h1[1].low;
   for(int i = 1; i <= look; i++)
     {
      if(g_h1[i].high > g_h1_range_high)
         g_h1_range_high = g_h1[i].high;
      if(g_h1[i].low < g_h1_range_low)
         g_h1_range_low = g_h1[i].low;
     }
   if(g_h1_high_count > 0 && g_h1_highs[0].price > g_h1_range_high)
      g_h1_range_high = g_h1_highs[0].price;
   if(g_h1_low_count > 0 && g_h1_lows[0].price < g_h1_range_low)
      g_h1_range_low = g_h1_lows[0].price;
  }

bool PriceInDiscount()
  {
   if(g_h1_range_high <= g_h1_range_low)
      return false;
   double eq = (g_h1_range_high + g_h1_range_low) * 0.5;
   return (CurrentMid() <= eq);
  }

bool PriceInPremium()
  {
   if(g_h1_range_high <= g_h1_range_low)
      return false;
   double eq = (g_h1_range_high + g_h1_range_low) * 0.5;
   return (CurrentMid() >= eq);
  }

bool AnalyzeStructure()
  {
   g_h1_high_count = FindSwingHighs(g_h1, InpH1SwingStrength, g_h1_highs, SMC_MAX_SWINGS);
   g_h1_low_count  = FindSwingLows(g_h1, InpH1SwingStrength, g_h1_lows, SMC_MAX_SWINGS);
   g_m5_high_count = FindSwingHighs(g_m5, InpM5SwingStrength, g_m5_highs, SMC_MAX_SWINGS);
   g_m5_low_count  = FindSwingLows(g_m5, InpM5SwingStrength, g_m5_lows, SMC_MAX_SWINGS);

   MarkBrokenSwings(g_h1, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count);
   MarkBrokenSwings(g_m5, g_m5_highs, g_m5_high_count, g_m5_lows, g_m5_low_count);

   g_atr_h1 = CalcATR(g_h1, 14, 1);
   g_atr_m5 = CalcATR(g_m5, 14, 1);
   UpdateH1Range();

   g_h1_bias = GetH1Bias();

   int disp_bar = -1;
   g_m5_bullish_disp = DetectM5Displacement(1, disp_bar);
   if(g_m5_bullish_disp)
      g_m5_disp_bar = disp_bar;
   g_m5_bearish_disp = DetectM5Displacement(-1, disp_bar);
   if(g_m5_bearish_disp && !g_m5_bullish_disp)
      g_m5_disp_bar = disp_bar;

   DetectM5BullishBOS();
   DetectM5BearishBOS();
   DetectM5BullishMSS();
   DetectM5BearishMSS();
   g_m5_bias = GetM5Bias();
   return true;
  }

#endif
