# build_onepager_pdf.py
# -----------------------------------------------------------------------------
# ONE-PAGE A4 executive one-pager (features + benefits) for Narrative
# Intelligence, for AAP leadership. Same palette/design as the capability doc.
# -----------------------------------------------------------------------------
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Table, TableStyle, Spacer, HRFlowable)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

NAVY   = colors.HexColor("#0E2A5E")
NAVY2  = colors.HexColor("#1B3F86")
SAFFRON= colors.HexColor("#FF7A00")
GREEN  = colors.HexColor("#2E9E5B")
BLUE   = colors.HexColor("#2563EB")
LIGHT  = colors.HexColor("#F3F6FC")
INK    = colors.HexColor("#1A2433")
GREY   = colors.HexColor("#52607A")

try:
    pdfmetrics.registerFont(TTFont("Sym", "C:/Windows/Fonts/seguisym.ttf"))
    def mk(c): return '<font name="Sym" color="%s">▸</font>' % c
except Exception:
    def mk(c): return '<font color="%s"><b>&gt;</b></font>' % c

PRODUCT  = "Narrative Intelligence"
SUBTITLE = "AAP Punjab Digital War-Room for Real-Time Opponent Ad Intelligence"
TAGLINE  = "Track every opponent ad  -  Decode the narrative  -  Counter in minutes"
TOOLNO   = "Tool 3 of 5"
FOOT_L   = "CONFIDENTIAL - Prepared for Aam Aadmi Party, Punjab 2027"

PAGEW, PAGEH = A4
M = 36

def S(n, **k): return ParagraphStyle(n, **k)
st_name = S("name", fontName="Helvetica-Bold", fontSize=23, leading=26, textColor=colors.white)
st_sub  = S("sub", fontName="Helvetica", fontSize=11, leading=13.5, textColor=colors.HexColor("#BCD3F2"))
st_tag  = S("tag", fontName="Helvetica-Oblique", fontSize=9.5, leading=12, textColor=SAFFRON)
st_intro= S("intro", fontName="Helvetica", fontSize=9.8, leading=13.4, textColor=INK)
st_knum = S("knum", fontName="Helvetica-Bold", fontSize=22, leading=24, alignment=TA_CENTER)
st_klab = S("klab", fontName="Helvetica", fontSize=7.4, leading=9, alignment=TA_CENTER, textColor=GREY)
st_colt = S("colt", fontName="Helvetica-Bold", fontSize=10.5, leading=12.5, textColor=colors.white)
st_feat = S("feat", fontName="Helvetica", fontSize=9.2, leading=12.4, textColor=INK, spaceAfter=4.5)
st_imptitle = S("impt", fontName="Helvetica-Bold", fontSize=12.5, leading=14, textColor=SAFFRON)
st_imp  = S("imp", fontName="Helvetica", fontSize=9.6, leading=13, textColor=colors.HexColor("#E7EEFA"))

def furniture(canv, doc):
    canv.saveState()
    bx, bw = M, PAGEW - 2 * M
    ytop = PAGEH - M
    canv.setFillColor(NAVY); canv.rect(bx, ytop - 6, bw, 6, fill=1, stroke=0)
    canv.setFillColor(SAFFRON); canv.rect(bx, ytop - 9, bw, 3, fill=1, stroke=0)
    canv.setStrokeColor(colors.HexColor("#C9D4E8")); canv.setLineWidth(0.6)
    canv.line(bx, M + 14, bx + bw, M + 14)
    canv.setFont("Helvetica", 7); canv.setFillColor(GREY)
    canv.drawString(bx, M + 4, FOOT_L)
    canv.drawRightString(bx + bw, M + 4,
                         "%s - Campaign Technology Suite | Page %d" % (TOOLNO, doc.page))
    canv.restoreState()

def hexof(c):
    return "#%02X%02X%02X" % (int(c.red*255), int(c.green*255), int(c.blue*255))

def hero():
    cell = [Paragraph(PRODUCT, st_name), Spacer(1, 3), Paragraph(SUBTITLE, st_sub),
            Spacer(1, 4), Paragraph(TAGLINE, st_tag)]
    t = Table([[cell]], colWidths=[PAGEW - 2 * M])
    t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1), NAVY),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
        ("TOPPADDING",(0,0),(-1,-1),13),("BOTTOMPADDING",(0,0),(-1,-1),13)]))
    return [t, HRFlowable(width="100%", thickness=4, color=SAFFRON, spaceBefore=0, spaceAfter=0)]

def kpi_row(cards):
    cells = []
    for num, lab, col in cards:
        ns = ParagraphStyle("k", parent=st_knum, textColor=col)
        cells.append([Paragraph(num, ns), Spacer(1,1), Paragraph(lab, st_klab)])
    w = (PAGEW - 2*M)/4.0
    t = Table([cells], colWidths=[w]*4)
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),LIGHT),
        ("INNERGRID",(0,0),(-1,-1),1.4,colors.white),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5)]))
    return t

