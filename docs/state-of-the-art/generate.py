"""Rebuild the PDF from the editable Markdown using ReportLab (pip install reportlab)."""
from pathlib import Path
import re, html
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image,Preformatted,KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
root=Path(__file__).resolve().parent
pdfmetrics.registerFont(TTFont('DejaVu','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuBold','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='AuditBody',fontName='DejaVu',fontSize=8.5,leading=13,spaceAfter=6,textColor=colors.HexColor('#243955')));styles.add(ParagraphStyle(name='AuditTitle',fontName='DejaVuBold',fontSize=23,leading=30,spaceAfter=18,textColor=colors.HexColor('#1d3557')));styles.add(ParagraphStyle(name='AuditHead',fontName='DejaVuBold',fontSize=14,leading=19,spaceBefore=14,spaceAfter=8,textColor=colors.HexColor('#315e7e'),keepWithNext=True));styles.add(ParagraphStyle(name='AuditSub',fontName='DejaVuBold',fontSize=10,leading=14,spaceBefore=9,spaceAfter=5,textColor=colors.HexColor('#315e7e'),keepWithNext=True));styles.add(ParagraphStyle(name='AuditCode',fontName='DejaVu',fontSize=6.8,leading=9,leftIndent=8,spaceAfter=8))
def fmt(s):
 s=html.escape(s);s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s);s=re.sub(r'`([^`]+)`',r'<font color="#295b78">\1</font>',s);return s
lines=(root/'OpenLabs3D_State_of_the_Art.md').read_text().splitlines();story=[];code=[];in_code=False
for line in lines:
 if line.startswith('```'):
  if in_code: story.append(Preformatted('\n'.join(code),styles['AuditCode']));code=[]
  in_code=not in_code;continue
 if in_code: code.append(line);continue
 if not line.strip():story.append(Spacer(1,3));continue
 if line.startswith('!['):
  m=re.search(r'\]\(([^)]+)\)',line)
  if m:
   path=root/m.group(1)
   if path.exists():
    im=Image(str(path));im._restrictSize(170*mm,125*mm);story.append(im)
  continue
 if line.startswith('# '):story.append(Paragraph(fmt(line[2:]),styles['AuditTitle']));continue
 if line.startswith('## Executive summary'):story.append(PageBreak())
 if line.startswith('## '):story.append(Paragraph(fmt(line[3:]),styles['AuditHead']));continue
 if line.startswith('### '):story.append(Paragraph(fmt(line[4:]),styles['AuditSub']));continue
 if line.startswith('|') and re.fullmatch(r'[| :\-]+',line):continue
 if line.startswith('|'):line=' · '.join(x.strip() for x in line.strip('|').split('|'))
 if line.startswith('- '):line='• '+line[2:]
 story.append(Paragraph(fmt(line),styles['AuditBody']))
def footer(canvas,doc):
 canvas.setFont('DejaVu',7);canvas.setFillColor(colors.HexColor('#71838c'));canvas.drawString(18*mm,12*mm,'OPENLABS3D  |  TECHNICAL ASSESSMENT  |  28 OCT 2026');canvas.drawRightString(192*mm,12*mm,str(doc.page))
SimpleDocTemplate(str(root/'OpenLabs3D_State_of_the_Art.pdf'),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=20*mm,title='OpenLabs3D — State of the Art & Technical Architecture Report',author='OpenLabs3D').build(story,onFirstPage=footer,onLaterPages=footer)
