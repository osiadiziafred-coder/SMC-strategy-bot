//+------------------------------------------------------------------+
//|                                              AMD_Session_EA.mq5  |
//|     FULL standalone bot — copy this ONE file into MQL5/Experts    |
//|           Session Accumulation, Manipulation & Distribution      |
//+------------------------------------------------------------------+
#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "Full standalone AMD session EA. Drop into MQL5/Experts, compile, attach. No extra include files required."

#include <Trade/Trade.mqh>


//+------------------------------------------------------------------+
//| AMD_Enums.mqh
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Session-based Accumulation / Manipulation / Distribution enums    |
//+------------------------------------------------------------------+

enum ENUM_AMD_PHASE
  {
   PHASE_IDLE = 0,              // waiting for accumulation session
   PHASE_ACCUMULATION,          // range is forming
   PHASE_RANGE_SET,             // range frozen, waiting for a sweep
   PHASE_MANIPULATION,          // liquidity taken, waiting for rejection
   PHASE_CONFIRMATION,          // structure shift detected, waiting for entry
   PHASE_IN_TRADE,              // position is open
   PHASE_CYCLE_COMPLETE,        // one trade already taken this cycle
   PHASE_RANGE_INVALID          // range rejected by filters
  };

enum ENUM_LOT_MODE
  {
   LOT_FIXED = 0,               // use InpFixedLots
   LOT_RISK_PERCENT             // size from account risk % and SL distance
  };

enum ENUM_TP_MODE
  {
   TP_RISK_REWARD = 0,          // SL distance * RR
   TP_LIQUIDITY,                // next session/swing liquidity
   TP_HYBRID                    // RR first target, liquidity for remainder
  };

enum ENUM_ENTRY_MODE
  {
   ENTRY_MARKET = 0,            // fill on confirmation bar close
   ENTRY_RETEST,                // wait for a tap of the BOS / FVG zone
   ENTRY_FVG                    // enter when price returns into the displacement FVG
  };

enum ENUM_CONFIRM_MODE
  {
   CONFIRM_BOS = 0,             // break of a relevant short-term swing
   CONFIRM_CISD,                // close through the opposite side of the sweep candle
   CONFIRM_BOS_AND_CISD         // both required
  };

enum ENUM_HTF_BIAS_MODE
  {
   BIAS_OFF = 0,                // both directions allowed
   BIAS_WITH_TREND,             // only trade in HTF structure direction
   BIAS_COUNTER_TREND           // only trade against HTF structure
  };

enum ENUM_SWEEP_RETURN
  {
   RETURN_INSIDE_RANGE = 0,     // close back inside the accumulation range
   RETURN_THROUGH_LEVEL,        // close back through the swept level
   RETURN_WICK_ONLY             // wick through, close already back (no extra close wait)
  };

enum ENUM_TRADE_DIR
  {
   DIR_NONE = 0,
   DIR_BUY,
   DIR_SELL
  };

enum ENUM_SESSION_KIND
  {
   SESSION_NONE = 0,
   SESSION_ASIA,
   SESSION_LONDON,
   SESSION_NEWYORK,
   SESSION_CUSTOM
  };


//+------------------------------------------------------------------+
//| AMD_Config.mqh
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Runtime copy of all EA inputs. Filled once in OnInit.            |
//+------------------------------------------------------------------+
struct SAmdConfig
  {
   long              magic;
   string            tradeComment;
   bool              allowBuy;
   bool              allowSell;

   int               asiaStartHour;
   int               asiaStartMinute;
   int               asiaEndHour;
   int               asiaEndMinute;
   int               londonStartHour;
   int               londonStartMinute;
   int               londonEndHour;
   int               londonEndMinute;
   int               nyStartHour;
   int               nyStartMinute;
   int               nyEndHour;
   int               nyEndMinute;
   bool              tradeLondon;
   bool              tradeNewYork;
   bool              closeFriday;
   int               fridayCloseHour;
   int               fridayCloseMinute;

   ENUM_TIMEFRAMES   htf;
   ENUM_TIMEFRAMES   ltf;
   int               htfLookback;
   int               ltfLookback;
   int               swingStrength;
   int               equalLookback;
   double            equalTolerancePoints;
   ENUM_HTF_BIAS_MODE htfBiasMode;

   double            minRangePoints;
   double            maxRangePoints;
   int               minAccBars;
   double            minSweepPoints;
   double            sweepBufferPoints;
   ENUM_SWEEP_RETURN sweepReturnMode;
   bool              requireRejection;
   ENUM_CONFIRM_MODE confirmMode;
   bool              requireDisplacement;
   double            displacementAtrMult;
   int               atrPeriod;
   ENUM_ENTRY_MODE   entryMode;
   int               maxBarsAfterMss;
   int               retestMaxBars;
   double            fvgMinPoints;

   ENUM_LOT_MODE     lotMode;
   double            fixedLots;
   double            riskPercent;
   double            maxLot;
   double            slBufferPoints;
   double            maxSlPoints;
   double            minSlPoints;
   ENUM_TP_MODE      tpMode;
   double            riskReward;
   bool              usePartialClose;
   double            partialClosePercent;
   double            partialCloseRR;
   bool              moveBeAfterPartial;
   double            beOffsetPoints;
   int               maxTradesPerDay;
   int               maxOpenPositions;
   bool              oneTradePerCycle;

   double            maxSpreadPoints;
   double            maxAtrPoints;
   double            minAtrPoints;
   bool              skipHighVolatility;
   double            volatilityAtrMult;

   bool              showVisuals;
   bool              showDashboard;
   bool              showLiquidityLabels;
   bool              debugLog;
   bool              tradeOnBarClose;
  };

struct SSessionRange
  {
   datetime          tStart;
   datetime          tEnd;
   double            openPrice;
   double            high;
   double            low;
   double            closePrice;
   double            rangeSize;
   bool              complete;
   bool              valid;
   string            name;
  };

struct SLiquidityLevel
  {
   double            price;
   datetime          tFormed;
   bool              buySide;          // true = BSL (above a high)
   bool              swept;
   datetime          tSwept;
   double            sweepExtreme;
   string            label;
  };

struct SSweepEvent
  {
   bool              active;
   ENUM_TRADE_DIR    setupDir;         // BUY after SSL sweep, SELL after BSL sweep
   double            level;
   double            extreme;
   datetime          tSweep;
   int               sweepBarShift;
   double            sweepOpen;
   double            sweepClose;
   double            sweepHigh;
   double            sweepLow;
   bool              returned;
   datetime          tReturned;
  };

struct SStructureShift
  {
   bool              confirmed;
   ENUM_TRADE_DIR    dir;
   datetime          tShift;
   double            brokenLevel;
   double            impulseHigh;
   double            impulseLow;
   double            fvgTop;
   double            fvgBottom;
   bool              hasFvg;
   double            entryZoneHigh;
   double            entryZoneLow;
  };

struct SPendingSetup
  {
   bool              armed;
   ENUM_TRADE_DIR    dir;
   datetime          tArmed;
   int               barsWaited;
   double            entryZoneHigh;
   double            entryZoneLow;
   double            slPrice;
   double            tpPrice;
   double            liquidityTarget;
  };

