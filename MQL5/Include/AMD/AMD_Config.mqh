#ifndef AMD_CONFIG_MQH
#define AMD_CONFIG_MQH

#include "AMD_Enums.mqh"

//+------------------------------------------------------------------+
//| Runtime copy of all EA inputs. Filled once in OnInit.            |
//+------------------------------------------------------------------+
struct SAmdConfig
  {
   long              magic;
   string            tradeComment;
   string            tradeSymbol;
   bool              allowBuy;
   bool              allowSell;
   bool              useM15;
   bool              useM30;
   bool              useH1;
   ENUM_TF_PRIORITY  tfPriority;

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
   double            startLots;
   double            balancePerLot;
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
   ENUM_DASH_THEME   dashTheme;
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

#endif
