#ifndef XAUUSDM_SMC_VISUAL_MQH
#define XAUUSDM_SMC_VISUAL_MQH

#define DASH_PREFIX SMC_PREFIX "DASH_"
#define OBJ_PREFIX  SMC_PREFIX "OBJ_"

void DeleteByPrefix(const string prefix)
  {
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
     {
      string name = ObjectName(0, i, -1, -1);
      if(StringFind(name, prefix) == 0)
         ObjectDelete(0, name);
     }
  }

void CleanupVisuals()
  {
   DeleteByPrefix(SMC_PREFIX);
  }

void CreateLabel(const string name, const int x, const int y, const string text, const color clr, const int size)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, size);
   ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
  }

void CreatePanelBg(const string name, const int x, const int y, const int w, const int h)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_BGCOLOR, C'18,24,32');
      ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, name, OBJPROP_COLOR, C'70,90,110');
      ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
  }

string M5ConfirmText()
  {
   if(g_ea_status == EA_STATUS_WAITING_M5)
      return "WAITING";
   if(g_ea_status == EA_STATUS_WAITING_RETEST)
      return "RETEST";
   if(g_m5_bullish_mss)
      return "BULL MSS";
   if(g_m5_bearish_mss)
      return "BEAR MSS";
   if(g_m5_bullish_bos)
      return "BULL BOS";
   if(g_m5_bearish_bos)
      return "BEAR BOS";
   if(g_m5_bias == BIAS_BULLISH)
      return "BULLISH";
   if(g_m5_bias == BIAS_BEARISH)
      return "BEARISH";
   return "NONE";
  }

void UpdateDashboard()
  {
   if(!ShowDashboard)
      return;

   int x = 12;
   int y = 22;
   CreatePanelBg(DASH_PREFIX "BG", x, y, 278, 268);

   color bias_clr = clrSilver;
   if(g_h1_bias == BIAS_BULLISH)
      bias_clr = clrLime;
   if(g_h1_bias == BIAS_BEARISH)
      bias_clr = clrOrangeRed;

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double lots = CalculateLotSizeFromBalance(bal);
   int positions = CountEAPositions();
   int spread = CurrentSpreadPoints();

   CreateLabel(DASH_PREFIX "T0", x + 12, y + 8,  g_symbol, clrGold, 11);
   CreateLabel(DASH_PREFIX "T1", x + 12, y + 28, "H1 Bias: " + BiasToText(g_h1_bias), bias_clr, 10);
   CreateLabel(DASH_PREFIX "T2", x + 12, y + 46, "M5 Confirmation: " + M5ConfirmText(), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T3", x + 12, y + 64, "Balance: $" + DoubleToString(bal, 2), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T4", x + 12, y + 82, "Lot Size: " + DoubleToString(lots, 2), clrAqua, 10);
   CreateLabel(DASH_PREFIX "T5", x + 12, y + 100, "Open Trades: " + IntegerToString(positions), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T6", x + 12, y + 118, "Spread: " + IntegerToString(spread), (spread > MaxSpreadPoints ? clrOrangeRed : clrWhite), 10);
   CreateLabel(DASH_PREFIX "T7", x + 12, y + 136, "Daily Trades: " + IntegerToString(g_daily.trades_today), clrWhite, 10);
   CreateLabel(DASH_PREFIX "T8", x + 12, y + 154, "Daily P/L: " + DoubleToString(g_daily.closed_pnl_today + FloatingPnL(), 2), (g_daily.closed_pnl_today + FloatingPnL() >= 0 ? clrLime : clrOrangeRed), 10);
   CreateLabel(DASH_PREFIX "T9", x + 12, y + 172, "Current R:R: " + DoubleToString(g_last_rr, 2), clrWhite, 10);
   CreateLabel(DASH_PREFIX "TA", x + 12, y + 190, "Status: " + StatusToText(g_ea_status), clrKhaki, 10);
   CreateLabel(DASH_PREFIX "TB", x + 12, y + 214, (g_h1_bias == BIAS_BULLISH ? "H1 BULLISH BIAS" : (g_h1_bias == BIAS_BEARISH ? "H1 BEARISH BIAS" : "H1 NO CLEAR BIAS")), bias_clr, 10);
   string extra = g_status_text;
   if(StringLen(extra) > 42)
      extra = StringSubstr(extra, 0, 42);
   CreateLabel(DASH_PREFIX "TC", x + 12, y + 236, extra, clrSilver, 8);
  }

void DrawHLineNamed(const string name, const double price, const color clr, const int style, const int width, const string text)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

void DrawRect(const string name, datetime t1, const double p1, datetime t2, const double p2, const color clr)
  {
   if(t2 <= t1)
      t2 = t1 + PeriodSeconds(InpAnalysisTF) * 8;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p1);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 1, p2);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   color fill = clr;
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, fill);
  }