struct SHtfBias
  {
   ENUM_TRADE_DIR    dir;
   double            lastSwingHigh;
   double            lastSwingLow;
   datetime          tLastBos;
  };


//+------------------------------------------------------------------+
//| AMD_Utils.mqh
//+------------------------------------------------------------------+

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

void DebugPrint(const SAmdConfig &cfg, const string msg)
  {
   if(cfg.debugLog)
      Print("[AMD] ", msg);
  }


//+------------------------------------------------------------------+
//| AMD_Sessions.mqh
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Session clock and accumulation-range builder                     |
//+------------------------------------------------------------------+
class CSessionManager
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;

public:
                     CSessionManager(void) { m_symbol = _Symbol; m_tf = PERIOD_M15; }

   void              Init(const SAmdConfig &cfg, const string symbol, const ENUM_TIMEFRAMES tf)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      m_tf     = tf;
     }

   ENUM_SESSION_KIND CurrentSession(const datetime now) const
     {
      if(TimeInWindow(now, m_cfg.asiaStartHour, m_cfg.asiaStartMinute,
                      m_cfg.asiaEndHour, m_cfg.asiaEndMinute))
         return(SESSION_ASIA);
      if(TimeInWindow(now, m_cfg.londonStartHour, m_cfg.londonStartMinute,
                      m_cfg.londonEndHour, m_cfg.londonEndMinute))
         return(SESSION_LONDON);
      if(TimeInWindow(now, m_cfg.nyStartHour, m_cfg.nyStartMinute,
                      m_cfg.nyEndHour, m_cfg.nyEndMinute))
         return(SESSION_NEWYORK);
      return(SESSION_NONE);
     }

   bool              InAccumulation(const datetime now) const
     {
      return(CurrentSession(now) == SESSION_ASIA);
     }

   bool              InTradeWindow(const datetime now) const
     {
      if(m_cfg.closeFriday && IsFridayCloseTime(now, m_cfg.fridayCloseHour, m_cfg.fridayCloseMinute))
         return(false);
      const ENUM_SESSION_KIND s = CurrentSession(now);
      if(s == SESSION_LONDON && m_cfg.tradeLondon)
         return(true);
      if(s == SESSION_NEWYORK && m_cfg.tradeNewYork)
         return(true);
      return(false);
     }

   bool              AccumulationBounds(const datetime now, datetime &tStart, datetime &tEnd) const
     {
      return(GetSessionBounds(now, m_cfg.asiaStartHour, m_cfg.asiaStartMinute,
                              m_cfg.asiaEndHour, m_cfg.asiaEndMinute, tStart, tEnd));
     }

   bool              BuildRange(const datetime now, SSessionRange &range) const
     {
      datetime tStart, tEnd;
      if(!AccumulationBounds(now, tStart, tEnd))
         return(false);

      range.tStart     = tStart;
      range.tEnd       = tEnd;
      range.name       = "ASIA";
      range.complete   = (now >= tEnd);
      range.valid      = false;
      range.openPrice  = 0;
      range.closePrice = 0;
      range.high       = 0;
      range.low        = 0;
      range.rangeSize  = 0;

      const datetime toTime = (now < tEnd ? now : tEnd - 1);
      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      const int copied = CopyRates(m_symbol, m_tf, tStart, toTime, rates);
      if(copied < m_cfg.minAccBars)
         return(false);

      range.high      = rates[copied - 1].high;
      range.low       = rates[copied - 1].low;
      range.openPrice = rates[copied - 1].open;
      range.closePrice= rates[0].close;
      int barsInside  = 0;
      for(int i = 0; i < copied; i++)
        {
         if(rates[i].time < tStart || rates[i].time >= tEnd)
            continue;
         barsInside++;
         if(rates[i].high > range.high)
            range.high = rates[i].high;
         if(rates[i].low < range.low)
            range.low = rates[i].low;
        }
      if(barsInside < m_cfg.minAccBars)
         return(false);

      range.rangeSize = range.high - range.low;
      const double pts = PriceToPoints(m_symbol, range.rangeSize);
      range.valid = (pts >= m_cfg.minRangePoints);
      if(m_cfg.maxRangePoints > 0.0 && pts > m_cfg.maxRangePoints)
         range.valid = false;
      return(true);
     }
  };


//+------------------------------------------------------------------+
//| AMD_Liquidity.mqh
//+------------------------------------------------------------------+

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


//+------------------------------------------------------------------+
//| AMD_Structure.mqh
//+------------------------------------------------------------------+

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


