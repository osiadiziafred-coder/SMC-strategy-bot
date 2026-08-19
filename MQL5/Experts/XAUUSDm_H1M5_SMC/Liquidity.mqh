#ifndef XAUUSDM_SMC_LIQUIDITY_MQH
#define XAUUSDM_SMC_LIQUIDITY_MQH

LiquidityLevel g_liq_highs[];
LiquidityLevel g_liq_lows[];
int            g_liq_high_count = 0;
int            g_liq_low_count  = 0;
Zone           g_demand_zones[];
Zone           g_supply_zones[];
int            g_demand_count = 0;
int            g_supply_count = 0;
Zone           g_active_demand;
Zone           g_active_supply;
LiquidityLevel g_last_bull_sweep;
LiquidityLevel g_last_bear_sweep;
bool           g_bullish_sweep = false;
bool           g_bearish_sweep = false;

double EqualTolerance()
  {
   double by_points = PointsToPrice(EqualLevelPoints);
   double by_atr = g_atr_h1 * 0.12;
   if(by_atr <= 0.0)
      return by_points;
   return MathMax(by_points, by_atr);
  }

bool AddLiquidityLevel(LiquidityLevel &arr[], int &count, const datetime t, const double price, const int bar, const bool is_high, const bool equal_level, const bool major_level)
  {
   for(int i = 0; i < count; i++)
     {
      if(MathAbs(arr[i].price - price) <= EqualTolerance())
        {
         arr[i].equal_level = true;
         if(major_level)
            arr[i].major_level = true;
         return true;
        }
     }
   if(count >= SMC_MAX_LIQ)
      return false;
   ArrayResize(arr, count + 1);
   arr[count].time = t;
   arr[count].price = price;
   arr[count].is_high = is_high;
   arr[count].equal_level = equal_level;
   arr[count].major_level = major_level;
   arr[count].swept = false;
   arr[count].sweep_time = 0;
   arr[count].sweep_extreme = 0.0;
   arr[count].bar_index = bar;
   arr[count].valid = true;
   count++;
   return true;
  }

void DetectEqualLevels(const SwingPoint &swings[], const int swing_count, LiquidityLevel &arr[], int &count, const bool is_high)
  {
   double tol = EqualTolerance();
   for(int i = 0; i < swing_count; i++)
     {
      for(int j = i + 1; j < swing_count; j++)
        {
         if(MathAbs(swings[i].price - swings[j].price) <= tol)
           {
            AddLiquidityLevel(arr, count, swings[i].time, swings[i].price, swings[i].bar_index, is_high, true, true);
            break;
           }
        }
     }
  }

void DetectConsolidationLiquidity()
  {
   int n = ArraySize(g_h1);
   int window = 12;
   if(n < window + 2)
      return;
   double max_h = g_h1[1].high;
   double min_l = g_h1[1].low;
   datetime high_t = g_h1[1].time;
   datetime low_t = g_h1[1].time;
   int high_bar = 1;
   int low_bar = 1;
   for(int i = 1; i <= window; i++)
     {
      if(g_h1[i].high >= max_h)
        {
         max_h = g_h1[i].high;
         high_t = g_h1[i].time;
         high_bar = i;
        }
      if(g_h1[i].low <= min_l)
        {
         min_l = g_h1[i].low;
         low_t = g_h1[i].time;
         low_bar = i;
        }
     }
   double rng = max_h - min_l;
   if(g_atr_h1 > 0.0 && rng < 1.15 * g_atr_h1)
     {
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, high_t, max_h, high_bar, true, false, true);
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, low_t, min_l, low_bar, false, false, true);
     }
  }