void DrawTextAt(const string name, const datetime t, const double price, const string text, const color clr)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TEXT, 0, t, price);
   ObjectSetInteger(0, name, OBJPROP_TIME, t);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void DrawStructure()
  {
   DeleteByPrefix(OBJ_PREFIX);

   datetime t_now = TimeCurrent();

   if(ShowStructure)
     {
      int hs = MathMin(8, g_h1_high_count);
      for(int i = 0; i < hs; i++)
        {
         string n = OBJ_PREFIX + "H1H" + IntegerToString(i);
         DrawHLineNamed(n, g_h1_highs[i].price, clrTomato, STYLE_DOT, 1, "H1 SH");
         DrawTextAt(n + "L", g_h1_highs[i].time, g_h1_highs[i].price, "H1 SH", clrTomato);
        }
      int ls = MathMin(8, g_h1_low_count);
      for(int i = 0; i < ls; i++)
        {
         string n = OBJ_PREFIX + "H1L" + IntegerToString(i);
         DrawHLineNamed(n, g_h1_lows[i].price, clrDodgerBlue, STYLE_DOT, 1, "H1 SL");
         DrawTextAt(n + "L", g_h1_lows[i].time, g_h1_lows[i].price, "H1 SL", clrDodgerBlue);
        }
     }

   if(ShowZones)
     {
      if(g_active_demand.valid)
        {
         DrawRect(OBJ_PREFIX + "DEMAND", g_active_demand.time, g_active_demand.top, t_now, g_active_demand.bottom, C'0,80,40');
         DrawTextAt(OBJ_PREFIX + "DEMANDL", g_active_demand.time, g_active_demand.top, "H1 DEMAND", clrLime);
        }
      if(g_active_supply.valid)
        {
         DrawRect(OBJ_PREFIX + "SUPPLY", g_active_supply.time, g_active_supply.top, t_now, g_active_supply.bottom, C'90,20,20');
         DrawTextAt(OBJ_PREFIX + "SUPPLYL", g_active_supply.time, g_active_supply.top, "H1 SUPPLY", clrOrangeRed);
        }
     }

   if(ShowLiquidity)
     {
      int lh = MathMin(6, g_liq_high_count);
      for(int i = 0; i < lh; i++)
        {
         string n = OBJ_PREFIX + "LIQH" + IntegerToString(i);
         DrawHLineNamed(n, g_liq_highs[i].price, clrGold, STYLE_DASH, 1, "BUY-SIDE LIQ");
        }
      int ll = MathMin(6, g_liq_low_count);
      for(int i = 0; i < ll; i++)
        {
         string n = OBJ_PREFIX + "LIQL" + IntegerToString(i);
         DrawHLineNamed(n, g_liq_lows[i].price, clrGold, STYLE_DASH, 1, "SELL-SIDE LIQ");
        }
      if(g_bullish_sweep)
         DrawTextAt(OBJ_PREFIX + "SWEEP", g_last_bull_sweep.sweep_time, g_last_bull_sweep.sweep_extreme, "LIQUIDITY SWEEP", clrAqua);
      if(g_bearish_sweep)
         DrawTextAt(OBJ_PREFIX + "SWEEP2", g_last_bear_sweep.sweep_time, g_last_bear_sweep.sweep_extreme, "LIQUIDITY SWEEP", clrAqua);
     }

   if(g_m5_bullish_bos)
      DrawTextAt(OBJ_PREFIX + "M5BOS", g_m5_bos_time, g_m5_bos_level, "M5 BOS", clrLime);
   if(g_m5_bearish_bos)
      DrawTextAt(OBJ_PREFIX + "M5BOSB", g_m5_bos_time, g_m5_bos_level, "M5 BOS", clrOrangeRed);
   if(g_m5_bullish_mss)
      DrawTextAt(OBJ_PREFIX + "M5MSS", g_m5_mss_time, g_m5_bos_level, "M5 MSS", clrLime);
   if(g_m5_bearish_mss)
      DrawTextAt(OBJ_PREFIX + "M5MSSB", g_m5_mss_time, g_m5_bos_level, "M5 MSS", clrOrangeRed);

   if(ShowEntryLevels && g_last_plan.valid && CountEAPositions() > 0)
     {
      DrawHLineNamed(OBJ_PREFIX + "ENTRY", g_last_plan.entry, clrWhite, STYLE_SOLID, 1, (g_last_plan.direction > 0 ? "BUY ENTRY" : "SELL ENTRY"));
      DrawHLineNamed(OBJ_PREFIX + "SL", g_last_plan.sl, clrRed, STYLE_SOLID, 2, "SL");
      DrawHLineNamed(OBJ_PREFIX + "TP", g_last_plan.tp, clrLime, STYLE_SOLID, 2, "TP");
      DrawTextAt(OBJ_PREFIX + "RR", t_now, g_last_plan.tp, "RR " + DoubleToString(g_last_plan.rr, 2), clrWhite);
     }
  }

#endif