//+------------------------------------------------------------------+
//| AMD_Trading.mqh
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Execution, position sizing, SL/TP, partials, breakeven           |
//+------------------------------------------------------------------+
class CAmdTrader
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;
   CTrade            m_trade;
   ulong             m_partialTicket;
   bool              m_partialDone;
   bool              m_beDone;

   bool              SelectFilling(void)
     {
      const int filling = (int)SymbolInfoInteger(m_symbol, SYMBOL_FILLING_MODE);
      if((filling & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
         m_trade.SetTypeFilling(ORDER_FILLING_IOC);
      else if((filling & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
         m_trade.SetTypeFilling(ORDER_FILLING_FOK);
      else
         m_trade.SetTypeFilling(ORDER_FILLING_RETURN);
      return(true);
     }

   double            StopsLevelPrice(void) const
     {
      const long lvl = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
      return(PointsToPrice(m_symbol, (double)lvl));
     }

public:
                     CAmdTrader(void)
     {
      m_symbol        = _Symbol;
      m_partialTicket = 0;
      m_partialDone   = false;
      m_beDone        = false;
     }

   void              Init(const SAmdConfig &cfg, const string symbol)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      m_trade.SetExpertMagicNumber(cfg.magic);
      m_trade.SetDeviationInPoints(20);
      SelectFilling();
      m_partialDone = false;
      m_beDone      = false;
     }

   void              ResetCycleFlags(void)
     {
      m_partialDone = false;
      m_beDone      = false;
      m_partialTicket = 0;
     }

   int               CountOpenPositions(void) const
     {
      int n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_cfg.magic)
            continue;
         n++;
        }
      return(n);
     }

   int               CountTodayDeals(const datetime now) const
     {
      const datetime from = DateFloor(now);
      if(!HistorySelect(from, now + 60))
         return(0);
      int n = 0;
      const int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
        {
         const ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0)
            continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != m_symbol)
            continue;
         if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != m_cfg.magic)
            continue;
         if((int)HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN)
            continue;
         n++;
        }
      return(n);
     }

   double            CalcLot(const double entry, const double sl) const
     {
      if(m_cfg.lotMode == LOT_FIXED)
        {
         double lot = m_cfg.fixedLots;
         return(NormalizeVolume(lot));
        }

      const double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      const double riskMoney = balance * m_cfg.riskPercent / 100.0;
      const double tickSize  = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      const double tickValue = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      const double slDist    = MathAbs(entry - sl);
      if(tickSize <= 0.0 || tickValue <= 0.0 || slDist <= 0.0 || riskMoney <= 0.0)
         return(0.0);
      const double ticks = slDist / tickSize;
      double lot = riskMoney / (ticks * tickValue);
      lot = NormalizeVolume(lot);
      if(m_cfg.maxLot > 0.0 && lot > m_cfg.maxLot)
         lot = NormalizeVolume(m_cfg.maxLot);
      return(lot);
     }

   double            NormalizeVolume(double lot) const
     {
      const double vmin = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      const double vmax = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      const double step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      if(step > 0.0)
         lot = MathFloor(lot / step + 1e-8) * step;
      if(lot < vmin)
         return(0.0);
      if(lot > vmax)
         lot = vmax;
      const int digits = (step >= 1.0 ? 0 : (step >= 0.1 ? 1 : 2));
      return(NormalizeDouble(lot, digits));
     }

   bool              ValidateStops(const ENUM_TRADE_DIR dir, const double entry,
                                   double &sl, double &tp, string &reason) const
     {
      const double minPts = m_cfg.minSlPoints;
      const double maxPts = m_cfg.maxSlPoints;
      double slPts = PriceToPoints(m_symbol, MathAbs(entry - sl));
      const double stops = StopsLevelPrice();

      if(dir == DIR_BUY && sl >= entry)
        {
         reason = "BUY SL must be below entry";
         return(false);
        }
      if(dir == DIR_SELL && sl <= entry)
        {
         reason = "SELL SL must be above entry";
         return(false);
        }

      if(MathAbs(entry - sl) < stops)
        {
         if(dir == DIR_BUY)
            sl = entry - stops;
         else
            sl = entry + stops;
         slPts = PriceToPoints(m_symbol, MathAbs(entry - sl));
        }

      if(minPts > 0.0 && slPts < minPts)
        {
         reason = "SL too tight";
         return(false);
        }
      if(maxPts > 0.0 && slPts > maxPts)
        {
         reason = "SL distance exceeds maximum allowed risk";
         return(false);
        }
      if(tp > 0.0)
        {
         if(dir == DIR_BUY && tp <= entry)
           {
            reason = "BUY TP must be above entry";
            return(false);
           }
         if(dir == DIR_SELL && tp >= entry)
           {
            reason = "SELL TP must be below entry";
            return(false);
           }
         if(MathAbs(tp - entry) < stops)
           {
            reason = "TP inside stops level";
            return(false);
           }
        }
      reason = "";
      return(true);
     }

   double            SlFromSweep(const ENUM_TRADE_DIR dir, const SSweepEvent &sweep) const
     {
      const double buf = PointsToPrice(m_symbol, m_cfg.slBufferPoints);
      if(dir == DIR_BUY)
         return(NormalizePrice(m_symbol, sweep.extreme - buf));
      return(NormalizePrice(m_symbol, sweep.extreme + buf));
     }

   double            TpFromMode(const ENUM_TRADE_DIR dir, const double entry, const double sl,
                                const double liquidityTarget) const
     {
      const double slDist = MathAbs(entry - sl);
      double rrTp = 0.0;
      if(dir == DIR_BUY)
         rrTp = entry + slDist * m_cfg.riskReward;
      else
         rrTp = entry - slDist * m_cfg.riskReward;

      if(m_cfg.tpMode == TP_RISK_REWARD)
         return(NormalizePrice(m_symbol, rrTp));

      double liq = liquidityTarget;
      if(liq <= 0.0)
         return(NormalizePrice(m_symbol, rrTp));

      if(m_cfg.tpMode == TP_LIQUIDITY)
        {
         if(dir == DIR_BUY && liq > entry)
            return(NormalizePrice(m_symbol, liq));
         if(dir == DIR_SELL && liq < entry)
            return(NormalizePrice(m_symbol, liq));
         return(NormalizePrice(m_symbol, rrTp));
        }

      // Hybrid: use the farther of RR and liquidity (more conservative = closer? User asked RR or liquidity)
      // Hybrid uses RR as first objective conceptually; final TP is liquidity if it is beyond RR.
      if(dir == DIR_BUY)
         return(NormalizePrice(m_symbol, MathMax(rrTp, liq)));
      return(NormalizePrice(m_symbol, MathMin(rrTp, liq)));
     }

   bool              OpenTrade(const ENUM_TRADE_DIR dir, const double sl, const double tp,
                               const string comment, string &reason)
     {
      if(dir == DIR_BUY && !m_cfg.allowBuy)
        {
         reason = "Buys disabled";
         return(false);
        }
      if(dir == DIR_SELL && !m_cfg.allowSell)
        {
         reason = "Sells disabled";
         return(false);
        }
      if(CountOpenPositions() >= m_cfg.maxOpenPositions)
        {
         reason = "Max open positions reached";
         return(false);
        }
      if(CountTodayDeals(TimeCurrent()) >= m_cfg.maxTradesPerDay)
        {
         reason = "Max trades per day reached";
         return(false);
        }

      const double entry = (dir == DIR_BUY
                            ? SymbolInfoDouble(m_symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(m_symbol, SYMBOL_BID));
      double slUse = sl;
      double tpUse = tp;
      if(!ValidateStops(dir, entry, slUse, tpUse, reason))
         return(false);

      const double lot = CalcLot(entry, slUse);
      if(lot <= 0.0)
        {
         reason = "Lot size is zero (risk/SL too large for the account)";
         return(false);
        }

      m_trade.SetExpertMagicNumber(m_cfg.magic);
      const string cmt = (comment == "" ? m_cfg.tradeComment : comment);
      bool ok = false;
      if(dir == DIR_BUY)
         ok = m_trade.Buy(lot, m_symbol, 0.0, slUse, tpUse, cmt);
      else
         ok = m_trade.Sell(lot, m_symbol, 0.0, slUse, tpUse, cmt);

      if(!ok)
        {
         reason = "OrderSend failed: " + IntegerToString((int)m_trade.ResultRetcode()) +
                  " " + m_trade.ResultRetcodeDescription();
         return(false);
        }
      m_partialDone = false;
      m_beDone      = false;
      m_partialTicket = m_trade.ResultOrder();
      reason = "";
      return(true);
     }

   void              ManageOpenTrades(void)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if((long)PositionGetInteger(POSITION_MAGIC) != m_cfg.magic)
            continue;

         const long type   = PositionGetInteger(POSITION_TYPE);
         const double open = PositionGetDouble(POSITION_PRICE_OPEN);
         const double sl   = PositionGetDouble(POSITION_SL);
         const double tp   = PositionGetDouble(POSITION_TP);
         const double vol  = PositionGetDouble(POSITION_VOLUME);
         const double bid  = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         const double ask  = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         const double slDist = MathAbs(open - sl);
         if(slDist <= 0.0)
            continue;

         if(m_cfg.usePartialClose && !m_partialDone && m_cfg.partialClosePercent > 0.0)
           {
            const double trigger = m_cfg.partialCloseRR * slDist;
            bool hit = false;
            if(type == POSITION_TYPE_BUY)
               hit = (bid >= open + trigger);
            else
               hit = (ask <= open - trigger);
            if(hit)
              {
               double closeVol = vol * m_cfg.partialClosePercent / 100.0;
               closeVol = NormalizeVolume(closeVol);
               const double vmin = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
               if(closeVol >= vmin && (vol - closeVol) >= vmin - 1e-8)
                 {
                  if(m_trade.PositionClosePartial(ticket, closeVol))
                    {
                     m_partialDone = true;
                     if(m_cfg.moveBeAfterPartial)
                        MoveToBreakeven(ticket, type, open);
                    }
                 }
               else if(hit && m_cfg.moveBeAfterPartial)
                 {
                  MoveToBreakeven(ticket, type, open);
                  m_partialDone = true;
                 }
              }
           }
         else if(m_cfg.moveBeAfterPartial && m_partialDone && !m_beDone)
            MoveToBreakeven(ticket, type, open);

         if(m_cfg.closeFriday && IsFridayCloseTime(TimeCurrent(), m_cfg.fridayCloseHour, m_cfg.fridayCloseMinute))
            m_trade.PositionClose(ticket);
        }
     }

   bool              HasOpenPosition(void) const
     {
      return(CountOpenPositions() > 0);
     }

