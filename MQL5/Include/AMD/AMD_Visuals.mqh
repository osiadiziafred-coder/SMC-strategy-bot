#ifndef AMD_VISUALS_MQH
#define AMD_VISUALS_MQH

#include "AMD_Utils.mqh"

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

   void              DrawRange(const SSessionRange &range, const string tag = "", const color fill = C'30,90,160')
     {
      if(!m_cfg.showVisuals || range.high <= 0.0)
         return;
      const datetime t2 = (range.complete ? range.tEnd : TimeCurrent());
      const string suffix = (tag == "" ? "" : "_" + tag);
      Rect("ACC_RANGE" + suffix, range.tStart, range.high, t2, range.low, fill, true);
      Trend("ACC_HIGH" + suffix, range.tStart, range.high, t2 + 6 * PeriodSeconds(PERIOD_H1), range.high,
            clrForestGreen, STYLE_DASH, 1);
      Trend("ACC_LOW" + suffix, range.tStart, range.low, t2 + 6 * PeriodSeconds(PERIOD_H1), range.low,
            clrFireBrick, STYLE_DASH, 1);
      Label("ACC_HIGH_L" + suffix, range.tStart, range.high, tag + " Buy-side liquidity (session high)",
            clrForestGreen, ANCHOR_LEFT_LOWER);
      Label("ACC_LOW_L" + suffix, range.tStart, range.low, tag + " Sell-side liquidity (session low)",
            clrFireBrick, ANCHOR_LEFT_UPPER);
      Label("ACC_TITLE" + suffix, range.tStart, range.high, "ACCUMULATION " + tag,
            clrDodgerBlue, ANCHOR_LEFT_LOWER);
     }

   void              DrawSweep(const SSweepEvent &sweep, const SSessionRange &range, const string tag = "")
     {
      if(!m_cfg.showVisuals || !sweep.active)
         return;
      const datetime t1 = sweep.tSweep;
      const datetime t2 = (sweep.tReturned > 0 ? sweep.tReturned : TimeCurrent());
      const string suffix = (tag == "" ? "" : "_" + tag);
      if(sweep.setupDir == DIR_SELL)
         Rect("MANIP" + suffix, t1, sweep.extreme, t2, range.high, C'200,120,20', true);
      else
         Rect("MANIP" + suffix, t1, range.low, t2, sweep.extreme, C'200,120,20', true);
      Label("MANIP_L" + suffix, t1, sweep.extreme, tag + " MANIPULATION / LIQUIDITY SWEEP",
            clrOrangeRed, ANCHOR_LEFT_LOWER);
     }

   void              DrawMss(const SStructureShift &mss, const string tag = "")
     {
      if(!m_cfg.showVisuals || !mss.confirmed)
         return;
      const string suffix = (tag == "" ? "" : "_" + tag);
      Arrow("MSS" + suffix, mss.tShift, mss.brokenLevel, mss.dir);
      Label("MSS_L" + suffix, mss.tShift, mss.brokenLevel,
            tag + " MSS / BOS  " + DirToString(mss.dir),
            (mss.dir == DIR_BUY ? clrTeal : clrMaroon), ANCHOR_LEFT);
      if(mss.hasFvg)
         Rect("FVG" + suffix, mss.tShift, mss.fvgTop, TimeCurrent(), mss.fvgBottom, C'80,40,140', true);
     }

   void              DrawTradeLevels(const ENUM_TRADE_DIR dir, const double entry,
                                     const double sl, const double tp, const datetime t)
     {
      if(!m_cfg.showVisuals || dir == DIR_NONE)
         return;
      const datetime t2 = t + 8 * PeriodSeconds(PERIOD_H1);
      const color entryClr = (dir == DIR_BUY ? clrTeal : clrMaroon);
      Trend("ENTRY", t, entry, t2, entry, entryClr, STYLE_SOLID, 2);
      Trend("SL", t, sl, t2, sl, clrFireBrick, STYLE_DOT, 2);
      Trend("TP", t, tp, t2, tp, clrDarkGoldenrod, STYLE_DOT, 2);
      Label("ENTRY_L", t, entry, "ENTRY " + DirToString(dir), entryClr, ANCHOR_LEFT);
      Label("SL_L", t, sl, "STOP LOSS", clrFireBrick, ANCHOR_LEFT);
      Label("TP_L", t, tp, "TAKE PROFIT", C'140,90,0', ANCHOR_LEFT);
      Arrow("SIGNAL", t, entry, dir);
     }

   bool              UseLightPanel(void) const
     {
      if(m_cfg.dashTheme == DASH_LIGHT)
         return(true);
      if(m_cfg.dashTheme == DASH_DARK)
         return(false);
      const color bg = (color)ChartGetInteger(m_chart, CHART_COLOR_BACKGROUND);
      return(ColorLuma(bg) >= 400);
     }

   // Each row is a read-only OBJ_EDIT so the text colour lives on the
   // control itself. A filled OBJ_RECTANGLE_LABEL paints over OBJ_LABEL
   // on many white-chart templates and leaves a blank box.
   void              DashRow(const string id, const int x, const int y,
                             const int width, const int height,
                             const string text, const color bg, const color fg,
                             const int size)
     {
      const string name = AMD_PREFIX + id;
      if(ObjectFind(m_chart, name) >= 0)
        {
         if((ENUM_OBJECT)ObjectGetInteger(m_chart, name, OBJPROP_TYPE) != OBJ_EDIT)
            ObjectDelete(m_chart, name);
        }
      if(ObjectFind(m_chart, name) < 0)
         ObjectCreate(m_chart, name, OBJ_EDIT, 0, 0, 0);
      ObjectSetInteger(m_chart, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(m_chart, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(m_chart, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(m_chart, name, OBJPROP_XSIZE, width);
      ObjectSetInteger(m_chart, name, OBJPROP_YSIZE, height);
      ObjectSetString(m_chart, name, OBJPROP_FONT, "Arial");
      ObjectSetInteger(m_chart, name, OBJPROP_FONTSIZE, size);
      ObjectSetInteger(m_chart, name, OBJPROP_COLOR, fg);
      ObjectSetInteger(m_chart, name, OBJPROP_BGCOLOR, bg);
      ObjectSetInteger(m_chart, name, OBJPROP_BORDER_COLOR, bg);
      ObjectSetInteger(m_chart, name, OBJPROP_READONLY, true);
      ObjectSetInteger(m_chart, name, OBJPROP_ALIGN, ALIGN_LEFT);
      ObjectSetInteger(m_chart, name, OBJPROP_BACK, false);
      ObjectSetInteger(m_chart, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(m_chart, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(m_chart, name, OBJPROP_ZORDER, 10);
      ObjectSetString(m_chart, name, OBJPROP_TEXT, " " + text);
     }

   void              DrawDashboard(const ENUM_SESSION_KIND session,
                                   const string h1status, const string m30status, const string m15status,
                                   const SSessionRange &range, const SHtfBias &bias,
                                   const double nextLot, const string lastMsg)
     {
      if(!m_cfg.showDashboard)
         return;

      Comment("");
      ObjectDelete(m_chart, AMD_PREFIX + "DASH");
      ObjectDelete(m_chart, AMD_PREFIX + "DASH_FRAME");

      const bool light = UseLightPanel();
      const color headerBg = (light ? C'10,55,120' : C'8,90,160');
      const color headerFg = clrWhite;
      const color rowBg    = (light ? C'230,238,248' : C'18,22,34');
      const color rowFg    = (light ? clrBlack : clrWhite);
      const color muteBg   = (light ? C'214,226,240' : C'24,30,44');
      const color muteFg   = (light ? C'20,40,70' : C'210,220,235');

      const int x = 10;
      const int w = 360;
      const int h = 22;
      int y = 18;

      DashRow("D_TITLE", x, y, w, h, "AMD  XAUUSDm  SESSION BOT", headerBg, headerFg, 10); y += h;
      DashRow("D_SYM",   x, y, w, h, "Symbol  : " + m_symbol, rowBg, rowFg, 9); y += h;
      DashRow("D_SES",   x, y, w, h, "Session : " + SessionKindToString(session), rowBg, rowFg, 9); y += h;
      DashRow("D_H1",    x, y, w, h, "H1      : " + h1status, rowBg, rowFg, 9); y += h;
      DashRow("D_M30",   x, y, w, h, "M30     : " + m30status, rowBg, rowFg, 9); y += h;
      DashRow("D_M15",   x, y, w, h, "M15     : " + m15status, rowBg, rowFg, 9); y += h;
      DashRow("D_BIAS",  x, y, w, h, "Bias    : " + DirToString(bias.dir), rowBg, rowFg, 9); y += h;
      DashRow("D_RH",    x, y, w, h, "Range H : " + DoubleToString(range.high, SymbolDigits(m_symbol)), rowBg, rowFg, 9); y += h;
      DashRow("D_RL",    x, y, w, h, "Range L : " + DoubleToString(range.low,  SymbolDigits(m_symbol)), rowBg, rowFg, 9); y += h;
      DashRow("D_LOT",   x, y, w, h, "Next lot: " + DoubleToString(nextLot, 2), rowBg, rowFg, 9); y += h;
      DashRow("D_POS",   x, y, w, h, "Max open: 1 position", rowBg, rowFg, 9); y += h;
      DashRow("D_MSG",   x, y, w, h, (lastMsg == "" ? "Waiting for AMD setup" : lastMsg), muteBg, muteFg, 8);
      ChartRedraw(m_chart);
     }
  };

#endif
