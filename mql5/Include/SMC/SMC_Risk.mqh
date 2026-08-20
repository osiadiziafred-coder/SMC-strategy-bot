//+------------------------------------------------------------------+
//| SMC_Risk.mqh — Lot sizing, SL/TP, breakeven management           |
//+------------------------------------------------------------------+
#ifndef SMC_RISK_MQH
#define SMC_RISK_MQH

//+------------------------------------------------------------------+
double CalcLotSize(const string symbol, double balancePer001Lot,
                   double minLot, double maxLot)
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double lots    = (balance / balancePer001Lot) * 0.01;

   double symMin  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double symMax  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double symStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   lots = MathMax(minLot, MathMin(maxLot, lots));
   lots = MathMax(symMin, MathMin(symMax, lots));
   lots = MathFloor(lots / symStep) * symStep;

   return NormalizeDouble(lots, 2);
  }

//+------------------------------------------------------------------+
void CalcSLTP(bool isBuy, double entry, double sl, double rrRatio,
              double &outSL, double &outTP)
  {
   double risk = MathAbs(entry - sl);
   outSL = sl;
   if(isBuy)
      outTP = entry + risk * rrRatio;
   else
      outTP = entry - risk * rrRatio;
  }

//+------------------------------------------------------------------+
int CountOpenPositions(const string symbol, ulong magic)
  {
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionSelectByTicket(PositionGetTicket(i)))
        {
         if(PositionGetString(POSITION_SYMBOL) == symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)magic)
            count++;
        }
     }
   return count;
  }

//+------------------------------------------------------------------+
void ManageBreakeven(const string symbol, ulong magic, double breakevenAtR,
                     double pipSize)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)magic)
         continue;

      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl    = PositionGetDouble(POSITION_SL);
      double tp    = PositionGetDouble(POSITION_TP);
      long   type  = PositionGetInteger(POSITION_TYPE);

      double risk = MathAbs(entry - sl);
      if(risk <= 0)
         continue;

      double trigger = risk * breakevenAtR;
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

      bool slAtBE = (MathAbs(sl - entry) < pipSize * 0.5);

      if(type == POSITION_TYPE_BUY)
        {
         if(bid >= entry + trigger && !slAtBE)
           {
            MqlTradeRequest request = {};
            MqlTradeResult  result  = {};
            request.action   = TRADE_ACTION_SLTP;
            request.symbol   = symbol;
            request.position = ticket;
            request.sl       = NormalizeDouble(entry, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
            request.tp       = tp;
            if(!OrderSend(request, result))
               Print("Breakeven modify failed: ", GetLastError());
            else
               Print("Breakeven set for BUY #", ticket, " at ", entry);
           }
        }
      else if(type == POSITION_TYPE_SELL)
        {
         if(ask <= entry - trigger && !slAtBE)
           {
            MqlTradeRequest request = {};
            MqlTradeResult  result  = {};
            request.action   = TRADE_ACTION_SLTP;
            request.symbol   = symbol;
            request.position = ticket;
            request.sl       = NormalizeDouble(entry, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
            request.tp       = tp;
            if(!OrderSend(request, result))
               Print("Breakeven modify failed: ", GetLastError());
            else
               Print("Breakeven set for SELL #", ticket, " at ", entry);
           }
        }
     }
  }

#endif