private:
   void              MoveToBreakeven(const ulong ticket, const long type, const double open)
     {
      if(m_beDone)
         return;
      const double off = PointsToPrice(m_symbol, m_cfg.beOffsetPoints);
      double newSl = (type == POSITION_TYPE_BUY ? open + off : open - off);
      newSl = NormalizePrice(m_symbol, newSl);
      const double tp = PositionGetDouble(POSITION_TP);
      if(m_trade.PositionModify(ticket, newSl, tp))
         m_beDone = true;
     }
  };


//+------------------------------------------------------------------+
//| AMD_Visuals.mqh
//+------------------------------------------------------------------+

#define AMD_PREFIX "AMD_"

//+------------------------------------------------------------------+
//| Chart drawings: range, liquidity, sweep, MSS, entry, dashboard   |
//+------------------------------------------------------------------+
class CAmdVisuals
  {
private:
   SAmdConfig        m_cfg;
   string            m_symbol;
   long              m_chart;

   void              SetCommon(const string name, const color clr, const int width, const bool back)
     {
      ObjectSetInteger(m_chart, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart, name, OBJPROP_WIDTH, width);
      ObjectSetInteger(m_chart, name, OBJPROP_BACK, back);
      ObjectSetInteger(m_chart, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(m_chart, name, OBJPROP_RAY_RIGHT, false);
     }

   void              HLine(const string id, const double price, const color clr,
                           const ENUM_LINE_STYLE style, const string caption)
     {
      const string name = AMD_PREFIX + id;
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_HLINE, 0, 0, price);
      ObjectSetDouble(m_chart, name, OBJPROP_PRICE, price);
      SetCommon(name, clr, 1, true);
      ObjectSetInteger(m_chart, name, OBJPROP_STYLE, style);
      if(m_cfg.showLiquidityLabels)
        {
         const string lab = AMD_PREFIX + id + "_L";
         if(ObjectFind(m_chart, lab) < 0)
            ObjectCreate(m_chart, lab, OBJ_TEXT, 0, TimeCurrent(), price);
         ObjectSetString(m_chart, lab, OBJPROP_TEXT, caption);
         ObjectSetInteger(m_chart, lab, OBJPROP_COLOR, clr);
         ObjectSetInteger(m_chart, lab, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(m_chart, lab, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
         ObjectSetInteger(m_chart, lab, OBJPROP_SELECTABLE, false);
         ObjectMove(m_chart, lab, 0, TimeCurrent(), price);
        }
     }

   void              Rect(const string id, const datetime t1, const double p1,
                          const datetime t2, const double p2, const color clr, const bool fill)
     {
      const string name = AMD_PREFIX + id;
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
      ObjectMove(m_chart, name, 0, t1, p1);
      ObjectMove(m_chart, name, 1, t2, p2);
      SetCommon(name, clr, 1, true);
      ObjectSetInteger(m_chart, name, OBJPROP_FILL, fill);
      ObjectSetInteger(m_chart, name, OBJPROP_STYLE, STYLE_SOLID);
     }

   void              Trend(const string id, const datetime t1, const double p1,
                           const datetime t2, const double p2, const color clr,
                           const ENUM_LINE_STYLE style, const int width)
     {
      const string name = AMD_PREFIX + id;
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_TREND, 0, t1, p1, t2, p2);
      ObjectMove(m_chart, name, 0, t1, p1);
      ObjectMove(m_chart, name, 1, t2, p2);
      SetCommon(name, clr, width, false);
      ObjectSetInteger(m_chart, name, OBJPROP_STYLE, style);
      ObjectSetInteger(m_chart, name, OBJPROP_RAY_RIGHT, false);
     }

   void              Label(const string id, const datetime t, const double price,
                           const string text, const color clr, const ENUM_ANCHOR_POINT anchor)
     {
      const string name = AMD_PREFIX + id;
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_TEXT, 0, t, price);
      ObjectSetString(m_chart, name, OBJPROP_TEXT, text);
      ObjectSetInteger(m_chart, name, OBJPROP_COLOR, clr);
      ObjectSetInteger(m_chart, name, OBJPROP_FONTSIZE, 9);
      ObjectSetInteger(m_chart, name, OBJPROP_ANCHOR, anchor);
      ObjectSetInteger(m_chart, name, OBJPROP_SELECTABLE, false);
      ObjectMove(m_chart, name, 0, t, price);
     }

   void              Arrow(const string id, const datetime t, const double price,
                           const ENUM_TRADE_DIR dir)
     {
      const string name = AMD_PREFIX + id;
      const int code = (dir == DIR_BUY ? 233 : 234);
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_ARROW, 0, t, price);
      ObjectSetInteger(m_chart, name, OBJPROP_ARROWCODE, code);
      ObjectSetInteger(m_chart, name, OBJPROP_COLOR, dir == DIR_BUY ? clrAqua : clrHotPink);
      ObjectSetInteger(m_chart, name, OBJPROP_WIDTH, 2);
      ObjectSetInteger(m_chart, name, OBJPROP_SELECTABLE, false);
      ObjectMove(m_chart, name, 0, t, price);
     }

