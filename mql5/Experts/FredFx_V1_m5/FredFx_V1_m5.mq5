//+------------------------------------------------------------------+
//| FredFx_V1_m5.mq5 — FredFx V1 m5 Expert Advisor                  |
//| Strategy: H1 bias | M15 sweep+CHoCH | M5 FVG entry               |
//| Risk: 1:2 R:R | Breakeven at +1R | $100 = 0.01 lot              |
//+------------------------------------------------------------------+
#property copyright "FredFx"
#property link      "https://github.com/osiadiziafred-coder/SMC-strategy-bot"
#property version   "1.00"
#property description "FredFx V1 m5 — SMC XAUUSDm Robot"

#include <Trade/Trade.mqh>
#include <SMC/SMC_Strategy.mqh>
#include <SMC/SMC_Risk.mqh>

//--- Input parameters
input string   InpSymbol             = "XAUUSDm";       // Trading symbol
input double   InpRiskReward           = 2.0;           // Risk : Reward ratio
input double   InpBreakevenAtR         = 1.0;           // Move SL to BE at this R
input double   InpBalancePer001Lot     = 100.0;         // Balance per 0.01 lot ($)
input double   InpMinLot               = 0.01;          // Minimum lot size
input double   InpMaxLot               = 100.0;         // Maximum lot size
input int      InpSwingLookback        = 5;             // Swing lookback bars
input double   InpSweepTolerancePips   = 2.0;           // Sweep tolerance (pips)
input double   InpFvgMinGapPips        = 1.0;           // Min FVG gap (pips)
input double   InpPipSize              = 0.1;           // Pip size for XAUUSD
input int      InpMagicNumber          = 20260820;      // EA magic number
input int      InpH1Bars               = 200;           // H1 bars to load
input int      InpM15Bars              = 300;           // M15 bars to load
input int      InpM5Bars               = 500;           // M5 bars to load

//--- Globals
CTrade   g_trade;
datetime g_lastBarTime = 0;
string   g_symbol;
string   g_eaName = "FredFx V1 m5";

//+------------------------------------------------------------------+
int OnInit()
  {
   g_symbol = InpSymbol;
   if(!SymbolSelect(g_symbol, true))
     {
      Print(g_eaName, ": Failed to select symbol: ", g_symbol);
      return INIT_FAILED;
     }

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(20);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);

   Print(g_eaName, " initialized on ", g_symbol);
   Print("R:R 1:", InpRiskReward, " | Breakeven at ", InpBreakevenAtR, "R");
   Print("Lot sizing: $", InpBalancePer001Lot, " = 0.01 lot");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print(g_eaName, " stopped. Reason: ", reason);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   ManageBreakeven(g_symbol, InpMagicNumber, InpBreakevenAtR, InpPipSize);

   datetime barTime = iTime(g_symbol, PERIOD_M5, 0);
   if(barTime == g_lastBarTime)
      return;
   g_lastBarTime = barTime;

   if(CountOpenPositions(g_symbol, InpMagicNumber) >= 1)
      return;

   double h1High[], h1Low[], h1Close[];
   double m15High[], m15Low[], m15Close[];
   double m5High[], m5Low[], m5Close[];

   if(!LoadOHLC(g_symbol, PERIOD_H1,  InpH1Bars,  h1High,  h1Low,  h1Close))
      return;
   if(!LoadOHLC(g_symbol, PERIOD_M15, InpM15Bars, m15High, m15Low, m15Close))
      return;
   if(!LoadOHLC(g_symbol, PERIOD_M5,  InpM5Bars,  m5High,  m5Low,  m5Close))
      return;

   int h1Total  = ArraySize(h1High);
   int m15Total = ArraySize(m15High);
   int m5Total  = ArraySize(m5High);

   double sweepTol = InpSweepTolerancePips * InpPipSize;
   double minFvg   = InpFvgMinGapPips * InpPipSize;

   SSMCSignal signal;
   if(!AnalyzeSMC(h1High, h1Low,
                  m15High, m15Low, m15Close,
                  m5High, m5Low, m5Close,
                  InpSwingLookback, sweepTol, minFvg,
                  InpPipSize, h1Total, m15Total, m5Total,
                  signal))
      return;

   if(!signal.valid)
      return;

   Print(g_eaName, " SIGNAL: ", signal.isBuy ? "BUY" : "SELL", " | ", signal.reason);

   double lots = CalcLotSize(g_symbol, InpBalancePer001Lot, InpMinLot, InpMaxLot);
   double sl, tp;
   double entry = signal.isBuy ? SymbolInfoDouble(g_symbol, SYMBOL_ASK)
                               : SymbolInfoDouble(g_symbol, SYMBOL_BID);
   CalcSLTP(signal.isBuy, entry, signal.slPrice, InpRiskReward, sl, tp);

   int digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);

   PrintFormat("%s Trade: %s %.2f lots | Entry %.2f | SL %.2f | TP %.2f",
               g_eaName, signal.isBuy ? "BUY" : "SELL", lots, entry, sl, tp);

   bool result;
   if(signal.isBuy)
      result = g_trade.Buy(lots, g_symbol, entry, sl, tp, g_eaName);
   else
      result = g_trade.Sell(lots, g_symbol, entry, sl, tp, g_eaName);

   if(!result)
      Print(g_eaName, " order failed: ", g_trade.ResultRetcode(),
            " — ", g_trade.ResultRetcodeDescription());
   else
      Print(g_eaName, " trade opened — ticket ", g_trade.ResultOrder());
  }

//+------------------------------------------------------------------+
bool LoadOHLC(const string symbol, ENUM_TIMEFRAMES tf, int count,
              double &high[], double &low[], double &close[])
  {
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   if(CopyHigh(symbol, tf, 0, count, high) < count)
     {
      Print(g_eaName, ": Failed to copy High for ", EnumToString(tf));
      return false;
     }
   if(CopyLow(symbol, tf, 0, count, low) < count)
     {
      Print(g_eaName, ": Failed to copy Low for ", EnumToString(tf));
      return false;
     }
   if(CopyClose(symbol, tf, 0, count, close) < count)
     {
      Print(g_eaName, ": Failed to copy Close for ", EnumToString(tf));
      return false;
     }
   return true;
  }
//+------------------------------------------------------------------+
