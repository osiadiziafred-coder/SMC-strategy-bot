#ifndef XAUUSDM_SMC_SETUPS_MQH
#define XAUUSDM_SMC_SETUPS_MQH

bool FindLastBearishBefore(const int before_bar, const int search, double &top, double &bottom, datetime &t)
  {
   int n = ArraySize(g_m5);
   int end = MathMin(before_bar + search, n - 1);
   for(int i = before_bar + 1; i <= end; i++)
     {
      if(IsBearishCandle(g_m5[i]) || CandleBody(g_m5[i]) < g_atr_m5 * 0.15)
        {
         top = g_m5[i].high;
         bottom = g_m5[i].low;
         t = g_m5[i].time;
         if(i + 1 <= end && IsBearishCandle(g_m5[i + 1]))
           {
            top = MathMax(top, g_m5[i + 1].high);
            bottom = MathMin(bottom, g_m5[i + 1].low);
           }
         return true;
        }
     }
   if(before_bar + 1 < n)
     {
      top = g_m5[before_bar + 1].high;
      bottom = g_m5[before_bar + 1].low;
      t = g_m5[before_bar + 1].time;
      return true;
     }
   return false;
  }

bool FindLastBullishBefore(const int before_bar, const int search, double &top, double &bottom, datetime &t)
  {
   int n = ArraySize(g_m5);
   int end = MathMin(before_bar + search, n - 1);
   for(int i = before_bar + 1; i <= end; i++)
     {
      if(IsBullishCandle(g_m5[i]) || CandleBody(g_m5[i]) < g_atr_m5 * 0.15)
        {
         top = g_m5[i].high;
         bottom = g_m5[i].low;
         t = g_m5[i].time;
         if(i + 1 <= end && IsBullishCandle(g_m5[i + 1]))
           {
            top = MathMax(top, g_m5[i + 1].high);
            bottom = MathMin(bottom, g_m5[i + 1].low);
           }
         return true;
        }
     }
   if(before_bar + 1 < n)
     {
      top = g_m5[before_bar + 1].high;
      bottom = g_m5[before_bar + 1].low;
      t = g_m5[before_bar + 1].time;
      return true;
     }
   return false;
  }

bool M5RetestConfirmed(const int direction, const double ob_top, const double ob_bottom)
  {
   if(ArraySize(g_m5) < 3)
      return false;
   MqlRates c = g_m5[1];
   double buf = PointsToPrice(5);
   if(g_atr_m5 > 0.0)
      buf = MathMax(buf, g_atr_m5 * 0.05);

   if(direction > 0)
     {
      bool touched = (c.low <= ob_top + buf && c.low >= ob_bottom - buf) ||
                     (c.low <= ob_top && c.high >= ob_bottom);
      if(!touched)
         return false;
      if(c.close < ob_bottom - buf)
         return false;
      if(IsBearishCandle(c) && !IsRejectionCandle(c, 1))
         return false;
      return (IsBullishCandle(c) || IsRejectionCandle(c, 1));
     }

   bool touched = (c.high >= ob_bottom - buf && c.high <= ob_top + buf) ||
                  (c.high >= ob_bottom && c.low <= ob_top);
   if(!touched)
      return false;
   if(c.close > ob_top + buf)
      return false;
   if(IsBullishCandle(c) && !IsRejectionCandle(c, -1))
      return false;
   return (IsBearishCandle(c) || IsRejectionCandle(c, -1));
  }