void BuildLiquidityLevels()
  {
   g_liq_high_count = 0;
   g_liq_low_count = 0;
   ArrayResize(g_liq_highs, 0);
   ArrayResize(g_liq_lows, 0);

   int swing_use = MathMin(12, g_h1_high_count);
   for(int i = 0; i < swing_use; i++)
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, g_h1_highs[i].time, g_h1_highs[i].price, g_h1_highs[i].bar_index, true, false, (i == 0));

   swing_use = MathMin(12, g_h1_low_count);
   for(int i = 0; i < swing_use; i++)
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, g_h1_lows[i].time, g_h1_lows[i].price, g_h1_lows[i].bar_index, false, false, (i == 0));

   DetectEqualLevels(g_h1_highs, g_h1_high_count, g_liq_highs, g_liq_high_count, true);
   DetectEqualLevels(g_h1_lows, g_h1_low_count, g_liq_lows, g_liq_low_count, false);

   int n = ArraySize(g_h1);
   if(n > 25)
     {
      double major_high = g_h1[1].high;
      double major_low = g_h1[1].low;
      datetime ht = g_h1[1].time;
      datetime lt = g_h1[1].time;
      int hb = 1;
      int lb = 1;
      int look = MathMin(80, n - 1);
      for(int i = 1; i <= look; i++)
        {
         if(g_h1[i].high >= major_high)
           {
            major_high = g_h1[i].high;
            ht = g_h1[i].time;
            hb = i;
           }
         if(g_h1[i].low <= major_low)
           {
            major_low = g_h1[i].low;
            lt = g_h1[i].time;
            lb = i;
           }
        }
      AddLiquidityLevel(g_liq_highs, g_liq_high_count, ht, major_high, hb, true, false, true);
      AddLiquidityLevel(g_liq_lows, g_liq_low_count, lt, major_low, lb, false, false, true);
     }

   DetectConsolidationLiquidity();
  }

bool LevelIsMeaningful(const LiquidityLevel &lv)
  {
   if(!lv.valid)
      return false;
   return (lv.equal_level || lv.major_level || lv.bar_index > 0);
  }

bool DetectSweepAgainstLevel(const LiquidityLevel &lv, const int direction, LiquidityLevel &result)
  {
   int n = ArraySize(g_m5);
   int max_age = SweepMaxAgeM5Bars;
   if(n < 4)
      return false;

   double min_pierce = PointsToPrice(MathMax(20, SweepMinPiercePoints));
   if(g_atr_m5 > 0.0)
      min_pierce = MathMax(min_pierce, g_atr_m5 * 0.08);

   double max_close_beyond = min_pierce * 0.35;
   double level = lv.price;

   for(int i = 1; i <= max_age && i < n; i++)
     {
      if(direction > 0)
        {
         double extreme = g_m5[i].low;
         if(g_m5[i].low >= level - min_pierce * 0.25)
            continue;
         if(level - g_m5[i].low < min_pierce)
            continue;

         bool reclaimed = false;
         datetime reclaim_time = 0;
         double reclaim_close = 0.0;
         int last = MathMin(i, 4);
         for(int k = i; k >= 1 && k >= i - 3; k--)
           {
            if(g_m5[k].close > level - max_close_beyond)
              {
               reclaimed = true;
               reclaim_time = g_m5[k].time;
               reclaim_close = g_m5[k].close;
               if(k < i)
                  extreme = MathMin(extreme, g_m5[i].low);
              }
           }
         if(!reclaimed)
            continue;
         if(reclaim_close <= extreme)
            continue;

         result = lv;
         result.swept = true;
         result.sweep_time = reclaim_time;
         result.sweep_extreme = MathMin(g_m5[i].low, extreme);
         return true;
        }
      else
        {
         double extreme = g_m5[i].high;
         if(g_m5[i].high <= level + min_pierce * 0.25)
            continue;
         if(g_m5[i].high - level < min_pierce)
            continue;

         bool reclaimed = false;
         datetime reclaim_time = 0;
         double reclaim_close = 0.0;
         for(int k = i; k >= 1 && k >= i - 3; k--)
           {
            if(g_m5[k].close < level + max_close_beyond)
              {
               reclaimed = true;
               reclaim_time = g_m5[k].time;
               reclaim_close = g_m5[k].close;
              }
           }
         if(!reclaimed)
            continue;
         if(reclaim_close >= extreme)
            continue;

         result = lv;
         result.swept = true;
         result.sweep_time = reclaim_time;
         result.sweep_extreme = MathMax(g_m5[i].high, extreme);
         return true;
        }
     }
   return false;
  }

bool DetectLiquiditySweep(const int direction, LiquidityLevel &out_sweep)
  {
   ZeroMemory(out_sweep);
   if(!UseLiquiditySweep)
      return false;

   if(direction > 0)
     {
      for(int i = 0; i < g_liq_low_count; i++)
        {
         if(!LevelIsMeaningful(g_liq_lows[i]))
            continue;
         LiquidityLevel tmp;
         if(DetectSweepAgainstLevel(g_liq_lows[i], 1, tmp))
           {
            out_sweep = tmp;
            return true;
           }
        }
     }
   else
     {
      for(int i = 0; i < g_liq_high_count; i++)
        {
         if(!LevelIsMeaningful(g_liq_highs[i]))
            continue;
         LiquidityLevel tmp;
         if(DetectSweepAgainstLevel(g_liq_highs[i], -1, tmp))
           {
            out_sweep = tmp;
            return true;
           }
        }
     }
   return false;
  }

