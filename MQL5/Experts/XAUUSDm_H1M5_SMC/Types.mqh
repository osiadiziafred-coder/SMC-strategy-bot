#ifndef XAUUSDM_SMC_TYPES_MQH
#define XAUUSDM_SMC_TYPES_MQH

#define SMC_PREFIX          "XAU_SMC_"
#define SMC_MAX_SWINGS      48
#define SMC_MAX_LIQ         48
#define SMC_MAX_ZONES       12
#define SMC_MAX_USED        128
#define SMC_RATES_H1        260
#define SMC_RATES_M5        240

enum ENUM_MARKET_BIAS
  {
   BIAS_NONE    = 0,
   BIAS_BULLISH = 1,
   BIAS_BEARISH = -1
  };

enum ENUM_EA_STATUS
  {
   EA_STATUS_INIT = 0,
   EA_STATUS_SYMBOL_ERROR,
   EA_STATUS_WAITING_SETUP,
   EA_STATUS_WAITING_M5,
   EA_STATUS_WAITING_RETEST,
   EA_STATUS_TRADE_OPEN,
   EA_STATUS_DAILY_LIMIT,
   EA_STATUS_DRAWDOWN_LIMIT,
   EA_STATUS_SESSION_CLOSED,
   EA_STATUS_SPREAD_HIGH,
   EA_STATUS_NEWS_DISABLED,
   EA_STATUS_MARKET_CLOSED,
   EA_STATUS_ERROR
  };

enum ENUM_SWEEP_DIR
  {
   SWEEP_NONE    = 0,
   SWEEP_BULLISH = 1,
   SWEEP_BEARISH = -1
  };

struct SwingPoint
  {
   datetime time;
   double   price;
   int      bar_index;
   bool     is_high;
   bool     broken;
   bool     valid;
  };

struct Zone
  {
   datetime time;
   int      bar_index;
   double   top;
   double   bottom;
   bool     is_demand;
   int      tests;
   bool     mitigated;
   bool     valid;
   bool     from_displacement;
  };

struct LiquidityLevel
  {
   datetime time;
   double   price;
   bool     is_high;
   bool     equal_level;
   bool     major_level;
   bool     swept;
   datetime sweep_time;
   double   sweep_extreme;
   int      bar_index;
   bool     valid;
  };

struct TradePlan
  {
   bool     valid;
   int      direction;
   ulong    setup_id;
   double   entry;
   double   sl;
   double   tp;
   double   rr;
   double   lots;
   double   zone_top;
   double   zone_bottom;
   double   sweep_extreme;
   datetime sweep_time;
   datetime confirmation_time;
   string   reason;
  };

struct PendingSetup
  {
   bool     active;
   bool     waiting_retest;
   bool     used;
   int      direction;
   ulong    setup_id;
   datetime created_time;
   datetime bos_time;
   datetime mss_time;
   datetime sweep_time;
   datetime liq_time;
   double   liq_price;
   double   sweep_extreme;
   double   ob_top;
   double   ob_bottom;
   double   bos_level;
   bool     had_displacement;
   bool     had_bos;
   bool     had_mss;
   bool     had_rejection;
  };

struct DailyState
  {
   datetime day_start;
   double   day_start_balance;
   double   peak_equity;
   int      trades_today;
   double   closed_pnl_today;
  };

#endif
