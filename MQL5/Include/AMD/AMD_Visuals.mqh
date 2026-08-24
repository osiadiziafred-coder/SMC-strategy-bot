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

   void              DrawRange(const SSessionRange &range)
     {
      if(!m_cfg.showVisuals || range.high <= 0.0)
         return;
      const datetime t2 = (range.complete ? range.tEnd : TimeCurrent());
      Rect("ACC_RANGE", range.tStart, range.high, t2, range.low, C'30,90,160', true);
      Trend("ACC_HIGH", range.tStart, range.high, t2 + 6 * PeriodSeconds(PERIOD_H1), range.high,
            clrLime, STYLE_DASH, 1);
      Trend("ACC_LOW", range.tStart, range.low, t2 + 6 * PeriodSeconds(PERIOD_H1), range.low,
            clrCrimson, STYLE_DASH, 1);
      Label("ACC_HIGH_L", range.tStart, range.high, "Buy-side liquidity (session high)",
            clrLime, ANCHOR_LEFT_LOWER);
      Label("ACC_LOW_L", range.tStart, range.low, "Sell-side liquidity (session low)",
            clrCrimson, ANCHOR_LEFT_UPPER);
      Label("ACC_TITLE", range.tStart, range.high, "ACCUMULATION",
            clrDodgerBlue, ANCHOR_LEFT_LOWER);
     }

   void              DrawSweep(const SSweepEvent &sweep, const SSessionRange &range)
     {
      if(!m_cfg.showVisuals || !sweep.active)
         return;
      const datetime t1 = sweep.tSweep;
      const datetime t2 = (sweep.tReturned > 0 ? sweep.tReturned : TimeCurrent());
      if(sweep.setupDir == DIR_SELL)
         Rect("MANIP", t1, sweep.extreme, t2, range.high, C'200,120,20', true);
      else
         Rect("MANIP", t1, range.low, t2, sweep.extreme, C'200,120,20', true);
      Label("MANIP_L", t1, sweep.extreme, "MANIPULATION / LIQUIDITY SWEEP",
            clrOrange, ANCHOR_LEFT_LOWER);
     }

   void              DrawMss(const SStructureShift &mss)
     {
      if(!m_cfg.showVisuals || !mss.confirmed)
         return;
      Arrow("MSS", mss.tShift, mss.brokenLevel, mss.dir);
      Label("MSS_L", mss.tShift, mss.brokenLevel,
            "MSS / BOS  " + DirToString(mss.dir),
            (mss.dir == DIR_BUY ? clrAqua : clrHotPink), ANCHOR_LEFT);
      if(mss.hasFvg)
         Rect("FVG", mss.tShift, mss.fvgTop, TimeCurrent(), mss.fvgBottom, C'80,40,140', true);
     }

   void              DrawTradeLevels(const ENUM_TRADE_DIR dir, const double entry,
                                     const double sl, const double tp, const datetime t)
     {
      if(!m_cfg.showVisuals || dir == DIR_NONE)
         return;
      const datetime t2 = t + 8 * PeriodSeconds(PERIOD_H1);
      Trend("ENTRY", t, entry, t2, entry, clrWhite, STYLE_SOLID, 2);
      Trend("SL", t, sl, t2, sl, clrRed, STYLE_DOT, 1);
      Trend("TP", t, tp, t2, tp, clrGold, STYLE_DOT, 1);
      Label("ENTRY_L", t, entry, "ENTRY " + DirToString(dir), clrWhite, ANCHOR_LEFT);
      Label("SL_L", t, sl, "STOP LOSS", clrRed, ANCHOR_LEFT);
      Label("TP_L", t, tp, "TAKE PROFIT", clrGold, ANCHOR_LEFT);
      Arrow("SIGNAL", t, entry, dir);
     }

   void              DrawDashboard(const ENUM_SESSION_KIND session, const ENUM_AMD_PHASE phase,
                                   const SSessionRange &range, const SHtfBias &bias,
                                   const SSweepEvent &sweep, const string lastMsg)
     {
      if(!m_cfg.showDashboard)
         return;

      const string lines =
         "AMD SESSION EA\n" +
         "Session : " + SessionKindToString(session) + "\n" +
         "Phase   : " + PhaseToString(phase) + "\n" +
         "HTF bias: " + DirToString(bias.dir) + "\n" +
         "Range H : " + DoubleToString(range.high, SymbolDigits(m_symbol)) + "\n" +
         "Range L : " + DoubleToString(range.low,  SymbolDigits(m_symbol)) + "\n" +
         "Range   : " + DoubleToString(PriceToPoints(m_symbol, range.rangeSize), 1) + " pts\n" +
         "Sweep   : " + (sweep.active ? DirToString(sweep.setupDir) : "none") +
         (sweep.returned ? " (returned)" : "") + "\n" +
         lastMsg;

      Comment(lines);

      const string box = AMD_PREFIX + "DASH";
      if(ObjectFind(m_chart, box) < 0)
         ObjectCreate(m_chart, box, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(m_chart, box, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(m_chart, box, OBJPROP_XDISTANCE, 12);
      ObjectSetInteger(m_chart, box, OBJPROP_YDISTANCE, 22);
      ObjectSetInteger(m_chart, box, OBJPROP_XSIZE, 280);
      ObjectSetInteger(m_chart, box, OBJPROP_YSIZE, 188);
      ObjectSetInteger(m_chart, box, OBJPROP_BGCOLOR, C'12,16,28');
      ObjectSetInteger(m_chart, box, OBJPROP_BORDER_COLOR, clrDodgerBlue);
      ObjectSetInteger(m_chart, box, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(m_chart, box, OBJPROP_BACK, false);
      ObjectSetInteger(m_chart, box, OBJPROP_SELECTABLE, false);
     }
  };

#endif