int CountZoneTests(const MqlRates &rates[], const Zone &z, const int from_bar)
  {
   int tests = 0;
   bool inside = false;
   for(int i = from_bar - 1; i >= 1; i--)
     {
      bool touch = (rates[i].low <= z.top && rates[i].high >= z.bottom);
      if(touch && !inside)
        {
         tests++;
         inside = true;
        }
      else
         if(!touch)
            inside = false;
     }
   return tests;
  }

bool ZoneFullyMitigated(const MqlRates &rates[], const Zone &z, const int from_bar)
  {
   for(int i = from_bar - 1; i >= 1; i--)
     {
      if(z.is_demand && rates[i].close < z.bottom)
         return true;
      if(!z.is_demand && rates[i].close > z.top)
         return true;
     }
   return false;
  }

bool BuildZoneFromImpulse(const MqlRates &rates[], const int impulse_bar, const bool is_demand, Zone &z)
  {
   int n = ArraySize(rates);
   if(impulse_bar + 1 >= n)
      return false;

   int search_end = MathMin(impulse_bar + 6, n - 1);
   int found = -1;
   double top = 0.0;
   double bottom = 0.0;
   datetime t = 0;

   for(int j = impulse_bar + 1; j <= search_end; j++)
     {
      if(is_demand && IsBearishCandle(rates[j]))
        {
         if(found < 0)
           {
            found = j;
            top = rates[j].high;
            bottom = rates[j].low;
            t = rates[j].time;
           }
         else
           {
            top = MathMax(top, rates[j].high);
            bottom = MathMin(bottom, rates[j].low);
           }
        }
      else
         if(!is_demand && IsBullishCandle(rates[j]))
           {
            if(found < 0)
              {
               found = j;
               top = rates[j].high;
               bottom = rates[j].low;
               t = rates[j].time;
              }
            else
              {
               top = MathMax(top, rates[j].high);
               bottom = MathMin(bottom, rates[j].low);
              }
           }
         else
            if(found >= 0)
               break;
     }

   if(found < 0)
     {
      int j = impulse_bar + 1;
      found = j;
      top = rates[j].high;
      bottom = rates[j].low;
      t = rates[j].time;
     }

   if(top - bottom <= 0.0)
      return false;

   z.time = t;
   z.bar_index = found;
   z.top = top;
   z.bottom = bottom;
   z.is_demand = is_demand;
   z.from_displacement = true;
   z.valid = true;
   z.mitigated = ZoneFullyMitigated(rates, z, found);
   z.tests = CountZoneTests(rates, z, found);
   if(z.mitigated)
      z.valid = false;
   if(z.tests > ZoneMaxTests)
      z.valid = false;
   return z.valid;
  }

bool ImpulseBrokeStructure(const MqlRates &rates[], const int impulse_bar, const bool bullish, const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count)
  {
   if(bullish)
     {
      for(int i = 0; i < high_count; i++)
        {
         if(highs[i].bar_index <= impulse_bar)
            continue;
         if(rates[impulse_bar].close > highs[i].price)
            return true;
        }
      if(impulse_bar + 3 < ArraySize(rates))
        {
         double prior_high = rates[impulse_bar + 1].high;
         for(int k = impulse_bar + 1; k <= impulse_bar + 8 && k < ArraySize(rates); k++)
            prior_high = MathMax(prior_high, rates[k].high);
         if(rates[impulse_bar].close > prior_high)
            return true;
        }
     }
   else
     {
      for(int i = 0; i < low_count; i++)
        {
         if(lows[i].bar_index <= impulse_bar)
            continue;
         if(rates[impulse_bar].close < lows[i].price)
            return true;
        }
      if(impulse_bar + 3 < ArraySize(rates))
        {
         double prior_low = rates[impulse_bar + 1].low;
         for(int k = impulse_bar + 1; k <= impulse_bar + 8 && k < ArraySize(rates); k++)
            prior_low = MathMin(prior_low, rates[k].low);
         if(rates[impulse_bar].close < prior_low)
            return true;
        }
     }
   return false;
  }