bool IsChasingMove(const int direction, const double entry, const double tp)
  {
   if(tp == entry)
      return true;
   double px = (direction > 0 ? CurrentAsk() : CurrentBid());
   if(direction > 0)
     {
      if(px >= tp)
         return true;
      if(px > entry && (px - entry) > 0.35 * MathAbs(tp - entry))
         return true;
      if(ArraySize(g_m5) > 1)
        {
         double range = CandleRange(g_m5[1]);
         if(IsBullishCandle(g_m5[1]) && g_atr_m5 > 0.0 && range > 2.2 * g_atr_m5)
           {
            if(g_m5[1].close > entry && !M5RetestConfirmed(1, g_pending.ob_top, g_pending.ob_bottom))
               return true;
           }
        }
     }
   else
     {
      if(px <= tp)
         return true;
      if(px < entry && (entry - px) > 0.35 * MathAbs(entry - tp))
         return true;
      if(ArraySize(g_m5) > 1)
        {
         double range = CandleRange(g_m5[1]);
         if(IsBearishCandle(g_m5[1]) && g_atr_m5 > 0.0 && range > 2.2 * g_atr_m5)
           {
            if(g_m5[1].close < entry && !M5RetestConfirmed(-1, g_pending.ob_top, g_pending.ob_bottom))
               return true;
           }
        }
     }
   return false;
  }

double FindInvalidationLow()
  {
   double sl = 0.0;
   if(g_m5_low_count > 0)
      sl = g_m5_lows[0].price;
   if(g_bullish_sweep && g_last_bull_sweep.sweep_extreme > 0.0)
     {
      if(sl <= 0.0)
         sl = g_last_bull_sweep.sweep_extreme;
      else
         sl = MathMin(sl, g_last_bull_sweep.sweep_extreme);
     }
   if(g_pending.active && g_pending.sweep_extreme > 0.0)
      sl = (sl <= 0.0 ? g_pending.sweep_extreme : MathMin(sl, g_pending.sweep_extreme));
   if(g_active_demand.valid)
      sl = (sl <= 0.0 ? g_active_demand.bottom : MathMin(sl, g_active_demand.bottom));
   if(g_pending.active && g_pending.ob_bottom > 0.0)
      sl = (sl <= 0.0 ? g_pending.ob_bottom : MathMin(sl, g_pending.ob_bottom));
   if(sl <= 0.0 && ArraySize(g_m5) > 3)
     {
      sl = g_m5[1].low;
      int look = MathMin(8, ArraySize(g_m5) - 1);
      for(int i = 1; i <= look; i++)
         sl = MathMin(sl, g_m5[i].low);
     }
   return sl;
  }

double FindInvalidationHigh()
  {
   double sl = 0.0;
   if(g_m5_high_count > 0)
      sl = g_m5_highs[0].price;
   if(g_bearish_sweep && g_last_bear_sweep.sweep_extreme > 0.0)
     {
      if(sl <= 0.0)
         sl = g_last_bear_sweep.sweep_extreme;
      else
         sl = MathMax(sl, g_last_bear_sweep.sweep_extreme);
     }
   if(g_pending.active && g_pending.sweep_extreme > 0.0)
      sl = (sl <= 0.0 ? g_pending.sweep_extreme : MathMax(sl, g_pending.sweep_extreme));
   if(g_active_supply.valid)
      sl = (sl <= 0.0 ? g_active_supply.top : MathMax(sl, g_active_supply.top));
   if(g_pending.active && g_pending.ob_top > 0.0)
      sl = (sl <= 0.0 ? g_pending.ob_top : MathMax(sl, g_pending.ob_top));
   if(sl <= 0.0 && ArraySize(g_m5) > 3)
     {
      sl = g_m5[1].high;
      int look = MathMin(8, ArraySize(g_m5) - 1);
      for(int i = 1; i <= look; i++)
         sl = MathMax(sl, g_m5[i].high);
     }
   return sl;
  }

double CalculateStopLoss(const int direction)
  {
   double buffer = PointsToPrice(SLBufferPoints);
   if(g_atr_m5 > 0.0)
      buffer = MathMax(buffer, g_atr_m5 * 0.08);
   buffer = MathMax(buffer, g_stops_level * g_point);

   if(direction > 0)
     {
      double raw = FindInvalidationLow();
      if(raw <= 0.0)
         return 0.0;
      return NormalizePrice(raw - buffer);
     }
   double rawh = FindInvalidationHigh();
   if(rawh <= 0.0)
      return 0.0;
   return NormalizePrice(rawh + buffer);
  }

