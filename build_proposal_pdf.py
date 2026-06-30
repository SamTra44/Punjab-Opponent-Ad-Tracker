# build_proposal_pdf.py
# -----------------------------------------------------------------------------
# ONE-PAGE A4 commercial proposal: Narrative Intelligence monthly engagement
# for AAP Punjab. Costs + 20% margin = Rs 3,00,000 / month. Pure reportlab.
# -----------------------------------------------------------------------------
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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
LIGHT2 = colors.HexColor("#E8EEF8")
INK    = colors.HexColor("#1A2433")
GREY   = colors.HexColor("#52607A")

# Rupee glyph: register a Unicode font if available, else fall back to "Rs ".
RUPEE = "Rs "
try:
    pdfmetrics.registerFont(TTFont("INR", "C:/Windows/Fonts/seguisym.ttf"))
    RUPEE = '<font name="INR">₹</font>'
except Exception:
    pass

def rs(n):
    return RUPEE + n

PRODUCT  = "Narrative Intelligence"
SUBTITLE = "Monthly Engagement & Cost Proposal  -  AAP Punjab 2027"
TAGLINE  = "10,000 ads tracked daily  -  AI analysis &amp; forecast  -  one monthly retainer"
TOOLNO   = "Commercial Proposal"
FOOT_L   = "CONFIDENTIAL - Prepared for Aam Aadmi Party, Punjab 2027"

PAGEW, PAGEH = A4
M = 36

def S(n, **k): return ParagraphStyle(n, **k)
st_name = S("name", fontName="Helvetica-Bold", fontSize=22, leading=25, textColor=colors.white)
st_sub  = S("sub", fontName="Helvetica", fontSize=11, leading=13.5, textColor=colors.HexColor("#BCD3F2"))
st_tag  = S("tag", fontName="Helvetica-Oblique", fontSize=9.3, leading=12, textColor=SAFFRON)
st_intro= S("intro", fontName="Helvetica", fontSize=9.6, leading=13.2, textColor=INK)
st_knum = S("knum", fontName="Helvetica-Bold", fontSize=20, leading=22, alignment=TA_CENTER)
st_klab = S("klab", fontName="Helvetica", fontSize=7.4, leading=9, alignment=TA_CENTER, textColor=GREY)
st_h4   = S("h4", fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=NAVY)
# table cell styles
st_th   = S("th", fontName="Helvetica-Bold", fontSize=9.5, leading=11.5, textColor=colors.white)
st_thr  = S("thr", parent=st_th, alignment=TA_RIGHT)
st_comp = S("comp", fontName="Helvetica-Bold", fontSize=9.6, leading=12, textColor=INK)
st_desc = S("desc", fontName="Helvetica", fontSize=8.7, leading=11, textColor=GREY)
st_amt  = S("amt", fontName="Helvetica-Bold", fontSize=9.8, leading=12, textColor=INK, alignment=TA_RIGHT)
st_subc = S("subc", fontName="Helvetica-Bold", fontSize=9.6, leading=12, textColor=NAVY)
st_suba = S("suba", fontName="Helvetica-Bold", fontSize=9.8, leading=12, textColor=NAVY, alignment=TA_RIGHT)
st_totc = S("totc", fontName="Helvetica-Bold", fontSize=11.5, leading=13, textColor=colors.white)
st_tota = S("tota", fontName="Helvetica-Bold", fontSize=13, leading=14, textColor=colors.white, alignment=TA_RIGHT)
st_feat = S("feat", fontName="Helvetica", fontSize=9.1, leading=12.3, textColor=INK, spaceAfter=2)
st_impt = S("impt", fontName="Helvetica-Bold", fontSize=12.5, leading=14, textColor=SAFFRON)
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
    canv.drawRightString(bx + bw, M + 4, "%s | Page %d" % (TOOLNO, doc.page))
    canv.restoreState()

