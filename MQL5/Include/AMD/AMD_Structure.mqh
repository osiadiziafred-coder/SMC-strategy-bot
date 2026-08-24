#ifndef AMD_STRUCTURE_MQH
#define AMD_STRUCTURE_MQH

#include "AMD_Utils.mqh"

//+------------------------------------------------------------------+
//| Higher-timeframe bias and lower-timeframe MSS / BOS / CISD / FVG |
//+------------------------------------------------------------------+
class CStructureEngine
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;

public:
                     CStructureEngine(void) { m_symbol = _Symbol; }

   void              Init(const SAmdConfig &cfg, const string symbol)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
     }

   SHtfBias          ComputeHtfBias(void) const
     {
      SHtfBias bias;
      bias.dir          = DIR_NONE;
      bias.lastSwingHigh= 0;
      bias.lastSwingLow = 0;
      bias.tLastBos     = 0;

      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      const int copied = CopyRates(m_symbol, m_cfg.htf, 0, m_cfg.htfLookback, rates);
      if(copied < m_cfg.swingStrength * 4 + 5)
         return(bias);

      const int strength = m_cfg.swingStrength;
      int lastSH = -1, prevSH = -1, lastSL = -1, prevSL = -1;
      for(int i = strength; i < copied - strength; i++)
        {
         if(lastSH < 0 && IsSwingHigh(rates, i, strength, copied))
            lastSH = i;
         else if(lastSH >= 0 && prevSH < 0 && IsSwingHigh(rates, i, strength, copied))
            prevSH = i;
         if(lastSL < 0 && IsSwingLow(rates, i, strength, copied))
            lastSL = i;
         else if(lastSL >= 0 && prevSL < 0 && IsSwingLow(rates, i, strength, copied))
            prevSL = i;
         if(lastSH >= 0 && lastSL >= 0 && prevSH >= 0 && prevSL >= 0)
            break;
        }

      if(lastSH >= 0)
         bias.lastSwingHigh = rates[lastSH].high;
      if(lastSL >= 0)
         bias.lastSwingLow = rates[lastSL].low;

      // Most recent confirmed BOS: price closed beyond prior swing
      // Scan from newest closed bar
      for(int i = 1; i < copied - strength; i++)
        {
         const int sh = FindLatestSwingHigh(rates, strength, copied, i + 1, copied - strength - 1);
         const int sl = FindLatestSwingLow(rates, strength, copied, i + 1, copied - strength - 1);
         if(sh >= 0 && rates[i].close > rates[sh].high)
           {
            bias.dir      = DIR_BUY;
            bias.tLastBos = rates[i].time;
            break;
           }
         if(sl >= 0 && rates[i].close < rates[sl].low)
           {
            bias.dir      = DIR_SELL;
            bias.tLastBos = rates[i].time;
            break;
           }
        }
      return(bias);
     }

   bool              DirectionAllowed(const ENUM_TRADE_DIR setupDir, const SHtfBias &bias) const
     {
      if(m_cfg.htfBiasMode == BIAS_OFF || bias.dir == DIR_NONE)
         return(true);
      if(m_cfg.htfBiasMode == BIAS_WITH_TREND)
         return(setupDir == bias.dir);
      if(m_cfg.htfBiasMode == BIAS_COUNTER_TREND)
         return(setupDir != bias.dir);
      return(true);
     }

   bool              ConfirmShift(const MqlRates &ltf[], const int total,
                                  const SSweepEvent &sweep, const SSessionRange &range,
                                  const double atr, SStructureShift &mss) const
     {
      ZeroMemory(mss);
      if(!sweep.active || !sweep.returned)
         return(false);

      const int strength = MathMax(m_cfg.swingStrength, 1);
      int sweepShift = -1;
      for(int i = 1; i < total; i++)
        {
         if(ltf[i].time == sweep.tSweep)
           {
            sweepShift = i;
            break;
           }
        }
      if(sweepShift < 0)
         sweepShift = 1;

      const bool sellSetup = (sweep.setupDir == DIR_SELL);
      bool cisd = false;
      bool bos  = false;
      double broken = 0;
      int bosBar = -1;

      // CISD: a later closed candle closes through the opposite side of the sweep candle
      for(int i = 1; i < sweepShift; i++)
        {
         if(sellSetup && ltf[i].close < sweep.sweepOpen && ltf[i].close < sweep.sweepLow)
            cisd = true;
         if(!sellSetup && ltf[i].close > sweep.sweepOpen && ltf[i].close > sweep.sweepHigh)
            cisd = true;
        }

      // BOS: break of the most relevant short-term swing created into the sweep
      if(sellSetup)
        {
         const int sl = FindLatestSwingLow(ltf, strength, total, 1, sweepShift + 8);
         if(sl >= 0)
           {
            broken = ltf[sl].low;
            for(int i = 1; i < sl; i++)
              {
               if(ltf[i].close < broken)
                 {
                  bos    = true;
                  bosBar = i;
                  break;
                 }
              }
           }
         // Fallback: break of accumulation midpoint / last internal low
         if(!bos)
           {
            broken = sweep.sweepLow;
            for(int i = 1; i < sweepShift; i++)
              {
               if(ltf[i].close < broken)
                 {
                  bos    = true;
                  bosBar = i;
                  break;
                 }
              }
           }
        }
      else
        {
         const int sh = FindLatestSwingHigh(ltf, strength, total, 1, sweepShift + 8);
         if(sh >= 0)
           {
            broken = ltf[sh].high;
            for(int i = 1; i < sh; i++)
              {
               if(ltf[i].close > broken)
                 {
                  bos    = true;
                  bosBar = i;
                  break;
                 }
              }
           }
         if(!bos)
           {
            broken = sweep.sweepHigh;
            for(int i = 1; i < sweepShift; i++)
              {
               if(ltf[i].close > broken)
                 {
                  bos    = true;
                  bosBar = i;
                  break;
                 }
              }
           }
        }

      bool ok = false;
      if(m_cfg.confirmMode == CONFIRM_BOS)
         ok = bos;
      else if(m_cfg.confirmMode == CONFIRM_CISD)
         ok = cisd;
      else
         ok = (bos && cisd);

      if(!ok)
         return(false);

      const int confirmBar = (bosBar > 0 ? bosBar : 1);
      if(m_cfg.requireDisplacement && !IsDisplacement(ltf[confirmBar], atr, m_cfg.displacementAtrMult))
         return(false);

      // Optional extra rejection: a lower-high (sell) or higher-low (buy) after the sweep
      if(m_cfg.requireRejection)
        {
         if(sellSetup)
           {
            bool lh = false;
            for(int i = 1; i < sweepShift; i++)
              {
               if(IsSwingHigh(ltf, i, strength, total) && ltf[i].high < sweep.extreme)
                  lh = true;
              }
            if(!lh && ltf[1].high >= sweep.extreme)
               return(false);
           }
         else
           {
            bool hl = false;
            for(int i = 1; i < sweepShift; i++)
              {
               if(IsSwingLow(ltf, i, strength, total) && ltf[i].low > sweep.extreme)
                  hl = true;
              }
            if(!hl && ltf[1].low <= sweep.extreme)
               return(false);
           }
        }

      mss.confirmed   = true;
      mss.dir         = sweep.setupDir;
      mss.tShift      = ltf[confirmBar].time;
      mss.brokenLevel = broken;
      mss.impulseHigh = (sellSetup ? sweep.extreme : MathMax(ltf[confirmBar].high, sweep.sweepHigh));
      mss.impulseLow  = (sellSetup ? MathMin(ltf[confirmBar].low, sweep.sweepLow) : sweep.extreme);

      double fvgTop = 0, fvgBot = 0;
      mss.hasFvg = DetectFvg(ltf, confirmBar, total, !sellSetup, fvgTop, fvgBot);
      if(!mss.hasFvg)
         mss.hasFvg = DetectFvg(ltf, confirmBar + 1, total, !sellSetup, fvgTop, fvgBot);
      mss.fvgTop    = fvgTop;
      mss.fvgBottom = fvgBot;

      if(mss.hasFvg && PriceToPoints(m_symbol, mss.fvgTop - mss.fvgBottom) >= m_cfg.fvgMinPoints)
        {
         mss.entryZoneHigh = mss.fvgTop;
         mss.entryZoneLow  = mss.fvgBottom;
        }
      else
        {
         const double zone = PointsToPrice(m_symbol, m_cfg.sweepBufferPoints + 5.0);
         mss.entryZoneHigh = broken + zone;
         mss.entryZoneLow  = broken - zone;
         if(sellSetup)
           {
            mss.entryZoneHigh = broken + zone;
            mss.entryZoneLow  = broken;
           }
         else
           {
            mss.entryZoneHigh = broken;
            mss.entryZoneLow  = broken - zone;
           }
        }
      return(true);
     }
  };

#endif