double NextBuyTarget(const double entry)
  {
   double best = 0.0;
   for(int i = 0; i < g_h1_high_count; i++)
     {
      if(g_h1_highs[i].price > entry)
        {
         if(best <= 0.0 || g_h1_highs[i].price < best)
            best = g_h1_highs[i].price;
        }
     }
   for(int i = 0; i < g_liq_high_count; i++)
     {
      if(g_liq_highs[i].price > entry)
        {
         if(best <= 0.0 || (g_liq_highs[i].major_level && g_liq_highs[i].price > best * 0.999))
           {
            if(best <= 0.0 || g_liq_highs[i].price < best || g_liq_highs[i].major_level)
              {
               if(best <= 0.0)
                  best = g_liq_highs[i].price;
               else
                  if(g_liq_highs[i].price > entry && g_liq_highs[i].price < best)
                     best = g_liq_highs[i].price;
              }
           }
        }
     }
   if(g_active_supply.valid && g_active_supply.bottom > entry)
     {
      if(best <= 0.0 || g_active_supply.bottom < best)
         best = g_active_supply.bottom;
     }
   if(best <= 0.0 && g_h1_range_high > entry)
      best = g_h1_range_high;
   return best;
  }

double NextSellTarget(const double entry)
  {
   double best = 0.0;
   for(int i = 0; i < g_h1_low_count; i++)
     {
      if(g_h1_lows[i].price < entry)
        {
         if(best <= 0.0 || g_h1_lows[i].price > best)
            best = g_h1_lows[i].price;
        }
     }
   for(int i = 0; i < g_liq_low_count; i++)
     {
      if(g_liq_low_count > 0 && g_liq_lows[i].price < entry)
        {
         if(best <= 0.0)
            best = g_liq_lows[i].price;
         else
            if(g_liq_lows[i].price > best)
               best = g_liq_lows[i].price;
        }
     }
   if(g_active_demand.valid && g_active_demand.top < entry)
     {
      if(best <= 0.0 || g_active_demand.top > best)
         best = g_active_demand.top;
     }
   if(best <= 0.0 && g_h1_range_low < entry && g_h1_range_low > 0.0)
      best = g_h1_range_low;
   return best;
  }