def hero():
    cell = [Paragraph(PRODUCT, st_name), Spacer(1, 3), Paragraph(SUBTITLE, st_sub),
            Spacer(1, 4), Paragraph(TAGLINE, st_tag)]
    t = Table([[cell]], colWidths=[PAGEW - 2 * M])
    t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,-1), NAVY),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
        ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),12)]))
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
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5)]))
    return t

def cost_table():
    w = PAGEW - 2*M
    cw = [w*0.27, w*0.54, w*0.19]
    P = lambda t, s: Paragraph(t, s)
    # sub-item styles (compact, indented)
    sic = S("sic", fontName="Helvetica", fontSize=8.7, leading=10.5, textColor=INK)
    sid = S("sid", fontName="Helvetica", fontSize=8.0, leading=9.8, textColor=GREY)
    sia = S("sia", fontName="Helvetica", fontSize=8.7, leading=10.5, textColor=INK, alignment=TA_RIGHT)
    arr = '<font color="#FF7A00">&#9656;</font> '   # saffron arrow

    def sub(comp, desc, amt):
        return [P(arr + comp, sic), P(desc, sid), P(rs(amt), sia)]

    data = [
        [P("Cost Component", st_th), P("What it covers", st_th), P("Monthly", st_thr)],
        [P("Team / Salaries (A)", st_comp),
         P("6 employees &#215; " + rs("60,000") + " - developers, data analysts, "
           "operations &amp; support", st_desc),
         P(rs("3,60,000"), st_amt)],
        [P("Tool Cost / Month (B)", st_subc),
         P("Infrastructure &amp; AI - itemised below", st_desc),
         P(rs("3,20,000"), st_suba)],
        sub("Claude AI / Vision Analysis",
            "~10,000 ads/day classified + narrative forecast + counter-strategy (Anthropic billing)", "1,50,000"),
        sub("Server &amp; Cloud Infrastructure",
            "24/7 production server, compute, uptime, load handling", "60,000"),
        sub("Proxy &amp; IP Rotation",
            "Rotating proxies / IPs for reliable large-scale data collection", "40,000"),
        sub("Database, Storage &amp; Archive",
            "Permanent record of 3,00,000+ ads/month, indexing &amp; backups", "30,000"),
        sub("Maintenance, DevOps &amp; Security",
            "Updates, monitoring, security patches, incident response", "30,000"),
        sub("Domain, SSL, API &amp; Misc",
            "Domain, SSL, Meta API access &amp; misc infrastructure", "10,000"),
        [P("GRAND TOTAL  -  per month  (A + B)", st_totc), P("", st_desc),
         P(rs("6,80,000"), st_tota)],
    ]
    t = Table(data, colWidths=cw)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("BACKGROUND", (0,1), (-1,1), colors.white),      # Team (A)
        ("BACKGROUND", (0,2), (-1,2), LIGHT2),            # Tool Cost (B) group row
        ("BACKGROUND", (0,3), (-1,3), colors.white),      # sub-items (alternate)
        ("BACKGROUND", (0,4), (-1,4), LIGHT),
        ("BACKGROUND", (0,5), (-1,5), colors.white),
        ("BACKGROUND", (0,6), (-1,6), LIGHT),
        ("BACKGROUND", (0,7), (-1,7), colors.white),
        ("BACKGROUND", (0,8), (-1,8), LIGHT),
        ("BACKGROUND", (0,9), (-1,9), SAFFRON),           # grand total
        ("SPAN", (0,9), (1,9)),
        ("LEFTPADDING", (0,3), (0,8), 18),                # indent sub-items
        ("LINEBELOW", (0,0), (-1,0), 0.6, NAVY),
        ("LINEABOVE", (0,9), (-1,9), 1, NAVY2),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,2), 9), ("LEFTPADDING", (0,9), (-1,9), 9),
        ("RIGHTPADDING", (0,0), (-1,-1), 9),
        ("TOPPADDING", (0,0), (-1,-1), 4.5), ("BOTTOMPADDING", (0,0), (-1,-1), 4.5),
        ("TOPPADDING", (0,1), (-1,2), 6), ("BOTTOMPADDING", (0,1), (-1,2), 6),
        ("TOPPADDING", (0,9), (-1,9), 9), ("BOTTOMPADDING", (0,9), (-1,9), 9),
        ("BOX", (0,0), (-1,-1), 0.8, colors.HexColor("#C9D4E8")),
    ]))
    return t

