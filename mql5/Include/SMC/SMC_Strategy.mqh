//+------------------------------------------------------------------+
//| SMC_Strategy.mqh — Multi-timeframe SMC confluence engine         |
//+------------------------------------------------------------------+
#ifndef SMC_STRATEGY_MQH
#define SMC_STRATEGY_MQH
#include "SMC_Liquidity.mqh"
#include "SMC_Structure.mqh"
#include "SMC_FVG.mqh"

//+------------------------------------------------------------------+
bool AnalyzeSMC(const double &h1High[], const double &h1Low[],
                const double &m15High[], const double &m15Low[], const double &m15Close[],
                const double &m5High[], const double &m5Low[], const double &m5Close[],
                int swingLookback, double sweepTolerance, double minFvgGap,
                double pipSize, int h1Total, int m15Total, int m5Total,
                SSMCSignal &signal)
  {
   signal.valid = false;

   // Step 1: H1 bias
   ENUM_SMC_BIAS bias = DetermineBias(h1High, h1Low, swingLookback, h1Total);
   if(bias == SMC_BIAS_NEUTRAL)
      return false;

   // Step 2: M15 liquidity sweep
   SLiquiditySweep sweep;
   if(!DetectLiquiditySweep(m15High, m15Low, m15Close, swingLookback,
                            sweepTolerance, m15Total, sweep))
      return false;

   if(bias == SMC_BIAS_BULLISH && sweep.direction != SMC_DIR_BULLISH)
      return false;
   if(bias == SMC_BIAS_BEARISH && sweep.direction != SMC_DIR_BEARISH)
      return false;

   // Step 3: M15 MSS/CHoCH after sweep
   SStructureShift shift;
   if(!DetectStructureShift(m15High, m15Low, m15Close, sweep.sweepIndex,
                            swingLookback, m15Total, shift))
      return false;

   if(shift.direction != sweep.direction)
      return false;

   // Step 4: M5 FVG entry
   double currentPrice = m5Close[1];
   SFairValueGap fvg;
   int fvgStart = MathMax(2, m5Total - 50);
   if(!FindNearestFVG(m5High, m5Low, shift.direction, currentPrice,
                      minFvgGap, fvgStart, m5Total, fvg))
      return false;

   // Build signal
   signal.valid = true;
   signal.entryPrice = currentPrice;

   if(shift.direction == SMC_DIR_BULLISH)
     {
      signal.isBuy  = true;
      signal.slPrice = sweep.sweepPrice - pipSize;
      signal.reason  = StringFormat("H1 %s | M15 bullish sweep+CHoCH | M5 FVG [%.2f-%.2f]",
                                    (bias == SMC_BIAS_BULLISH ? "bullish" : "bearish"),
                                    fvg.bottom, fvg.top);
     }
   else
     {
      signal.isBuy  = false;
      signal.slPrice = sweep.sweepPrice + pipSize;
      signal.reason  = StringFormat("H1 %s | M15 bearish sweep+CHoCH | M5 FVG [%.2f-%.2f]",
                                    (bias == SMC_BIAS_BEARISH ? "bearish" : "bullish"),
                                    fvg.bottom, fvg.top);
     }

   return true;
  }

#endif