public:
                     CAmdVisuals(void) { m_chart = 0; m_symbol = _Symbol; }

   void              Init(const SAmdConfig &cfg, const string symbol)
     {
      m_cfg    = cfg;
      m_symbol = symbol;
      m_chart  = 0;
     }

   void              DeleteAll(void)
     {
      ObjectsDeleteAll(m_chart, AMD_PREFIX);
     }

   void              DrawRange(const SSessionRange &range)
     {
      if(!m_cfg.showVisuals || range.high <= 0.0)
         return;
      const datetime t2 = (range.complete ? range.tEnd : TimeCurrent());
      Rect("ACC_RANGE", range.tStart, range.high, t2, range.low, C'30,90,160', true);
      Trend("ACC_HIGH", range.tStart, range.high, t2 + 6 * PeriodSeconds(PERIOD_H1), range.high,
            clrLime, STYLE_DASH, 1);
      Trend("ACC_LOW", range.tStart, range.low, t2 + 6 * PeriodSeconds(PERIOD_H1), range.low,
            clrCrimson, STYLE_DASH, 1);
      Label("ACC_HIGH_L", range.tStart, range.high, "Buy-side liquidity (session high)",
            clrLime, ANCHOR_LEFT_LOWER);
      Label("ACC_LOW_L", range.tStart, range.low, "Sell-side liquidity (session low)",
            clrCrimson, ANCHOR_LEFT_UPPER);
      Label("ACC_TITLE", range.tStart, range.high, "ACCUMULATION",
            clrDodgerBlue, ANCHOR_LEFT_LOWER);
     }

   void              DrawSweep(const SSweepEvent &sweep, const SSessionRange &range)
     {
      if(!m_cfg.showVisuals || !sweep.active)
         return;
      const datetime t1 = sweep.tSweep;
      const datetime t2 = (sweep.tReturned > 0 ? sweep.tReturned : TimeCurrent());
      if(sweep.setupDir == DIR_SELL)
         Rect("MANIP", t1, sweep.extreme, t2, range.high, C'200,120,20', true);
      else
         Rect("MANIP", t1, range.low, t2, sweep.extreme, C'200,120,20', true);
      Label("MANIP_L", t1, sweep.extreme, "MANIPULATION / LIQUIDITY SWEEP",
            clrOrange, ANCHOR_LEFT_LOWER);
     }

   void              DrawMss(const SStructureShift &mss)
     {
      if(!m_cfg.showVisuals || !mss.confirmed)
         return;
      Arrow("MSS", mss.tShift, mss.brokenLevel, mss.dir);
      Label("MSS_L", mss.tShift, mss.brokenLevel,
            "MSS / BOS  " + DirToString(mss.dir),
            (mss.dir == DIR_BUY ? clrAqua : clrHotPink), ANCHOR_LEFT);
      if(mss.hasFvg)
         Rect("FVG", mss.tShift, mss.fvgTop, TimeCurrent(), mss.fvgBottom, C'80,40,140', true);
     }

   void              DrawTradeLevels(const ENUM_TRADE_DIR dir, const double entry,
                                     const double sl, const double tp, const datetime t)
     {
      if(!m_cfg.showVisuals || dir == DIR_NONE)
         return;
      const datetime t2 = t + 8 * PeriodSeconds(PERIOD_H1);
      Trend("ENTRY", t, entry, t2, entry, clrWhite, STYLE_SOLID, 2);
      Trend("SL", t, sl, t2, sl, clrRed, STYLE_DOT, 1);
      Trend("TP", t, tp, t2, tp, clrGold, STYLE_DOT, 1);
      Label("ENTRY_L", t, entry, "ENTRY " + DirToString(dir), clrWhite, ANCHOR_LEFT);
      Label("SL_L", t, sl, "STOP LOSS", clrRed, ANCHOR_LEFT);
      Label("TP_L", t, tp, "TAKE PROFIT", clrGold, ANCHOR_LEFT);
      Arrow("SIGNAL", t, entry, dir);
     }

   void              DrawDashboard(const ENUM_SESSION_KIND session, const ENUM_AMD_PHASE phase,
                                   const SSessionRange &range, const SHtfBias &bias,
                                   const SSweepEvent &sweep, const string lastMsg)
     {
      if(!m_cfg.showDashboard)
         return;

      const string lines =
         "AMD SESSION EA\n" +
         "Session : " + SessionKindToString(session) + "\n" +
         "Phase   : " + PhaseToString(phase) + "\n" +
         "HTF bias: " + DirToString(bias.dir) + "\n" +
         "Range H : " + DoubleToString(range.high, SymbolDigits(m_symbol)) + "\n" +
         "Range L : " + DoubleToString(range.low,  SymbolDigits(m_symbol)) + "\n" +
         "Range   : " + DoubleToString(PriceToPoints(m_symbol, range.rangeSize), 1) + " pts\n" +
         "Sweep   : " + (sweep.active ? DirToString(sweep.setupDir) : "none") +
         (sweep.returned ? " (returned)" : "") + "\n" +
         lastMsg;

      Comment(lines);

      const string box = AMD_PREFIX + "DASH";
      if(ObjectFind(m_chart, box) < 0)
         ObjectCreate(m_chart, box, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(m_chart, box, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(m_chart, box, OBJPROP_XDISTANCE, 12);
      ObjectSetInteger(m_chart, box, OBJPROP_YDISTANCE, 22);
      ObjectSetInteger(m_chart, box, OBJPROP_XSIZE, 280);
      ObjectSetInteger(m_chart, box, OBJPROP_YSIZE, 188);
      ObjectSetInteger(m_chart, box, OBJPROP_BGCOLOR, C'12,16,28');
      ObjectSetInteger(m_chart, box, OBJPROP_BORDER_COLOR, clrDodgerBlue);
      ObjectSetInteger(m_chart, box, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(m_chart, box, OBJPROP_BACK, false);
      ObjectSetInteger(m_chart, box, OBJPROP_SELECTABLE, false);
     }
  };


//+------------------------------------------------------------------+
//| Inputs, state machine, OnInit / OnTick
//+------------------------------------------------------------------+

input group "=== General ==="
input long               InpMagic              = 240824;           // Magic number
input string             InpComment            = "AMD_EA";         // Order comment
input bool               InpAllowBuy           = true;             // Allow BUY trades
input bool               InpAllowSell          = true;             // Allow SELL trades
input bool               InpTradeOnBarClose    = true;             // Evaluate on new LTF bar only
input bool               InpDebugLog           = false;            // Print debug logs

//--- Sessions (broker server time)
input group "=== Sessions (server time) ==="
input int                InpAsiaStartHour      = 0;                // Accumulation start hour
input int                InpAsiaStartMinute    = 0;                // Accumulation start minute
input int                InpAsiaEndHour        = 8;                // Accumulation end hour
input int                InpAsiaEndMinute      = 0;                // Accumulation end minute
input int                InpLondonStartHour    = 8;                // London start hour
input int                InpLondonStartMinute  = 0;                // London start minute
input int                InpLondonEndHour      = 12;               // London end hour
input int                InpLondonEndMinute    = 0;                // London end minute
input int                InpNYStartHour        = 12;               // New York start hour
input int                InpNYStartMinute      = 0;                // New York start minute
input int                InpNYEndHour          = 17;               // New York end hour
input int                InpNYEndMinute        = 0;                // New York end minute
input bool               InpTradeLondon        = true;             // Allow entries during London
input bool               InpTradeNewYork       = true;             // Allow entries during New York
input bool               InpCloseFriday        = true;             // Flatten before weekend
input int                InpFridayCloseHour    = 21;               // Friday flatten hour
input int                InpFridayCloseMinute  = 0;                // Friday flatten minute

//--- Timeframes / structure
input group "=== Timeframes & Structure ==="
input ENUM_TIMEFRAMES    InpHTF                = PERIOD_H1;        // Higher timeframe (bias)
input ENUM_TIMEFRAMES    InpLTF                = PERIOD_M5;        // Lower timeframe (entry)
input int                InpHtfLookback        = 80;               // HTF bars to scan
input int                InpLtfLookback        = 250;              // LTF bars to scan
input int                InpSwingStrength      = 2;                // Fractal swing strength
input int                InpEqualLookback      = 40;               // Bars for equal H/L scan
input double             InpEqualTolPoints     = 20;               // Equal H/L tolerance (points)
input ENUM_HTF_BIAS_MODE InpHtfBiasMode        = BIAS_OFF;         // HTF directional filter

//--- Accumulation / manipulation
input group "=== Accumulation & Liquidity Sweep ==="
input double             InpMinRangePoints     = 50;               // Min accumulation range (points)
input double             InpMaxRangePoints     = 800;              // Max accumulation range (0=off)
input int                InpMinAccBars         = 4;                // Min bars inside accumulation
input double             InpMinSweepPoints     = 5;                // Min pierce beyond the level
input double             InpSweepBufferPoints  = 0;                // Extra buffer beyond high/low
input ENUM_SWEEP_RETURN  InpSweepReturnMode    = RETURN_INSIDE_RANGE; // Sweep return rule
input bool               InpRequireRejection   = true;             // Require LH/HL rejection after sweep
input ENUM_CONFIRM_MODE  InpConfirmMode        = CONFIRM_BOS;      // Structure confirmation mode
input bool               InpRequireDisplacement= false;            // Require displacement candle
input double             InpDispAtrMult        = 0.8;              // Displacement body >= ATR *
input int                InpAtrPeriod          = 14;               // ATR period

//--- Entry
input group "=== Entry ==="
input ENUM_ENTRY_MODE    InpEntryMode          = ENTRY_MARKET;     // Entry style
input int                InpMaxBarsAfterMss    = 12;               // Expire setup after N LTF bars
input int                InpRetestMaxBars      = 8;                // Max bars to wait for retest/FVG
input double             InpFvgMinPoints       = 10;               // Ignore tiny FVGs

//--- Risk / money management
input group "=== Risk & Trade Management ==="
input ENUM_LOT_MODE      InpLotMode            = LOT_RISK_PERCENT; // Position sizing
input double             InpFixedLots          = 0.10;             // Fixed lot size
input double             InpRiskPercent        = 0.5;              // Risk percent of balance
input double             InpMaxLot             = 2.0;              // Cap on calculated lots
input double             InpSlBufferPoints     = 30;               // SL buffer beyond sweep extreme
input double             InpMaxSlPoints        = 400;              // Skip if SL wider than this
input double             InpMinSlPoints        = 40;               // Skip if SL tighter than this
input ENUM_TP_MODE       InpTpMode             = TP_HYBRID;        // Take-profit method
input double             InpRiskReward         = 2.0;              // RR multiple (1.5 / 2 / 3 / 4)
input bool               InpUsePartialClose    = true;             // Partial close enabled
input double             InpPartialPercent     = 50;               // Close this % at first target
input double             InpPartialRR          = 2.0;              // First partial at this RR
input bool               InpMoveBeAfterPartial = true;             // Move SL to BE after partial
input double             InpBeOffsetPoints     = 5;                // BE offset (points)
input int                InpMaxTradesPerDay    = 1;                // Daily trade cap
input int                InpMaxOpenPositions   = 1;                // Max concurrent positions
input bool               InpOneTradePerCycle   = true;             // One setup per AMD cycle

//--- Filters
input group "=== Quality Filters ==="
input double             InpMaxSpreadPoints    = 35;               // Max spread (points)
input double             InpMaxAtrPoints       = 0;                // Max ATR in points (0=off)
input double             InpMinAtrPoints       = 0;                // Min ATR in points (0=off)
input bool               InpSkipHighVol        = true;             // Skip abnormally high ATR
input double             InpVolAtrMult         = 2.5;              // High-vol if ATR > avg * this

//--- Visuals
input group "=== Chart Visuals ==="
input bool               InpShowVisuals        = true;             // Draw AMD objects
input bool               InpShowDashboard      = true;             // Show on-chart dashboard
input bool               InpShowLiqLabels      = true;             // Label liquidity levels

SAmdConfig         g_cfg;
CSessionManager    g_sessions;
CLiquidityEngine   g_liq;
CStructureEngine   g_structure;
CAmdTrader         g_trader;
CAmdVisuals        g_visuals;

ENUM_AMD_PHASE     g_phase          = PHASE_IDLE;
SSessionRange      g_range;
SSweepEvent        g_sweep;
SStructureShift    g_mss;
SPendingSetup      g_pending;
SHtfBias           g_bias;
datetime           g_cycleStart     = 0;
datetime           g_lastLtfBar     = 0;
string             g_lastMsg        = "";
double             g_lastEntry      = 0;
double             g_lastSl         = 0;
double             g_lastTp         = 0;
ENUM_TRADE_DIR     g_lastDir        = DIR_NONE;
datetime           g_lastTradeTime  = 0;
int                g_atrHandle      = INVALID_HANDLE;

//+------------------------------------------------------------------+
void FillConfig(void)
  {
   g_cfg.magic                 = InpMagic;
   g_cfg.tradeComment          = InpComment;
   g_cfg.allowBuy              = InpAllowBuy;
   g_cfg.allowSell             = InpAllowSell;
   g_cfg.asiaStartHour         = InpAsiaStartHour;
   g_cfg.asiaStartMinute       = InpAsiaStartMinute;
   g_cfg.asiaEndHour           = InpAsiaEndHour;
   g_cfg.asiaEndMinute         = InpAsiaEndMinute;
   g_cfg.londonStartHour       = InpLondonStartHour;
   g_cfg.londonStartMinute     = InpLondonStartMinute;
   g_cfg.londonEndHour         = InpLondonEndHour;
   g_cfg.londonEndMinute       = InpLondonEndMinute;
   g_cfg.nyStartHour           = InpNYStartHour;
   g_cfg.nyStartMinute         = InpNYStartMinute;
   g_cfg.nyEndHour             = InpNYEndHour;
   g_cfg.nyEndMinute           = InpNYEndMinute;
   g_cfg.tradeLondon           = InpTradeLondon;
   g_cfg.tradeNewYork          = InpTradeNewYork;
   g_cfg.closeFriday           = InpCloseFriday;
   g_cfg.fridayCloseHour       = InpFridayCloseHour;
   g_cfg.fridayCloseMinute     = InpFridayCloseMinute;
   g_cfg.htf                   = InpHTF;
   g_cfg.ltf                   = InpLTF;
   g_cfg.htfLookback           = InpHtfLookback;
   g_cfg.ltfLookback           = InpLtfLookback;
   g_cfg.swingStrength         = InpSwingStrength;
   g_cfg.equalLookback         = InpEqualLookback;
   g_cfg.equalTolerancePoints  = InpEqualTolPoints;
   g_cfg.htfBiasMode           = InpHtfBiasMode;
   g_cfg.minRangePoints        = InpMinRangePoints;
   g_cfg.maxRangePoints        = InpMaxRangePoints;
   g_cfg.minAccBars            = InpMinAccBars;
   g_cfg.minSweepPoints        = InpMinSweepPoints;
   g_cfg.sweepBufferPoints     = InpSweepBufferPoints;
   g_cfg.sweepReturnMode       = InpSweepReturnMode;
   g_cfg.requireRejection      = InpRequireRejection;
   g_cfg.confirmMode           = InpConfirmMode;
   g_cfg.requireDisplacement   = InpRequireDisplacement;
   g_cfg.displacementAtrMult   = InpDispAtrMult;
   g_cfg.atrPeriod             = InpAtrPeriod;
   g_cfg.entryMode             = InpEntryMode;
   g_cfg.maxBarsAfterMss       = InpMaxBarsAfterMss;
   g_cfg.retestMaxBars         = InpRetestMaxBars;
   g_cfg.fvgMinPoints          = InpFvgMinPoints;
   g_cfg.lotMode               = InpLotMode;
   g_cfg.fixedLots             = InpFixedLots;
   g_cfg.riskPercent           = InpRiskPercent;
   g_cfg.maxLot                = InpMaxLot;
   g_cfg.slBufferPoints        = InpSlBufferPoints;
   g_cfg.maxSlPoints           = InpMaxSlPoints;
   g_cfg.minSlPoints           = InpMinSlPoints;
   g_cfg.tpMode                = InpTpMode;
   g_cfg.riskReward            = InpRiskReward;
   g_cfg.usePartialClose       = InpUsePartialClose;
   g_cfg.partialClosePercent   = InpPartialPercent;
   g_cfg.partialCloseRR        = InpPartialRR;
   g_cfg.moveBeAfterPartial    = InpMoveBeAfterPartial;
   g_cfg.beOffsetPoints        = InpBeOffsetPoints;
   g_cfg.maxTradesPerDay       = InpMaxTradesPerDay;
   g_cfg.maxOpenPositions      = InpMaxOpenPositions;
   g_cfg.oneTradePerCycle      = InpOneTradePerCycle;
   g_cfg.maxSpreadPoints       = InpMaxSpreadPoints;
   g_cfg.maxAtrPoints          = InpMaxAtrPoints;
   g_cfg.minAtrPoints          = InpMinAtrPoints;
   g_cfg.skipHighVolatility    = InpSkipHighVol;
   g_cfg.volatilityAtrMult     = InpVolAtrMult;
   g_cfg.showVisuals           = InpShowVisuals;
   g_cfg.showDashboard         = InpShowDashboard;
   g_cfg.showLiquidityLabels   = InpShowLiqLabels;
   g_cfg.debugLog              = InpDebugLog;
   g_cfg.tradeOnBarClose       = InpTradeOnBarClose;
  }

void ResetCycle(const datetime newStart, const string why)
  {
   g_phase       = PHASE_IDLE;
   ZeroMemory(g_range);
   ZeroMemory(g_sweep);
   ZeroMemory(g_mss);
   ZeroMemory(g_pending);
   g_cycleStart  = newStart;
   g_lastMsg     = why;
   g_trader.ResetCycleFlags();
   DebugPrint(g_cfg, "Cycle reset: " + why);
  }

bool LoadLtf(MqlRates &rates[], int &copied)
  {
   ArraySetAsSeries(rates, true);
   copied = CopyRates(_Symbol, g_cfg.ltf, 0, g_cfg.ltfLookback, rates);
   return(copied > g_cfg.swingStrength * 4);
  }

double LtfAtr(void)
  {
   if(g_atrHandle == INVALID_HANDLE)
      return(0.0);
   double buf[];
   if(CopyBuffer(g_atrHandle, 0, 0, 1, buf) < 1)
      return(0.0);
   return(buf[0]);
  }

bool PassesFilters(string &reason)
  {
   const double spread = CurrentSpreadPoints(_Symbol);
   if(g_cfg.maxSpreadPoints > 0.0 && spread > g_cfg.maxSpreadPoints)
     {
      reason = "Spread too high (" + DoubleToString(spread, 1) + ")";
      return(false);
     }

   const double atr = LtfAtr();
   const double atrPts = PriceToPoints(_Symbol, atr);
   if(g_cfg.maxAtrPoints > 0.0 && atrPts > g_cfg.maxAtrPoints)
     {
      reason = "ATR too high";
      return(false);
     }
   if(g_cfg.minAtrPoints > 0.0 && atrPts < g_cfg.minAtrPoints)
     {
      reason = "ATR too low";
      return(false);
     }
   if(g_cfg.skipHighVolatility && g_atrHandle != INVALID_HANDLE)
     {
      double buf[];
      const int n = 50;
      if(CopyBuffer(g_atrHandle, 0, 0, n, buf) >= n)
        {
         double sum = 0.0;
         for(int i = 0; i < n; i++)
            sum += buf[i];
         const double avg = sum / n;
         if(avg > 0.0 && atr > avg * g_cfg.volatilityAtrMult)
           {
            reason = "Abnormal volatility";
            return(false);
           }
        }
     }
   if(!g_sessions.InTradeWindow(TimeCurrent()))
     {
      reason = "Outside permitted trading session";
      return(false);
     }
   if(g_trader.CountTodayDeals(TimeCurrent()) >= g_cfg.maxTradesPerDay)
     {
      reason = "Max trades already reached";
      return(false);
     }
   reason = "";
   return(true);
  }

bool PriceTouchesZone(const MqlRates &bar, const double zHigh, const double zLow)
  {
   return(!(bar.low > zHigh || bar.high < zLow));
  }

void ArmSetup(const MqlRates &ltf[])
  {
   g_pending.armed         = true;
   g_pending.dir           = g_mss.dir;
   g_pending.tArmed        = ltf[1].time;
   g_pending.barsWaited    = 0;
   g_pending.entryZoneHigh = g_mss.entryZoneHigh;
   g_pending.entryZoneLow  = g_mss.entryZoneLow;
   g_pending.slPrice       = g_trader.SlFromSweep(g_mss.dir, g_sweep);
   const double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   const double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   const double entryPx = (g_mss.dir == DIR_BUY ? ask : bid);
   g_pending.liquidityTarget = g_liq.NextLiquidityTarget(g_mss.dir, entryPx, g_range);
   g_pending.tpPrice = g_trader.TpFromMode(g_mss.dir, entryPx, g_pending.slPrice, g_pending.liquidityTarget);
   g_phase = PHASE_CONFIRMATION;
   g_lastMsg = "Structure confirmed. Setup armed (" + DirToString(g_mss.dir) + ")";
   DebugPrint(g_cfg, g_lastMsg);
  }

void TryEnter(const MqlRates &ltf[])
  {
   if(!g_pending.armed)
      return;
   if(g_cfg.oneTradePerCycle && g_phase == PHASE_CYCLE_COMPLETE)
      return;

   string reason;
   if(!PassesFilters(reason))
     {
      g_lastMsg = reason;
      return;
     }
   if(!g_structure.DirectionAllowed(g_pending.dir, g_bias))
     {
      g_lastMsg = "HTF bias filter blocked " + DirToString(g_pending.dir);
      return;
     }

   bool fire = false;
   if(g_cfg.entryMode == ENTRY_MARKET)
      fire = true;
   else
     {
      if(PriceTouchesZone(ltf[1], g_pending.entryZoneHigh, g_pending.entryZoneLow) ||
         PriceTouchesZone(ltf[0], g_pending.entryZoneHigh, g_pending.entryZoneLow))
         fire = true;
      g_pending.barsWaited++;
      if(!fire && g_pending.barsWaited > g_cfg.retestMaxBars)
        {
         g_lastMsg = "Retest/FVG timeout — setup cancelled";
         g_pending.armed = false;
         g_phase = PHASE_RANGE_SET;
         ZeroMemory(g_sweep);
         ZeroMemory(g_mss);
         return;
        }
     }

   if(g_cfg.maxBarsAfterMss > 0 && g_pending.barsWaited > g_cfg.maxBarsAfterMss)
     {
      g_lastMsg = "Confirmation expired";
      g_pending.armed = false;
      return;
     }

   if(!fire)
      return;

   const string cmt = g_cfg.tradeComment + " " + DirToString(g_pending.dir);
   if(!g_trader.OpenTrade(g_pending.dir, g_pending.slPrice, g_pending.tpPrice, cmt, reason))
     {
      g_lastMsg = "Entry skipped: " + reason;
      DebugPrint(g_cfg, g_lastMsg);
      // Permanent skip only when SL/risk is invalid; keep waiting on spread blips
      if(StringFind(reason, "SL ") >= 0 || StringFind(reason, "Lot size") >= 0)
        {
         g_pending.armed = false;
         g_phase = PHASE_CYCLE_COMPLETE;
        }
      return;
     }

   g_lastDir       = g_pending.dir;
   g_lastEntry     = (g_pending.dir == DIR_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                               : SymbolInfoDouble(_Symbol, SYMBOL_BID));
   g_lastSl        = g_pending.slPrice;
   g_lastTp        = g_pending.tpPrice;
   g_lastTradeTime = TimeCurrent();
   g_pending.armed = false;
   g_phase         = (g_cfg.oneTradePerCycle ? PHASE_CYCLE_COMPLETE : PHASE_IN_TRADE);
   g_lastMsg       = "DISTRIBUTION entry " + DirToString(g_lastDir);
   g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
   DebugPrint(g_cfg, g_lastMsg);
  }

void ProcessLogic(void)
  {
   const datetime now = TimeCurrent();
   datetime accStart = 0, accEnd = 0;
   g_sessions.AccumulationBounds(now, accStart, accEnd);
   if(accStart != 0 && accStart != g_cycleStart)
      ResetCycle(accStart, "New accumulation session");

   MqlRates ltf[];
   int copied = 0;
   if(!LoadLtf(ltf, copied))
     {
      g_lastMsg = "Not enough LTF bars";
      return;
     }

   g_bias = g_structure.ComputeHtfBias();
   g_sessions.BuildRange(now, g_range);

   const ENUM_SESSION_KIND session = g_sessions.CurrentSession(now);

   if(g_trader.HasOpenPosition())
     {
      if(g_phase != PHASE_CYCLE_COMPLETE)
         g_phase = PHASE_IN_TRADE;
     }
   else if(g_phase == PHASE_IN_TRADE && !g_cfg.oneTradePerCycle)
      g_phase = PHASE_RANGE_SET;

   // --- Phase machine ---
   if(session == SESSION_ASIA)
     {
      if(g_phase == PHASE_IDLE || g_phase == PHASE_RANGE_INVALID || g_phase == PHASE_RANGE_SET)
         g_phase = PHASE_ACCUMULATION;
     }
   else
     {
      if(g_range.valid && (g_phase == PHASE_IDLE || g_phase == PHASE_ACCUMULATION))
         g_phase = PHASE_RANGE_SET;
      else if(!g_range.valid && g_range.complete &&
              (g_phase == PHASE_IDLE || g_phase == PHASE_ACCUMULATION))
        {
         g_phase = PHASE_RANGE_INVALID;
         g_lastMsg = "Accumulation range rejected by size/bar filters";
        }
     }

   if(g_range.valid)
      g_liq.BuildFromRange(g_range, ltf, copied);

   // Never assume a sweep. Wait for actual price action on closed (or current) bars.
   if(g_range.valid &&
      g_phase != PHASE_CYCLE_COMPLETE &&
      g_phase != PHASE_RANGE_INVALID &&
      g_phase != PHASE_ACCUMULATION)
     {
      const MqlRates bar = ltf[g_cfg.tradeOnBarClose ? 1 : 0];

      if(!g_sweep.active)
        {
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, g_range, ev))
           {
            g_sweep = ev;
            g_phase = PHASE_MANIPULATION;
            g_lastMsg = "Liquidity sweep detected (" + DirToString(g_sweep.setupDir) + ")";
            DebugPrint(g_cfg, g_lastMsg);
            ZeroMemory(g_mss);
            ZeroMemory(g_pending);
           }
        }
      else
        {
         // Opposite sweep replaces the working idea only if the first
         // sweep never rejected. A later take of the other side after
         // a rejection is distribution toward liquidity, not a new Judas.
         SSweepEvent ev;
         ZeroMemory(ev);
         if(g_liq.DetectSweep(bar, g_range, ev) &&
            ev.setupDir != g_sweep.setupDir &&
            !g_sweep.returned)
           {
            g_sweep = ev;
            g_phase = PHASE_MANIPULATION;
            g_lastMsg = "Opposite sweep — working direction flipped to " + DirToString(g_sweep.setupDir);
            ZeroMemory(g_mss);
            ZeroMemory(g_pending);
           }
         else
           {
            if(g_sweep.setupDir == DIR_SELL && bar.high > g_sweep.extreme)
               g_sweep.extreme = bar.high;
            if(g_sweep.setupDir == DIR_BUY && bar.low < g_sweep.extreme)
               g_sweep.extreme = bar.low;
            g_liq.UpdateReturn(bar, g_range, g_sweep);
           }
        }

      if(g_sweep.active && g_sweep.returned && !g_mss.confirmed && !g_pending.armed)
        {
         const double atr = LtfAtr();
         if(g_structure.ConfirmShift(ltf, copied, g_sweep, g_range, atr, g_mss))
            ArmSetup(ltf);
         else
            g_lastMsg = "Sweep returned — waiting for market-structure confirmation";
        }
     }

   if(g_pending.armed)
      TryEnter(ltf);

   g_visuals.DrawRange(g_range);
   g_visuals.DrawSweep(g_sweep, g_range);
   g_visuals.DrawMss(g_mss);
   if(g_lastDir != DIR_NONE)
      g_visuals.DrawTradeLevels(g_lastDir, g_lastEntry, g_lastSl, g_lastTp, g_lastTradeTime);
   g_visuals.DrawDashboard(session, g_phase, g_range, g_bias, g_sweep, g_lastMsg);
  }