int CollectZones(const MqlRates &rates[], const bool is_demand, const SwingPoint &highs[], const int high_count, const SwingPoint &lows[], const int low_count, Zone &out[], const int max_scan)
  {
   ArrayResize(out, 0);
   int count = 0;
   int n = ArraySize(rates);
   int scan = MathMin(max_scan, n - 8);
   int dir = is_demand ? 1 : -1;
   for(int i = 2; i <= scan; i++)
     {
      if(!IsDisplacementCandle(rates, i, dir))
         continue;
      if(!ImpulseBrokeStructure(rates, i, is_demand, highs, high_count, lows, low_count))
         continue;
      Zone z;
      ZeroMemory(z);
      if(!BuildZoneFromImpulse(rates, i, is_demand, z))
         continue;
      ArrayResize(out, count + 1);
      out[count] = z;
      count++;
      if(count >= SMC_MAX_ZONES)
         break;
     }
   return count;
  }

bool FindDemandZone(Zone &out_zone)
  {
   ZeroMemory(out_zone);
   if(!UseOrderBlocks)
      return false;
   g_demand_count = CollectZones(g_h1, true, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, g_demand_zones, 80);
   if(g_demand_count <= 0)
      return false;
   out_zone = g_demand_zones[0];
   return out_zone.valid;
  }

bool FindSupplyZone(Zone &out_zone)
  {
   ZeroMemory(out_zone);
   if(!UseOrderBlocks)
      return false;
   g_supply_count = CollectZones(g_h1, false, g_h1_highs, g_h1_high_count, g_h1_lows, g_h1_low_count, g_supply_zones, 80);
   if(g_supply_count <= 0)
      return false;
   out_zone = g_supply_zones[0];
   return out_zone.valid;
  }

bool PriceNearZone(const Zone &z, const double atr_mult)
  {
   if(!z.valid)
      return false;
   double px = CurrentMid();
   if(px <= z.top && px >= z.bottom)
      return true;
   double buf = 0.0;
   if(g_atr_h1 > 0.0)
      buf = g_atr_h1 * atr_mult;
   buf = MathMax(buf, PointsToPrice(ZoneApproachPoints));
   if(px < z.bottom && (z.bottom - px) <= buf)
      return true;
   if(px > z.top && (px - z.top) <= buf)
      return true;
   return false;
  }

bool PriceNearLevel(const double level, const double atr_mult)
  {
   double px = CurrentMid();
   double buf = PointsToPrice(ZoneApproachPoints);
   if(g_atr_h1 > 0.0)
      buf = MathMax(buf, g_atr_h1 * atr_mult);
   return (MathAbs(px - level) <= buf);
  }

bool PriceAtBullishArea()
  {
   if(g_active_demand.valid && PriceNearZone(g_active_demand, 0.35))
      return true;
   if(g_h1_low_count > 0 && PriceNearLevel(g_h1_lows[0].price, 0.30))
      return true;
   if(g_liq_low_count > 0 && PriceNearLevel(g_liq_lows[0].price, 0.30))
      return true;
   if(g_bullish_sweep)
      return true;
   if(RequireDiscountPremium && PriceInDiscount())
      return true;
   if(!RequireDiscountPremium && PriceInDiscount())
      return true;
   return false;
  }

bool PriceAtBearishArea()
  {
   if(g_active_supply.valid && PriceNearZone(g_active_supply, 0.35))
      return true;
   if(g_h1_high_count > 0 && PriceNearLevel(g_h1_highs[0].price, 0.30))
      return true;
   if(g_liq_high_count > 0 && PriceNearLevel(g_liq_highs[0].price, 0.30))
      return true;
   if(g_bearish_sweep)
      return true;
   if(RequireDiscountPremium && PriceInPremium())
      return true;
   if(!RequireDiscountPremium && PriceInPremium())
      return true;
   return false;
  }

void AnalyzeLiquidityAndZones()
  {
   BuildLiquidityLevels();
   FindDemandZone(g_active_demand);
   FindSupplyZone(g_active_supply);

   g_bullish_sweep = DetectLiquiditySweep(1, g_last_bull_sweep);
   g_bearish_sweep = DetectLiquiditySweep(-1, g_last_bear_sweep);
  }

#endif
