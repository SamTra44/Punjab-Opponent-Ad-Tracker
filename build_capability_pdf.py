# build_capability_pdf.py
# -----------------------------------------------------------------------------
# 2-page A4 "capability document" for Narrative Intelligence (Tool 3 of 5).
# Pure reportlab Platypus + BaseDocTemplate so content auto-flows across pages.
# -----------------------------------------------------------------------------
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Table, TableStyle, Spacer, KeepTogether, HRFlowable)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---- palette ----------------------------------------------------------------
NAVY   = colors.HexColor("#0E2A5E")
NAVY2  = colors.HexColor("#1B3F86")
SAFFRON= colors.HexColor("#FF7A00")
GREEN  = colors.HexColor("#2E9E5B")
BLUE   = colors.HexColor("#2563EB")
LIGHT  = colors.HexColor("#F3F6FC")
INK    = colors.HexColor("#1A2433")
GREY   = colors.HexColor("#52607A")
DKGREEN= colors.HexColor("#0B3D2E")
PEACH  = colors.HexColor("#FFD9B0")

# ---- triangle marker: use Segoe UI Symbol if available, else ASCII fallback --
MARK = "&#9656;"  # U+25B8
try:
    pdfmetrics.registerFont(TTFont("Sym", "C:/Windows/Fonts/seguisym.ttf"))
    def mk(c):  # coloured triangle
        return '<font name="Sym" color="%s">▸</font>' % c
except Exception:
    def mk(c):
        return '<font color="%s"><b>&gt;</b></font>' % c

PRODUCT  = "Narrative Intelligence"
SUBTITLE = "AAP Punjab Digital War-Room for Real-Time Opponent Ad Intelligence"
TAGLINE  = "Track every opponent ad  -  Decode the narrative  -  Counter in minutes"
TOOLNO   = "Tool 3 of 5"
FOOT_L   = "CONFIDENTIAL - Prepared for Aam Aadmi Party, Punjab 2027"

PAGEW, PAGEH = A4
M = 36

# ---- styles -----------------------------------------------------------------
def S(name, **kw):
    return ParagraphStyle(name, **kw)

st_name = S("name", fontName="Helvetica-Bold", fontSize=24, leading=27,
            textColor=colors.white)
st_sub  = S("sub", fontName="Helvetica", fontSize=11.5, leading=14,
            textColor=colors.HexColor("#BcD3F2".upper()))
st_tag  = S("tag", fontName="Helvetica-Oblique", fontSize=9.5, leading=12,
            textColor=SAFFRON)
st_intro= S("intro", fontName="Helvetica", fontSize=9.7, leading=13.4,
            textColor=INK)
st_knum = S("knum", fontName="Helvetica-Bold", fontSize=25, leading=27,
            alignment=TA_CENTER)
st_klab = S("klab", fontName="Helvetica", fontSize=7.5, leading=9.2,
            alignment=TA_CENTER, textColor=GREY)
st_modt = S("modt", fontName="Helvetica-Bold", fontSize=11, leading=13,
            textColor=colors.white)
st_feat = S("feat", fontName="Helvetica", fontSize=9.3, leading=12.9,
            textColor=INK, spaceAfter=3.4)
st_imptitle = S("impt", fontName="Helvetica-Bold", fontSize=12.5, leading=14,
               textColor=SAFFRON)
st_imp  = S("imp", fontName="Helvetica", fontSize=9.3, leading=12.8,
            textColor=colors.HexColor("#E7EEFA"), spaceAfter=3)

# ---- page furniture (top accent + footer) -----------------------------------
def furniture(canv, doc):
    canv.saveState()
    # top accent: navy 6pt bar + saffron 3pt line under it
    bx, bw = M, PAGEW - 2 * M
    ytop = PAGEH - M
    canv.setFillColor(NAVY)
    canv.rect(bx, ytop - 6, bw, 6, fill=1, stroke=0)
    canv.setFillColor(SAFFRON)
    canv.rect(bx, ytop - 6 - 3, bw, 3, fill=1, stroke=0)
    # footer
    canv.setStrokeColor(colors.HexColor("#C9D4E8"))
    canv.setLineWidth(0.6)
    canv.line(bx, M + 14, bx + bw, M + 14)
    canv.setFont("Helvetica", 7)
    canv.setFillColor(GREY)
    canv.drawString(bx, M + 4, FOOT_L)
    canv.drawRightString(bx + bw, M + 4,
                         "%s - Campaign Technology Suite | Page %d"
                         % (TOOLNO, doc.page))
    canv.restoreState()