double CalculateTakeProfit(const int direction, const double entry, const double sl)
  {
   double risk = MathAbs(entry - sl);
   if(risk <= 0.0)
      return 0.0;
   double min_dist = risk * MinimumRiskReward;

   if(direction > 0)
     {
      double candidates[8];
      int n = 0;
      for(int i = 0; i < g_h1_high_count && n < 6; i++)
        {
         if(g_h1_highs[i].price > entry + min_dist * 0.98)
            candidates[n++] = g_h1_highs[i].price;
        }
      for(int i = 0; i < g_liq_high_count && n < 8; i++)
        {
         if(g_liq_highs[i].price > entry + min_dist * 0.98)
            candidates[n++] = g_liq_highs[i].price;
        }
      if(g_active_supply.valid && g_active_supply.bottom > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = g_active_supply.bottom;
      if(g_h1_range_high > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = g_h1_range_high;
      double nearest_buy = NextBuyTarget(entry);
      if(nearest_buy > entry + min_dist * 0.98 && n < 8)
         candidates[n++] = nearest_buy;

      double best = 0.0;
      for(int i = 0; i < n; i++)
        {
         if(candidates[i] <= entry)
            continue;
         if(best <= 0.0 || candidates[i] < best)
            best = candidates[i];
        }
      if(best > 0.0)
         return NormalizePrice(best);
      return 0.0;
     }

   double candidates_s[8];
   int ns = 0;
   for(int i = 0; i < g_h1_low_count && ns < 6; i++)
     {
      if(g_h1_lows[i].price < entry - min_dist * 0.98)
         candidates_s[ns++] = g_h1_lows[i].price;
     }
   for(int i = 0; i < g_liq_low_count && ns < 8; i++)
     {
      if(g_liq_lows[i].price < entry - min_dist * 0.98)
         candidates_s[ns++] = g_liq_lows[i].price;
     }
   if(g_active_demand.valid && g_active_demand.top < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = g_active_demand.top;
   if(g_h1_range_low > 0.0 && g_h1_range_low < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = g_h1_range_low;
   double nearest_sell = NextSellTarget(entry);
   if(nearest_sell > 0.0 && nearest_sell < entry - min_dist * 0.98 && ns < 8)
      candidates_s[ns++] = nearest_sell;

   double bests = 0.0;
   for(int i = 0; i < ns; i++)
     {
      if(candidates_s[i] >= entry)
         continue;
      if(bests <= 0.0 || candidates_s[i] > bests)
         bests = candidates_s[i];
     }
   if(bests > 0.0)
      return NormalizePrice(bests);
   return 0.0;
  }

double CalculateRiskReward(const double entry, const double sl, const double tp)
  {
   double risk = MathAbs(entry - sl);
   double reward = MathAbs(tp - entry);
   if(risk <= 0.0)
      return 0.0;
   return reward / risk;
  }

bool StopDistanceAcceptable(const double entry, const double sl)
  {
   double dist = MathAbs(entry - sl);
   if(dist <= 0.0)
      return false;
   int points = (int)MathRound(dist / g_point);
   if(points > MaxStopLossPoints)
      return false;
   int min_points = MathMax(g_stops_level, 5);
   if(points < min_points)
      return false;
   return true;
  }

bool FillM5EntryZone(const int direction, const int confirm_bar, double &ob_top, double &ob_bottom)
  {
   datetime dummy = 0;
   if(direction > 0)
      return FindLastBearishBefore(confirm_bar, 5, ob_top, ob_bottom, dummy);
   return FindLastBullishBefore(confirm_bar, 5, ob_top, ob_bottom, dummy);
  }

bool M5ConfirmationReady(const int direction, PendingSetup &ps)
  {
   if(!UseM5Confirmation)
      return true;

   bool disp = (direction > 0 ? g_m5_bullish_disp : g_m5_bearish_disp);
   bool bos  = (direction > 0 ? g_m5_bullish_bos  : g_m5_bearish_bos);
   bool mss  = (direction > 0 ? g_m5_bullish_mss  : g_m5_bearish_mss);
   bool rej  = false;
   if(ArraySize(g_m5) > 1)
      rej = IsRejectionCandle(g_m5[1], direction);

   if(!disp && !bos && !mss && !rej)
      return false;

   int confirm_bar = 1;
   if(mss && g_m5_mss_bar > 0)
      confirm_bar = g_m5_mss_bar;
   else
      if(bos && g_m5_bos_bar > 0)
         confirm_bar = g_m5_bos_bar;
      else
         if(disp && g_m5_disp_bar > 0)
            confirm_bar = g_m5_disp_bar;

   ps.had_displacement = disp;
   ps.had_bos = bos;
   ps.had_mss = mss;
   ps.had_rejection = rej;
   ps.bos_time = (bos ? g_m5_bos_time : 0);
   ps.mss_time = (mss ? g_m5_mss_time : 0);
   ps.bos_level = g_m5_bos_level;

   double top = 0.0;
   double bot = 0.0;
   if(!FillM5EntryZone(direction, confirm_bar, top, bot))
     {
      if(direction > 0 && g_m5_low_count > 0)
        {
         bot = g_m5_lows[0].price;
         top = bot + MathMax(g_atr_m5 * 0.4, PointsToPrice(50));
        }
      else
         if(direction < 0 && g_m5_high_count > 0)
           {
            top = g_m5_highs[0].price;
            bot = top - MathMax(g_atr_m5 * 0.4, PointsToPrice(50));
           }
         else
            return false;
     }
   ps.ob_top = top;
   ps.ob_bottom = bot;
   return true;
  }

bool PendingInvalidated()
  {
   if(!g_pending.active)
      return false;
   if(ArraySize(g_m5) < 2)
      return false;
   if(g_pending.direction > 0)
     {
      if(g_pending.sweep_extreme > 0.0 && g_m5[1].close < g_pending.sweep_extreme)
         return true;
      if(g_h1_bias == BIAS_BEARISH)
         return true;
     }
   else
     {
      if(g_pending.sweep_extreme > 0.0 && g_m5[1].close > g_pending.sweep_extreme)
         return true;
      if(g_h1_bias == BIAS_BULLISH)
         return true;
     }
   int age = iBarShift(g_symbol, InpEntryTF, g_pending.created_time, true);
   if(age < 0)
      age = SweepMaxAgeM5Bars + 1;
   if(age > SweepMaxAgeM5Bars)
      return true;
   return false;
  }

bool BuildTradePlan(const int direction, TradePlan &plan)
  {
   ZeroMemory(plan);
   plan.direction = direction;
   plan.entry = (direction > 0 ? CurrentAsk() : CurrentBid());
   plan.sl = CalculateStopLoss(direction);
   if(plan.sl <= 0.0)
     {
      plan.reason = "No trade: invalid structural stop";
      return false;
     }
   if(direction > 0 && plan.sl >= plan.entry)
     {
      plan.reason = "No trade: invalid stops";
      return false;
     }
   if(direction < 0 && plan.sl <= plan.entry)
     {
      plan.reason = "No trade: invalid stops";
      return false;
     }
   if(!StopDistanceAcceptable(plan.entry, plan.sl))
     {
      plan.reason = "No trade: stop exceeds MaxStopLossPoints";
      return false;
     }

   plan.tp = CalculateTakeProfit(direction, plan.entry, plan.sl);
   if(plan.tp <= 0.0)
     {
      plan.reason = StringFormat("No trade: RR below %.1f", MinimumRiskReward);
      return false;
     }
   plan.rr = CalculateRiskReward(plan.entry, plan.sl, plan.tp);
   g_last_rr = plan.rr;
   if(plan.rr + 1.0e-8 < MinimumRiskReward)
     {
      plan.reason = StringFormat("No trade: RR below %.1f", MinimumRiskReward);
      return false;
     }
   if(IsChasingMove(direction, plan.entry, plan.tp))
     {
      plan.reason = "No trade: chasing price after large move";
      return false;
     }
   plan.lots = CalculateLotSizeFromBalance(AccountInfoDouble(ACCOUNT_BALANCE));
   if(plan.lots < g_volume_min)
     {
      plan.reason = "No trade: invalid volume";
      return false;
     }
   plan.zone_top = g_pending.ob_top;
   plan.zone_bottom = g_pending.ob_bottom;
   plan.sweep_extreme = g_pending.sweep_extreme;
   plan.sweep_time = g_pending.sweep_time;
   plan.confirmation_time = g_m5[1].time;
   plan.setup_id = g_pending.setup_id;
   plan.valid = true;
   plan.reason = (direction > 0 ? "BUY setup confirmed" : "SELL setup confirmed");
   return true;
  }

bool ConfirmBuySetup(TradePlan &plan)
  {
   ZeroMemory(plan);
   if(g_h1_bias != BIAS_BULLISH)
     {
      LogReason("No trade: H1 bias unclear");
      return false;
     }
   if(RequireDiscountPremium && !PriceInDiscount() && !g_bullish_sweep && !(g_active_demand.valid && PriceNearZone(g_active_demand, 0.35)))
     {
      LogReason("No trade: price not in discount / demand area");
      return false;
     }
   if(!PriceAtBullishArea())
     {
      LogReason("No trade: price not at H1 demand/support/liquidity");
      return false;
     }
   if(UseLiquiditySweep && !g_bullish_sweep && !g_pending.active)
     {
      LogReason("No trade: liquidity sweep not detected");
      return false;
     }
   if(UseM5Confirmation)
     {
      if(!g_pending.active || g_pending.direction != 1)
        {
         PendingSetup ps;
         ZeroMemory(ps);
         if(!M5ConfirmationReady(1, ps))
           {
            g_ea_status = EA_STATUS_WAITING_M5;
            LogReason("No trade: M5 confirmation missing");
            return false;
           }
         g_pending = ps;
         g_pending.active = true;
         g_pending.direction = 1;
         g_pending.waiting_retest = RequireM5Retest;
         g_pending.created_time = TimeCurrent();
         if(g_bullish_sweep)
           {
            g_pending.sweep_time = g_last_bull_sweep.sweep_time;
            g_pending.sweep_extreme = g_last_bull_sweep.sweep_extreme;
            g_pending.liq_price = g_last_bull_sweep.price;
            g_pending.liq_time = g_last_bull_sweep.time;
           }
         g_pending.setup_id = BuildSetupId(1, g_pending.liq_time, g_pending.liq_price);
         if(SetupAlreadyUsed(g_pending.setup_id))
           {
            LogReason("No trade: setup already used");
            ResetPending();
            return false;
           }
        }

      if(RequireM5Retest)
        {
         if(!M5RetestConfirmed(1, g_pending.ob_top, g_pending.ob_bottom))
           {
            g_pending.waiting_retest = true;
            g_ea_status = EA_STATUS_WAITING_RETEST;
            LogReason("No trade: waiting M5 retest into demand/OB");
            return false;
           }
        }
     }

   if(!BuildTradePlan(1, plan))
     {
      LogReason(plan.reason);
      if(StringFind(plan.reason, "RR below") >= 0)
         MarkSetupUsed(g_pending.setup_id);
      return false;
     }
   return true;
  }

bool ConfirmSellSetup(TradePlan &plan)
  {
   ZeroMemory(plan);
   if(g_h1_bias != BIAS_BEARISH)
     {
      LogReason("No trade: H1 bias unclear");
      return false;
     }
   if(RequireDiscountPremium && !PriceInPremium() && !g_bearish_sweep && !(g_active_supply.valid && PriceNearZone(g_active_supply, 0.35)))
     {
      LogReason("No trade: price not in premium / supply area");
      return false;
     }
   if(!PriceAtBearishArea())
     {
      LogReason("No trade: price not at H1 supply/resistance/liquidity");
      return false;
     }
   if(UseLiquiditySweep && !g_bearish_sweep && !g_pending.active)
     {
      LogReason("No trade: liquidity sweep not detected");
      return false;
     }
   if(UseM5Confirmation)
     {
      if(!g_pending.active || g_pending.direction != -1)
        {
         PendingSetup ps;
         ZeroMemory(ps);
         if(!M5ConfirmationReady(-1, ps))
           {
            g_ea_status = EA_STATUS_WAITING_M5;
            LogReason("No trade: M5 confirmation missing");
            return false;
           }
         g_pending = ps;
         g_pending.active = true;
         g_pending.direction = -1;
         g_pending.waiting_retest = RequireM5Retest;
         g_pending.created_time = TimeCurrent();
         if(g_bearish_sweep)
           {
            g_pending.sweep_time = g_last_bear_sweep.sweep_time;
            g_pending.sweep_extreme = g_last_bear_sweep.sweep_extreme;
            g_pending.liq_price = g_last_bear_sweep.price;
            g_pending.liq_time = g_last_bear_sweep.time;
           }
         g_pending.setup_id = BuildSetupId(-1, g_pending.liq_time, g_pending.liq_price);
         if(SetupAlreadyUsed(g_pending.setup_id))
           {
            LogReason("No trade: setup already used");
            ResetPending();
            return false;
           }
        }

      if(RequireM5Retest)
        {
         if(!M5RetestConfirmed(-1, g_pending.ob_top, g_pending.ob_bottom))
           {
            g_pending.waiting_retest = true;
            g_ea_status = EA_STATUS_WAITING_RETEST;
            LogReason("No trade: waiting M5 retest into supply/OB");
            return false;
           }
        }
     }

   if(!BuildTradePlan(-1, plan))
     {
      LogReason(plan.reason);
      if(StringFind(plan.reason, "RR below") >= 0)
         MarkSetupUsed(g_pending.setup_id);
      return false;
     }
   return true;
  }

#endif
