from pathlib import Path
from markdown import markdown
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_LEFT

root = Path(r'd:\projects\Insurance_using_RAG')
md_path = root / 'PROJECT_REPORT.md'
text = md_path.read_text(encoding='utf-8')
html = markdown(text)

story = []
styles = getSampleStyleSheet()
styles['BodyText'].fontName = 'Helvetica'
styles['BodyText'].fontSize = 11
styles['Heading1'].fontName = 'Helvetica-Bold'
styles['Heading1'].fontSize = 16
styles['Heading2'].fontName = 'Helvetica-Bold'
styles['Heading2'].fontSize = 13

for line in html.split('<p>'):
    if not line.strip():
        continue
    if line.startswith('<h1') or line.startswith('<h2'):
        continue

# Simple fallback: convert markdown headings to paragraphs.
for line in text.splitlines():
    if not line.strip():
        continue
    if line.startswith('# '):
        story.append(Paragraph(line[2:], styles['Heading1']))
    elif line.startswith('## '):
        story.append(Paragraph(line[3:], styles['Heading2']))
    elif line.startswith('---'):
        story.append(Spacer(1, 8))
    else:
        story.append(Paragraph(line, styles['BodyText']))
    story.append(Spacer(1, 6))

pdf_path = root / 'PROJECT_REPORT.pdf'
doc = SimpleDocTemplate(str(pdf_path), pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
doc.build(story)
print(pdf_path)