int OnInit()
  {
   FillConfig();
   g_sessions.Init(g_cfg, _Symbol, InpLTF);
   g_liq.Init(g_cfg, _Symbol);
   g_structure.Init(g_cfg, _Symbol);
   g_trader.Init(g_cfg, _Symbol);
   g_visuals.Init(g_cfg, _Symbol);

   g_atrHandle = iATR(_Symbol, InpLTF, InpAtrPeriod);
   if(g_atrHandle == INVALID_HANDLE)
     {
      Print("Failed to create ATR handle");
      return(INIT_FAILED);
     }

   ResetCycle(0, "Init");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);
   g_visuals.DeleteAll();
   Comment("");
  }

void OnTick()
  {
   g_trader.ManageOpenTrades();

   bool run = true;
   if(g_cfg.tradeOnBarClose)
      run = IsNewBar(_Symbol, g_cfg.ltf, g_lastLtfBar);

   // Always refresh the dashboard / live range while accumulating
   if(!run)
     {
      const datetime now = TimeCurrent();
      if(g_sessions.CurrentSession(now) == SESSION_ASIA)
        {
         g_sessions.BuildRange(now, g_range);
         g_phase = PHASE_ACCUMULATION;
         g_visuals.DrawRange(g_range);
         g_visuals.DrawDashboard(SESSION_ASIA, g_phase, g_range, g_bias, g_sweep, g_lastMsg);
        }
      return;
     }

   ProcessLogic();
  }

void OnTimer()
  {
  }
