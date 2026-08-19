#property copyright "SMC Strategy Bot"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "XAUUSDm H1/M5 market-structure EA: H1 bias, liquidity, order blocks, M5 confirmation, structural SL/TP, balance-tier lots."

#include "Types.mqh"

input group "=== Symbol & Timeframes ==="
input string            InpSymbol              = "XAUUSDm";
input ENUM_TIMEFRAMES   InpAnalysisTF          = PERIOD_H1;
input ENUM_TIMEFRAMES   InpEntryTF             = PERIOD_M5;

input group "=== Lot Size / Balance Tiers ==="
input double            StartingLot            = 0.01;
input double            FirstIncreaseBalance   = 150.00;
input double            BalanceStep            = 100.00;
input double            LotIncrease            = 0.01;

input group "=== Strategy Filters ==="
input bool              UseMarketStructure     = true;
input bool              UseLiquiditySweep      = true;
input bool              UseOrderBlocks         = true;
input bool              UseM5Confirmation      = true;
input bool              RequireM5Retest        = true;
input bool              RequireDiscountPremium = true;

input group "=== Structure Parameters ==="
input int               InpH1LookbackBars      = 220;
input int               InpM5LookbackBars      = 180;
input int               InpH1SwingStrength     = 3;
input int               InpM5SwingStrength     = 2;
input int               InpM5ConfirmMaxBars    = 18;
input double            InpDisplacementFactor  = 1.60;
input int               EqualLevelPoints       = 180;
input int               SweepMaxAgeM5Bars      = 36;
input int               SweepMinPiercePoints   = 30;
input int               ZoneMaxTests           = 2;
input int               ZoneApproachPoints     = 250;

input group "=== Risk Protection ==="
input int               MaxOpenPositions       = 1;
input int               MaximumDailyTrades     = 6;
input double            MaximumDailyLossPercent = 5.0;
input double            MaximumDrawdownPercent = 20.0;
input double            MinimumRiskReward      = 2.0;
input int               MaxStopLossPoints      = 5000;
input int               SLBufferPoints         = 80;
input bool              UseSpreadFilter        = true;
input int               MaxSpreadPoints        = 350;
input bool              UseDailyLossProtection = true;
input bool              UseMaxDrawdownProtection = true;
input int               SlippagePoints         = 40;
input int               FailedOrderWaitSeconds = 60;

input group "=== Session & News ==="
input bool              UseTradingSession      = false;
input int               StartTradingHour       = 7;
input int               EndTradingHour         = 21;
input bool              UseNewsFilter          = false;

input group "=== Identification ==="
input long              MagicNumber            = 19052601;
input string            TradeComment           = "XAUUSDm-H1M5";

input group "=== Visualization ==="
input bool              ShowDashboard          = true;
input bool              ShowZones              = true;
input bool              ShowLiquidity          = true;
input bool              ShowStructure          = true;
input bool              ShowEntryLevels        = true;

#include "Utils.mqh"
#include "Structure.mqh"
#include "Liquidity.mqh"
#include "Setups.mqh"
#include "TradeEngine.mqh"
#include "Visual.mqh"

void ProcessNewSetup()
  {
   if(PendingInvalidated())
     {
      LogReason("Pending setup invalidated");
      ResetPending();
     }

   if(!IsWithinTradingSession(TimeCurrent()))
     {
      g_ea_status = EA_STATUS_SESSION_CLOSED;
      LogReason("No trade: outside trading session");
      return;
     }

   if(!CheckRiskLimits())
      return;

   if(CountEAPositions() >= MaxOpenPositions)
     {
      g_ea_status = EA_STATUS_TRADE_OPEN;
      return;
     }

   if(g_h1_bias == BIAS_NONE)
     {
      g_ea_status = EA_STATUS_WAITING_SETUP;
      LogReason("No trade: H1 bias unclear");
      ResetPending();
      return;
     }

   TradePlan plan;
   ZeroMemory(plan);

   if(g_h1_bias == BIAS_BULLISH)
     {
      if(ConfirmBuySetup(plan))
        {
         Print(plan.reason);
         OpenBuy(plan);
        }
      return;
     }

   if(g_h1_bias == BIAS_BEARISH)
     {
      if(ConfirmSellSetup(plan))
        {
         Print(plan.reason);
         OpenSell(plan);
        }
     }
  }

int OnInit()
  {
   g_ea_status = EA_STATUS_INIT;
   ResetPending();
   ZeroMemory(g_daily);
   ZeroMemory(g_last_plan);
   g_used_setups_count = 0;
   ArrayResize(g_used_setups, 0);

   g_symbol = DetectXAUUSDm();
   if(g_symbol == "" || !IsXAUUSDmName(g_symbol))
     {
      g_ea_status = EA_STATUS_SYMBOL_ERROR;
      string err = "ERROR: XAUUSDm is unavailable. EA will not place trades.";
      Print(err);
      Alert(err);
      Comment(err);
      return INIT_FAILED;
     }

   if(!LoadSymbolContract(g_symbol))
     {
      g_ea_status = EA_STATUS_SYMBOL_ERROR;
      Print("ERROR: failed to read XAUUSDm contract specification.");
      Alert("ERROR: failed to read XAUUSDm contract specification.");
      return INIT_FAILED;
     }

   if(!SymbolIsTradable(g_symbol))
      Print("Warning: ", g_symbol, " trade mode is currently restricted.");

   InitTradeEngine();

   g_daily.day_start = BeginningOfDay(TimeCurrent());
   g_daily.day_start_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_daily.peak_equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(UseNewsFilter)
      Print("News filter requested, but no news API is available. The filter will stay inactive and will not invent events.");

   if(!RefreshRates(true))
      Print("Warning: initial rate copy incomplete; waiting for market data.");

   PrintFormat("XAUUSDm H1/M5 EA initialized on %s  digits=%d point=%.5f minlot=%.2f",
               g_symbol, g_digits, g_point, g_volume_min);
   PrintFormat("Starting balance: %.2f  lot size: %.2f",
               AccountInfoDouble(ACCOUNT_BALANCE),
               CalculateLotSizeFromBalance(AccountInfoDouble(ACCOUNT_BALANCE)));

   g_ea_status = EA_STATUS_WAITING_SETUP;
   g_status_text = "WAITING FOR SETUP";
   UpdateDashboard();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   Print("EA removed, reason=", IntegerToString(reason));
   CleanupVisuals();
   Comment("");
  }

void OnTick()
  {
   if(g_symbol == "" || g_ea_status == EA_STATUS_SYMBOL_ERROR)
      return;

   ManageTrade();
   RefreshDailyStats();

   if(CountEAPositions() > 0)
      g_ea_status = EA_STATUS_TRADE_OPEN;

   UpdateDashboard();

   if(!IsNewM5Bar())
      return;

   if(!RefreshRates(true))
     {
      LogReason("No trade: waiting for closed candle data");
      return;
     }

   AnalyzeStructure();
   AnalyzeLiquidityAndZones();
   DrawStructure();
   ProcessNewSetup();
   UpdateDashboard();
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD || request.magic == (ulong)MagicNumber || result.order > 0)
      RefreshDailyStats();
  }
