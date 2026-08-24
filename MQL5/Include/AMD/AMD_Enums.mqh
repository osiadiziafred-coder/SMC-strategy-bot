#ifndef AMD_ENUMS_MQH
#define AMD_ENUMS_MQH

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

#endif