def build_doc(path):
    doc = BaseDocTemplate(path, pagesize=A4,
                          leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M)
    # frame sits below the top accent (~16pt) and above the footer (~22pt)
    frame = Frame(M, M + 22, PAGEW - 2 * M, PAGEH - 2 * M - 22 - 16,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=furniture)])
    return doc

# ---- content blocks ---------------------------------------------------------
def hero():
    cell = [Paragraph(PRODUCT, st_name),
            Spacer(1, 3),
            Paragraph(SUBTITLE, st_sub),
            Spacer(1, 4),
            Paragraph(TAGLINE, st_tag)]
    t = Table([[cell]], colWidths=[PAGEW - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return [t, HRFlowable(width="100%", thickness=4, color=SAFFRON,
                          spaceBefore=0, spaceAfter=0)]

def kpi_row(cards):
    cells = []
    for num, lab, col in cards:
        ns = ParagraphStyle("k", parent=st_knum, textColor=col)
        cells.append([Paragraph(num, ns), Spacer(1, 1), Paragraph(lab, st_klab)])
    w = (PAGEW - 2 * M) / 4.0
    t = Table([cells], colWidths=[w] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("INNERGRID", (0, 0), (-1, -1), 1.4, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t

def module(title, color, feats):
    bar = Table([[Paragraph(title, st_modt)]], colWidths=[PAGEW - 2 * M])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    hexc = "#%02X%02X%02X" % (int(color.red * 255), int(color.green * 255),
                              int(color.blue * 255))
    flow = [bar, Spacer(1, 4)]
    for name, desc in feats:
        p = ('%s <font color="%s"><b>%s</b></font>'
             '<font color="#1A2433"> - %s</font>'
             % (mk(hexc), hexc, name, desc))
        flow.append(Paragraph(p, st_feat))
    flow.append(Spacer(1, 12))
    return KeepTogether(flow)

def usecases(items):
    bar = Table([[Paragraph("USE CASES", st_modt)]], colWidths=[PAGEW - 2 * M])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DKGREEN),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    gc = "#2E9E5B"
    flow = [bar, Spacer(1, 4)]
    for name, desc in items:
        p = ('%s <font color="%s"><b>%s</b></font>'
             '<font color="#1A2433"> - %s</font>' % (mk(gc), gc, name, desc))
        flow.append(Paragraph(p, st_feat))
    return KeepTogether(flow)

def impact(points):
    inner = [Paragraph("THE IMPACT", st_imptitle), Spacer(1, 5)]
    for lab, txt in points:
        inner.append(Paragraph(
            '<b><font color="#FFD9B0">%s:</font></b> %s' % (lab, txt), st_imp))
    t = Table([[inner]], colWidths=[PAGEW - 2 * M])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LINEBEFORE", (0, 0), (0, -1), 7, SAFFRON),
        ("ROUNDEDCORNERS", [7, 7, 7, 7]),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return KeepTogether([t])

# ---- the actual copy --------------------------------------------------------
INTRO = ("Narrative Intelligence is a single-screen digital war-room that watches every "
         "active political ad run by AAP's Punjab opponents - BJP, Congress and SAD - "
         "on the Meta Ad Library, around the clock. Claude AI reads each ad to decide who "
         "it attacks, which party is really behind it and what narrative it pushes, then "
         "turns that into spend tracking, threat ranking and ready-to-post counters. "
         "Every ad is archived forever, so the team always knows what the opposition is "
         "saying, spending and quietly deleting.")

KPIS = [("3", "Opponent parties tracked live - BJP, Congress, SAD", BLUE),
        ("6-Hr", "Hands-off auto-refresh cycle, running 24/7", SAFFRON),
        ("100%", "Ads archived permanently - active and stopped", GREEN),
        ("2-Way", "Spend split: Against-AAP vs Pro-AAP", NAVY2)]

MODULES = [
 ("MODULE 1  -  LIVE OPPONENT AD MONITORING", BLUE, [
   ("Meta Ad Library Sync", "Pulls every active ad from opponent official and proxy pages via Graph API v21, with full pagination, on a fixed schedule."),
   ("War-Room Dashboard", "Dark single-screen UI with a stat strip, party chips, region filter, live search and an ad-card grid showing spend, impressions, theme and a View-on-Meta link."),
   ("Auto-Refresh and Cache", "APScheduler refreshes the data every 6 hours into a thread-safe in-memory cache, so the dashboard always loads instantly."),
   ("Demo-Safe Fallback", "If the Meta token ever fails, the tool serves realistic sample data so a live presentation never breaks."),
 ]),
 ("MODULE 2  -  CLAUDE AI CLASSIFICATION ENGINE", SAFFRON, [
   ("Stance Detection", "Claude Haiku reads each ad and tags it For, Against or Neutral on AAP - by meaning, never by keyword."),
   ("Party Attribution", "Claude reads the ad message plus page name to find the real sponsoring party; a satirical pro-AAP page like 'Fraud to be Akali' is correctly AAP, not SAD."),
   ("Narrative Tagging", "Every ad is bucketed into a campaign narrative theme with a punchy, under-12-word plain-English summary."),
   ("Consistency Guards", "Logic rules auto-fix contradictions, while known official pages stay locked as ground truth."),
 ]),
 ("MODULE 3  -  THREAT and TREND INTELLIGENCE", GREEN, [
   ("Damage Radar", "Ranks anti-AAP ads by threat and damage level, so the team answers the most dangerous narratives first."),
   ("Trends Over Time", "Each refresh is snapshotted; charts show how spend, stance and narratives move, with auto-generated insight alerts."),
   ("Audience Vulnerability", "Computes which voter segments each opponent is targeting and where AAP is most exposed."),
   ("Forecast", "Claude Opus projects where opponent spend and narratives are heading next."),
 ]),
 ("MODULE 4  -  COUNTER-STRATEGY STUDIO", NAVY2, [
   ("Strategy Brief", "Claude Opus writes a full war-room counter-strategy brief in Hindi, straight from the live data."),
   ("Instant Counter", "Generates a ready-to-post rebuttal in Hindi or Hinglish for any single opponent ad."),
   ("Creative Generator", "Drafts counter ad copy and creative ideas on demand."),
   ("One-Tap Translate", "Converts any Punjabi or English ad into clean Hindi for the whole team in one click."),
 ]),
 ("MODULE 5  -  PERMANENT ARCHIVE and SPEND TRACKER", BLUE, [
   ("Ad Archive", "Stores every ad ever pooled forever, with first-seen and last-seen dates and an auto Active or Stopped status - revealing which ads opponents quietly killed."),
   ("Spend Tracker", "Splits estimated spend into Against-AAP versus Pro-AAP, party-wise and day-by-day, straight from the permanent archive."),
   ("Excel Export", "One-click .xlsx of live ads or the full archive, each row linking back to the Facebook page."),
   ("Dual-Backend Storage", "PostgreSQL in the cloud, SQLite on the production server - data survives every redeploy."),
 ]),
]

USECASES = [
 ("Morning War-Room Brief", "The team opens one screen and sees overnight opponent ads, top spenders and new attack narratives at a glance."),
 ("Rapid Rebuttal", "A damaging BJP ad appears; one click produces a Hindi counter-post ready to ship within minutes."),
 ("Spend Exposure", "Show leadership exactly how much opponents spent attacking AAP versus promoting it, broken down by party."),
 ("Narrative Early-Warning", "Trends and Forecast flag a rising attack narrative before it goes viral."),
 ("Leadership Strategy Memo", "Generate a Claude Opus counter-strategy brief to brief senior leadership in seconds."),
]

IMPACT = [
 ("Scale", "Watches every ad from three opponent parties and their proxy pages from a single screen, around the clock."),
 ("Speed", "Auto-refreshes every 6 hours and turns any ad into a ready Hindi counter in seconds."),
 ("Cost", "One self-hosted tool replaces a manual monitoring desk and pricey ad-intelligence subscriptions."),
 ("Control", "A permanent archive means no opponent ad is ever lost - even the ones they silently delete."),
 ("Edge", "Claude reads each ad like a strategist, so AAP answers narratives with data, not guesswork."),
]

def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Narrative_Intelligence_Detailed.pdf")
    doc = build_doc(out)
    story = []
    story += hero()
    story.append(Spacer(1, 9))
    story.append(Paragraph(INTRO, st_intro))
    story.append(Spacer(1, 11))
    story.append(kpi_row(KPIS))
    story.append(Spacer(1, 14))
    cols = [BLUE, SAFFRON, GREEN, NAVY2, BLUE]
    for (title, color, feats) in MODULES:
        story.append(module(title, color, feats))
    story.append(usecases(USECASES))
    story.append(Spacer(1, 8))
    story.append(impact(IMPACT))
    doc.build(story)
    print("WROTE", out)

if __name__ == "__main__":
    main()
