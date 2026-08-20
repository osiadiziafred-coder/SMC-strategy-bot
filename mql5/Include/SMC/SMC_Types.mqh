//+------------------------------------------------------------------+
//| SMC_Types.mqh — Shared enums and structs for SMC Robot           |
//+------------------------------------------------------------------+
#ifndef SMC_TYPES_MQH
#define SMC_TYPES_MQH

enum ENUM_SMC_BIAS
  {
   SMC_BIAS_NEUTRAL = 0,
   SMC_BIAS_BULLISH = 1,
   SMC_BIAS_BEARISH = -1
  };

enum ENUM_SMC_DIRECTION
  {
   SMC_DIR_NONE    = 0,
   SMC_DIR_BULLISH = 1,
   SMC_DIR_BEARISH = -1
  };

struct SSwingPoint
  {
   int    index;
   double price;
   bool   isHigh;
  };

struct SLiquiditySweep
  {
   bool   found;
   int    direction;      // SMC_DIR_BULLISH or SMC_DIR_BEARISH
   int    sweepIndex;
   double sweepPrice;
   double sweptLevel;
  };

struct SStructureShift
  {
   bool   found;
   int    direction;
   int    shiftIndex;
   double breakLevel;
  };

struct SFairValueGap
  {
   bool   found;
   int    direction;
   double top;
   double bottom;
   int    index;
  };

struct SSMCSignal
  {
   bool   valid;
   bool   isBuy;
   double entryPrice;
   double slPrice;
   string reason;
  };

#endif