def feat_flow(items, color):
    hc = hexof(color)
    out = []
    for name, desc in items:
        out.append(Paragraph('%s <font color="%s"><b>%s</b></font>'
                             '<font color="#1A2433"> - %s</font>' % (mk(hc), hc, name, desc),
                             st_feat))
    return out

def two_col(left_title, left_items, lcolor, right_title, right_items, rcolor):
    gut = 16
    side = (PAGEW - 2*M - gut)/2.0
    bar_l = Table([[Paragraph(left_title, st_colt)]], colWidths=[side])
    bar_l.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),lcolor),
        ("LEFTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    bar_r = Table([[Paragraph(right_title, st_colt)]], colWidths=[side])
    bar_r.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),rcolor),
        ("LEFTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    head = Table([[bar_l, "", bar_r]], colWidths=[side, gut, side])
    head.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    body = Table([[feat_flow(left_items, lcolor), "", feat_flow(right_items, rcolor)]],
                 colWidths=[side, gut, side])
    body.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return [head, body]

def closing(lines):
    inner = [Paragraph("THE BOTTOM LINE", st_imptitle), Spacer(1, 5)]
    for t in lines:
        inner.append(Paragraph(t, st_imp))
        inner.append(Spacer(1, 3))
    t = Table([[inner]], colWidths=[PAGEW - 2*M])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),
        ("LINEBEFORE",(0,0),(0,-1),7,SAFFRON),("ROUNDEDCORNERS",[7,7,7,7]),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),14),
        ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),12)]))
    return t

# ---- copy -------------------------------------------------------------------
INTRO = ("Narrative Intelligence is a single-screen war-room that watches every active "
         "ad run by AAP's Punjab opponents - BJP, Congress and SAD - on the Meta Ad "
         "Library, around the clock. Claude AI reads each ad to decide who it attacks, "
         "which party is behind it and what it claims, then hands the team spend "
         "tracking, threat ranking and ready-to-post counters - all in one place.")

KPIS = [("3", "Opponent parties watched live", BLUE),
        ("24/7", "Always-on auto monitoring", SAFFRON),
        ("2-Way", "Against vs Pro-AAP spend", GREEN),
        ("100%", "Ads archived forever", NAVY2)]

FEATURES = [
  ("Live Opponent Tracking", "Every active BJP, Congress and SAD ad from Meta, auto-refreshed every 6 hours."),
  ("AI Reads Every Ad", "Claude tags each ad's stance (for or against AAP), sponsoring party and narrative - in Punjabi and Hindi."),
  ("Damage Radar", "Ranks the most dangerous anti-AAP ads first, so the team hits the real threats."),
  ("Spend Tracker", "Shows how much opponents spent attacking vs promoting AAP, party-wise and day-by-day."),
  ("Instant Counter", "One click turns any opponent ad into a ready Hindi rebuttal and a full strategy brief."),
  ("Permanent Archive", "Saves every ad forever - even the ones opponents quietly delete - with one-click Excel export."),
]

BENEFITS = [
  ("See the Whole Battlefield", "The entire opposition's ad activity on one screen, around the clock - nothing missed."),
  ("Respond in Minutes", "Answer a damaging ad with a data-backed Hindi counter in minutes, not hours."),
  ("Follow the Money", "Know exactly where opponent rupees are going - and expose it to leadership and press."),
  ("Never Lose Evidence", "Full history of every ad on demand, including deleted ones - proof whenever needed."),
  ("One Tool, Not Five", "Replaces 4-5 costly tools and an analyst team with one affordable, self-hosted system."),
  ("Built for AAP Punjab", "Custom-made for the 2027 fight, fluent in Punjabi and Hindi - not a generic foreign tool."),
]

CLOSING = [
  '<b><font color="#FFD9B0">From watching to winning:</font></b> the opposition spends crores to set the '
  'narrative - this tool lets AAP read it, expose it and out-message it the same day.',
  '<b><font color="#FFD9B0">Ready now:</font></b> live and running on a secure server, monitoring Punjab '
  'opponents 24/7 - ready to brief the team from day one.',
]

def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Narrative_Intelligence_OnePager.pdf")
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=M, rightMargin=M,
                          topMargin=M, bottomMargin=M)
    frame = Frame(M, M + 22, PAGEW - 2*M, PAGEH - 2*M - 22 - 16,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=furniture)])
    story = []
    story += hero()
    story.append(Spacer(1, 9))
    story.append(Paragraph(INTRO, st_intro))
    story.append(Spacer(1, 10))
    story.append(kpi_row(KPIS))
    story.append(Spacer(1, 13))
    story += two_col("WHAT IT DOES", FEATURES, BLUE, "WHY IT MATTERS", BENEFITS, GREEN)
    story.append(Spacer(1, 13))
    story.append(closing(CLOSING))
    doc.build(story)
    print("WROTE", out)

if __name__ == "__main__":
    main()
