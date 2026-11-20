import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "policies"
FONT_DIR = Path(__import__("reportlab").__file__).resolve().parent / "fonts"
pdfmetrics.registerFont(TTFont("Vera", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("Vera-Bold", str(FONT_DIR / "VeraBd.ttf")))


def read_sections(path: Path) -> list[tuple[int, str, str]]:
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^## (.+?) \(page (\d+)\)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(source))
    sections = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        body = re.sub(r"\s+", " ", source[body_start:body_end]).strip()
        sections.append((int(match.group(2)), match.group(1), body))
    return sections


def make_policy_pdf(path: Path, title: str, intro: str, sections: list[tuple[int, str, str]]) -> None:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PolicyTitle", parent=styles["Title"], fontName="Vera-Bold",
        fontSize=20, leading=26, textColor=colors.HexColor("#22304a"), alignment=TA_CENTER,
        spaceAfter=18,
    )
    section_style = ParagraphStyle(
        "PolicySection", parent=styles["Heading2"], fontName="Vera-Bold",
        fontSize=14, leading=19, textColor=colors.HexColor("#384d70"), spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "PolicyBody", parent=styles["BodyText"], fontName="Vera",
        fontSize=11, leading=17, textColor=colors.HexColor("#303744"),
    )
    story = [
        Spacer(1, 1.15 * inch),
        Paragraph("VOLTTECH CUSTOMER CARE", ParagraphStyle(
            "PolicyKicker", parent=styles["Normal"], fontName="Vera-Bold",
            fontSize=9, textColor=colors.HexColor("#6b5ce7"), alignment=TA_CENTER,
        )),
        Spacer(1, 12),
        Paragraph(title, title_style),
        Paragraph(intro, body_style),
    ]
    current_page = 1
    for page_number, heading, body in sorted(sections):
        while current_page < page_number:
            story.append(PageBreak())
            current_page += 1
        story.extend([Spacer(1, 0.3 * inch), Paragraph(heading, section_style), Paragraph(body, body_style)])
    document = SimpleDocTemplate(
        str(path), pagesize=letter, rightMargin=0.85 * inch, leftMargin=0.85 * inch,
        topMargin=0.8 * inch, bottomMargin=0.8 * inch, title=title,
        author="VoltTech Customer Care",
    )
    document.build(story)


def main() -> None:
    returns = read_sections(POLICY_DIR / "returns-and-warranty.md")
    shipping = read_sections(POLICY_DIR / "shipping.md")
    orders = read_sections(POLICY_DIR / "orders-and-payments.md")
    product_support = read_sections(POLICY_DIR / "product-support.md")
    make_policy_pdf(
        POLICY_DIR / "returns-and-warranty.pdf",
        "Returns & Limited Warranty",
        "This guide explains return eligibility and limited warranty coverage for VoltTech products. Keep proof of purchase and contact support if a policy clause needs human review.",
        returns,
    )
    make_policy_pdf(
        POLICY_DIR / "shipping.pdf",
        "Shipping Policy",
        "This policy describes standard delivery timelines, tracking updates, and how to report a parcel that is marked delivered but not received.",
        shipping,
    )
    make_policy_pdf(
        POLICY_DIR / "orders-and-payments.pdf",
        "Orders & Payments",
        "This guide covers checkout payments, receipt copies, order cancellations, and delivery-address changes.",
        orders,
    )
    make_policy_pdf(
        POLICY_DIR / "product-support.pdf",
        "Product Support",
        "This guide offers a small set of basic checks and explains when to stop and contact VoltTech support.",
        product_support,
    )


if __name__ == "__main__":
    main()