def included(items):
    bar = Table([[Paragraph("INCLUDED EVERY MONTH", st_th)]], colWidths=[PAGEW-2*M])
    bar.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),GREEN),
        ("LEFTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    gc = "#2E9E5B"
    half = (len(items)+1)//2
    def col(lst):
        flow=[]
        for it in lst:
            flow.append(Paragraph('<font color="%s"><b>&#10003;</b></font> %s' % (gc, it), st_feat))
        return flow
    body = Table([[col(items[:half]), "", col(items[half:])]],
                 colWidths=[(PAGEW-2*M-16)/2, 16, (PAGEW-2*M-16)/2])
    body.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    return [bar, body]

def total_band():
    inner = [Paragraph("THE BOTTOM LINE", st_impt), Spacer(1, 5),
             Paragraph('<b><font color="#FFD9B0">All-inclusive monthly retainer:</font></b> '
                       + rs("6,80,000") + ' / month  =  Team / Salaries (A) ' + rs("3,60,000")
                       + '  +  Tool Cost / Month (B) ' + rs("3,20,000")
                       + '. Covers the 6-member team, AI analysis of ~10,000 ads a day, '
                       'narrative forecast, servers, data access and ongoing development. '
                       'No hidden or per-use charges.', st_imp)]
    t = Table([[inner]], colWidths=[PAGEW - 2*M])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),
        ("LINEBEFORE",(0,0),(0,-1),7,SAFFRON),("ROUNDEDCORNERS",[7,7,7,7]),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),14),
        ("TOPPADDING",(0,0),(-1,-1),11),("BOTTOMPADDING",(0,0),(-1,-1),11)]))
    return t

INTRO = ("A complete, fully-managed digital war-room delivered as a single monthly engagement: "
         "a 6-member team plus the tool that tracks and analyses roughly 10,000 opponent ads "
         "every day - over 3,00,000 a month - with Claude AI classification, narrative "
         "forecasting and ready counter-strategy, on secure 24/7 infrastructure.")

KPIS = [("10,000/day", "Ads tracked &amp; analysed by AI", BLUE),
        ("3,00,000", "Ads tracked per month", SAFFRON),
        ("6", "Team members (devs + analysts)", GREEN),
        (rs("6.8L"), "All-inclusive / month", NAVY2)]

INCLUDED = [
  "~10,000 ads/day tracked (BJP / Congress / SAD)",
  "3,00,000+ ads analysed &amp; archived per month",
  "Claude AI classification + narrative forecast",
  "Spend Tracker, Damage Radar &amp; Intelligence",
  "Ready counter-strategy &amp; rebuttals on demand",
  "Dedicated 6-member team + 24/7 secure server",
]

def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Narrative_Intelligence_Proposal.pdf")
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=M, rightMargin=M,
                          topMargin=M, bottomMargin=M)
    frame = Frame(M, M + 22, PAGEW - 2*M, PAGEH - 2*M - 22 - 16,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=furniture)])
    story = []
    story += hero()
    story.append(Spacer(1, 8))
    story.append(Paragraph(INTRO, st_intro))
    story.append(Spacer(1, 9))
    story.append(kpi_row(KPIS))
    story.append(Spacer(1, 11))
    story.append(Paragraph("MONTHLY COST BREAKDOWN  -  Salary (A) + Tool Cost (B)", st_h4))
    story.append(Spacer(1, 5))
    story.append(cost_table())
    story.append(Spacer(1, 12))
    story.append(total_band())
    doc.build(story)
    print("WROTE", out)

if __name__ == "__main__":
    main()
