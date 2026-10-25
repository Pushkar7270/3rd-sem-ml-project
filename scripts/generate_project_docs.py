#!/usr/bin/env python3
"""Generate the Word project documentation.

Run from the repository root:
    uv run python scripts/generate_project_docs.py

Output:
    docs/Telco_Churn_Project_Documentation.docx
    docs/claude_ppt_master_prompt.txt
"""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from churn import config
from churn.data import prepare_dataset

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Telco_Churn_Project_Documentation.docx"
PROMPT_OUTPUT = ROOT / "docs" / "claude_ppt_master_prompt.txt"
SCREENSHOTS = ROOT / "docs" / "screenshots"

DARK = RGBColor(0x0B, 0x1F, 0x1A)
GREEN = RGBColor(0x0E, 0xA9, 0x6F)
MUTED = RGBColor(0x5E, 0x74, 0x6B)
LIGHT_GREEN = "E8F7F0"
HEADER_FILL = "0B3B2E"
ZEBRA_FILL = "F5FAF8"

metadata = json.loads(config.METADATA_PATH.read_text(encoding="utf-8"))
model_name = metadata["model_name"]
model_display = metadata["model_display_name"]
cv = metadata["cv_results"]
test = metadata["test_results"]
final = metadata["final_test_metrics"]
threshold = metadata["threshold"]
risk = metadata["risk_distribution"]
global_importance = metadata["global_importance"]
dataset_info = metadata["dataset"]

frame = prepare_dataset()

contract_rates = (
    frame.groupby("Contract", observed=True)["churn"].agg(["size", "mean"]).reset_index()
)
internet_rates = (
    frame.groupby("InternetService", observed=True)["churn"].agg(["size", "mean"]).reset_index()
)
payment_rates = (
    frame.groupby("PaymentMethod", observed=True)["churn"].agg(["size", "mean"]).reset_index()
)
monthly_churn = float(frame.loc[frame.churn == 1, "MonthlyCharges"].mean())
monthly_stay = float(frame.loc[frame.churn == 0, "MonthlyCharges"].mean())
tenure_churn = float(frame.loc[frame.churn == 1, "tenure"].mean())
tenure_stay = float(frame.loc[frame.churn == 0, "tenure"].mean())

TEAM = [
    ("Pushkar", "Project lead · ML & backend", "45%"),
    ("Karan", "Research · frontend & visual design", "35%"),
    ("Shaurya", "Data validation · testing & documentation support", "20%"),
]

RULES = [
    (
        "RET-01",
        "Any scored customer",
        "Retention specialist call within 48 hours",
        "Dedicated specialist + service review",
        "Engagement",
    ),
    (
        "RET-02",
        "Month-to-month contract",
        "Offer a 12/24-month commitment plan",
        "15–20% loyalty discount",
        "Contract",
    ),
    (
        "RET-03",
        "Fiber optic + monthly ≥ $70",
        "Audit plan against usage; right-size the speed tier",
        "$10–20/month credit or cheaper tier",
        "Pricing",
    ),
    (
        "RET-04",
        "Electronic check",
        "Assisted switch to autopay",
        "5% credit for 6 months",
        "Payment",
    ),
    (
        "RET-05",
        "No tech support (internet customer)",
        "Enable TechSupport and book a setup call",
        "3 months free TechSupport",
        "Service",
    ),
    (
        "RET-06",
        "No online security",
        "Add OnlineSecurity and guide activation",
        "3 months free, then bundled rate",
        "Service",
    ),
    (
        "RET-07",
        "Tenure ≤ 6 months",
        "Welcome call day 7, check-in day 30",
        "Onboarding concierge",
        "Engagement",
    ),
    (
        "RET-08",
        "Tenure ≥ 24 months",
        "Loyalty pricing review, named account contact",
        "Loyalty price + account manager",
        "Loyalty",
    ),
    (
        "RET-09",
        "Senior citizen",
        "Register for priority human support",
        "Priority line + simplified billing",
        "Service",
    ),
    (
        "RET-10",
        "Paperless billing ≥ $75",
        "Itemised bill review, paper option",
        "Bill audit + one-time $10 credit",
        "Billing",
    ),
    (
        "RET-11",
        "Both streaming add-ons ≥ $80 bill",
        "Package both streaming services",
        "Bundle discount",
        "Pricing",
    ),
    (
        "RET-12",
        "No device protection (> 6 months)",
        "Offer a DeviceProtection trial",
        "6 months free",
        "Service",
    ),
    (
        "RET-13",
        "P(churn) ≥ 0.65",
        "Personal, time-boxed save offer",
        "20% off for 3 months",
        "Pricing",
    ),
    (
        "RET-14",
        "Low risk",
        "Loyalty nurture, not discounts",
        "Rewards programme invitation",
        "Engagement",
    ),
]

FEATURES = [
    (
        "NumServices",
        "Count of subscribed services across phone, internet add-ons and streaming",
        "Product depth / switching cost",
    ),
    (
        "SupportServices",
        "Count of OnlineSecurity, OnlineBackup, DeviceProtection and TechSupport = Yes",
        "Service stickiness",
    ),
    (
        "StreamingServices",
        "Count of StreamingTV and StreamingMovies = Yes",
        "Entertainment bundle behaviour",
    ),
    ("IsNewCustomer", "1 when tenure ≤ 6 months", "First six months carry the highest churn risk"),
    ("HasFamily", "1 when Partner = Yes or Dependents = Yes", "Household stability"),
]


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def set_cell_margins(
    cell, top: int = 70, bottom: int = 70, left: int = 90, right: int = 90
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tc_pr.append(margins)


def set_table_borders(table, color: str = "D7E5DE", size: int = 4) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)
        borders.append(element)
    tbl_pr.append(borders)


def repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def add_table(doc, headers, rows, widths=None, font_size=8.4, header_fill=HEADER_FILL):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    header = table.rows[0]
    repeat_header(header)
    for index, text in enumerate(headers):
        cell = header.cells[index]
        set_cell_shading(cell, header_fill)
        set_cell_margins(cell)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(str(text))
        run.bold = True
        run.font.size = Pt(font_size)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.name = "Calibri"
    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(values):
            cell = cells[index]
            set_cell_margins(cell)
            if row_index % 2 == 1:
                set_cell_shading(cell, ZEBRA_FILL)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.05
            run = paragraph.add_run(str(value))
            run.font.size = Pt(font_size)
            run.font.name = "Calibri"
            run.font.color.rgb = DARK
    if widths:
        for index, width in enumerate(widths):
            for row in table.rows:
                row.cells[index].width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_bullets(doc, items, style="List Bullet"):
    for item in items:
        paragraph = doc.add_paragraph(style=style)
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.add_run(item)


def add_steps(doc, steps):
    """Numbered steps with a hanging indent (safe across Word template styles)."""
    for index, step in enumerate(steps, start=1):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.55)
        paragraph.paragraph_format.first_line_indent = Cm(-0.45)
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.line_spacing = 1.2
        number = paragraph.add_run(f"{index}.")
        number.bold = True
        number.font.color.rgb = GREEN
        number.font.size = Pt(9.8)
        paragraph.add_run(f"   {step}")


def add_body(doc, text, bold_prefix=None, italic=False, size=None, color=None, align=None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(7)
    paragraph.paragraph_format.line_spacing = 1.28
    if align is not None:
        paragraph.alignment = align
    if bold_prefix:
        run = paragraph.add_run(bold_prefix)
        run.bold = True
        run.font.color.rgb = DARK
    run = paragraph.add_run(text)
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    return paragraph


def add_callout(doc, title, text):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, "BFE8D5", 6)
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F1FAF6")
    set_cell_margins(cell, 130, 130, 170, 170)
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(3)
    run = paragraph.add_run(title)
    run.bold = True
    run.font.color.rgb = GREEN
    run.font.size = Pt(9.5)
    paragraph = cell.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.2
    run = paragraph.add_run(text)
    run.font.size = Pt(9.3)
    run.font.color.rgb = DARK
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code_block(doc, text):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, "D2E6DC", 5)
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F6F9F7")
    set_cell_margins(cell, 130, 130, 150, 150)
    first = True
    for line in text.splitlines():
        paragraph = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.05
        run = paragraph.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(7.6)
        run.font.color.rgb = RGBColor(0x1B, 0x33, 0x2B)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_heading(doc, text, level=1):
    heading = doc.add_heading(text, level=level)
    heading.paragraph_format.space_before = Pt(12 if level == 1 else 9)
    heading.paragraph_format.space_after = Pt(5)
    heading.paragraph_format.keep_with_next = True
    return heading


def add_page_number(paragraph):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def style_document(doc):
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.3)
    normal.font.color.rgb = DARK
    normal.paragraph_format.line_spacing = 1.28
    normal.paragraph_format.space_after = Pt(6)

    for level, size in ((1, 17), (2, 12.6), (3, 10.8)):
        style = doc.styles[f"Heading {level}"]
        style.font.name = "Calibri"
        style.font.bold = True
        style.font.size = Pt(size)
        style.font.color.rgb = DARK if level == 1 else GREEN
        style.paragraph_format.keep_with_next = True

    header = section.header.paragraphs[0]
    header.text = "Telco Churn Intelligence  ·  Project Documentation"
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in header.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(footer)
    for run in footer.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED


def page_break(doc):
    doc.add_page_break()


def cover(doc):
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(55)
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    cell = table.cell(0, 0)
    set_cell_shading(cell, "0B3B2E")
    set_cell_margins(cell, 190, 190, 220, 220)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run("3RD SEMESTER  ·  MACHINE LEARNING PROJECT")
    run.font.size = Pt(8.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x9F, 0xF5, 0xD2)

    title = doc.add_paragraph()
    title.paragraph_format.space_before = Pt(36)
    title.paragraph_format.space_after = Pt(8)
    run = title.add_run("Telco Customer Churn\nIntelligence")
    run.font.size = Pt(38)
    run.font.bold = True
    run.font.color.rgb = DARK
    run.font.name = "Calibri"

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(24)
    run = subtitle.add_run(
        "An explainable machine-learning system for churn prediction, risk scoring "
        "and personalised retention recommendations."
    )
    run.font.size = Pt(13.5)
    run.font.color.rgb = MUTED
    run.font.name = "Calibri"

    rule = doc.add_paragraph()
    rule.paragraph_format.space_after = Pt(22)
    p_pr = rule._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "18")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "2FF0A3")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)

    details = doc.add_paragraph()
    details.paragraph_format.space_after = Pt(3)
    run = details.add_run("Submitted by")
    run.font.size = Pt(8.5)
    run.font.bold = True
    run.font.color.rgb = MUTED
    for name, role, _ in TEAM:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(name)
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = DARK
        run = paragraph.add_run(f"   {role}")
        run.font.size = Pt(9)
        run.font.color.rgb = MUTED

    bottom = doc.add_paragraph()
    bottom.paragraph_format.space_before = Pt(70)
    run = bottom.add_run(
        "Python 3.12  ·  scikit-learn  ·  XGBoost  ·  SHAP  ·  FastAPI  ·  SQLite  ·  React + Vite dashboard"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED
    run.italic = True


def contents(doc):
    add_heading(doc, "Contents", 1)
    items = [
        ("1", "Executive summary"),
        ("2", "Problem statement and objectives"),
        ("3", "Dataset"),
        ("4", "Exploratory data analysis"),
        ("5", "Preprocessing and feature engineering"),
        ("6", "Models and methodology"),
        ("7", "Results and model selection"),
        ("8", "Explainability"),
        ("9", "Risk scoring and business value"),
        ("10", "Retention recommendation engine"),
        ("11", "System architecture and API"),
        ("12", "Frontend, database and step-by-step tutorial"),
        ("13", "Testing and quality"),
        ("14", "Limitations, ethics and future work"),
        ("15", "Viva preparation: 40 questions and answers"),
        ("16", "Team contributions"),
        ("17", "Master prompt for a free Claude presentation"),
        ("18", "Glossary"),
        ("19", "References"),
    ]
    for number, title in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(f"{number}.")
        run.bold = True
        run.font.color.rgb = GREEN
        run.font.size = Pt(10.5)
        run = p.add_run(f"   {title}")
        run.font.size = Pt(10.5)
        run.font.color.rgb = DARK


def section_summary(doc):
    add_heading(doc, "1. Executive summary", 1)
    add_body(
        doc,
        "Customer churn is the loss of existing customers to a competitor or to a cancelled "
        "subscription. It directly reduces recurring revenue and makes growth expensive because "
        "replacing a lost customer usually costs more than retaining one. This project builds an "
        "end-to-end, explainable churn intelligence system on the public IBM Telco Customer Churn "
        "dataset. The system predicts whether a customer is likely to leave, quantifies the risk, "
        "explains the drivers behind each score and converts that evidence into a personalised "
        "retention playbook.",
    )
    add_body(
        doc,
        f"Six classifiers were compared under an identical preprocessing pipeline and a stratified "
        f"5-fold cross-validation protocol. {model_display} won on the pre-registered selection "
        f"metric with a CV ROC-AUC of {cv[model_name]['roc_auc']['mean']:.4f} "
        f"(σ {cv[model_name]['roc_auc']['std']:.4f}). On the untouched test set it achieved "
        f"ROC-AUC {final['roc_auc']:.4f}, PR-AUC {final['pr_auc']:.4f}, recall "
        f"{final['recall']:.1%} and F1 {final['f1']:.3f} at the deployed threshold of "
        f"{threshold:.2f}.",
    )
    add_body(
        doc,
        "The system is more than a classifier. SHAP explanations translate model behaviour into "
        "customer-level reasons, risk bands turn probabilities into an operational queue, and a "
        "14-rule retention engine produces concrete offers. A FastAPI backend exposes the model, "
        "the customer book, analytics and saved actions. A dark, responsive web dashboard served "
        "at /app/ lets a retention team search customers, inspect a score, save actions and close "
        "the loop with real outcomes. SQLite provides the audit trail and action workflow with no "
        "server installation and no authentication required for the local demo.",
    )
    add_callout(
        doc,
        "Headline result",
        f"{model_display} · CV ROC-AUC {cv[model_name]['roc_auc']['mean']:.4f} · "
        f"test ROC-AUC {final['roc_auc']:.4f} · threshold {threshold:.2f} · "
        f"recall {final['recall']:.1%} · {len(frame):,} customers scored.",
    )


def section_problem(doc):
    add_heading(doc, "2. Problem statement and objectives", 1)
    add_body(
        doc,
        "Traditional churn analysis relies on historical summaries and manual rules. Such analysis "
        "is slow, hard to reproduce and rarely explains why a particular customer is at risk. A "
        "basic machine-learning model can produce a probability, but a probability alone does not "
        "tell a retention agent what to do next. The project therefore addresses three gaps: "
        "prediction quality, explanation and action.",
    )
    add_heading(doc, "2.1 Objectives", 2)
    add_bullets(
        doc,
        [
            "Build a reproducible binary classifier that predicts churn from customer attributes.",
            "Compare Logistic Regression, Decision Tree, Random Forest, XGBoost, KNN and SVM fairly.",
            "Select the final model using 5-fold cross-validated ROC-AUC.",
            "Quantify churn probability and assign a business-friendly risk band.",
            "Explain global and per-customer predictions using coefficients, feature importance and SHAP.",
            "Generate personalised retention recommendations for high-risk customers.",
            "Expose the system through a documented FastAPI backend and a usable web dashboard.",
            "Persist predictions, feedback and saved actions in a lightweight operational database.",
        ],
    )
    add_heading(doc, "2.2 Scope and non-goals", 2)
    add_body(
        doc,
        "The project is a decision-support prototype. It does not make autonomous offers, does not "
        "use causal inference and does not claim that a SHAP value is the customer's true reason for "
        "leaving. Authentication, multi-tenant access control, payment and production-scale data "
        "pipelines are deliberately out of scope for the semester demonstration.",
    )


def section_dataset(doc):
    add_heading(doc, "3. Dataset", 1)
    add_body(
        doc,
        "The system uses the IBM Telco Customer Churn dataset, publicly available on Kaggle "
        "(blastchar/telco-customer-churn). It contains one row per customer and is widely used as a "
        "benchmark for tabular binary classification.",
    )
    add_table(
        doc,
        ["Property", "Value"],
        [
            ("Rows", f"{dataset_info['rows']:,}"),
            ("Raw columns", "21"),
            ("Unique customers", f"{dataset_info['unique_customers']:,}"),
            ("Target", "Churn: Yes / No → 1 / 0"),
            ("Churn rate", f"{dataset_info['churn_rate']:.2%}"),
            (
                "Train / test split",
                f"{dataset_info['train_rows']:,} / {dataset_info['test_rows']:,} (stratified 80/20)",
            ),
            ("Missing values", "11 blanks in TotalCharges, all customers with tenure = 0"),
            ("Class balance", "Imbalanced: ~26.5% positive class"),
        ],
        widths=[2.0, 4.6],
    )
    add_heading(doc, "3.1 Important columns", 2)
    add_table(
        doc,
        ["Column", "Type", "Meaning"],
        [
            ("tenure", "Numeric", "Months the customer has stayed"),
            ("MonthlyCharges", "Numeric", "Current monthly bill"),
            ("TotalCharges", "Numeric*", "Lifetime charges; blank for brand-new customers"),
            ("Contract", "Categorical", "Month-to-month, One year or Two year"),
            ("InternetService", "Categorical", "DSL, Fiber optic or No"),
            (
                "PaymentMethod",
                "Categorical",
                "Electronic check, mailed check, bank transfer, credit card",
            ),
            (
                "OnlineSecurity … TechSupport",
                "Categorical",
                "Service add-ons; value includes 'No internet service'",
            ),
            ("StreamingTV / StreamingMovies", "Categorical", "Entertainment add-ons"),
            ("PaperlessBilling", "Categorical", "Yes / No"),
            ("Churn", "Target", "Yes / No"),
        ],
        widths=[1.9, 1.1, 3.7],
    )
    add_callout(
        doc,
        "Data-quality decision",
        "The blanks in TotalCharges are not missing-at-random. They belong to customers with "
        "tenure = 0, for whom lifetime spend is genuinely zero. They are filled with 0 rather "
        "than the column median, which would invent revenue that never existed.",
    )
    add_body(
        doc,
        "customerID is an identifier and is never used as a feature. Keeping it in the model would "
        "allow the model to memorise rows and would not generalise to new customers.",
    )


def section_eda(doc):
    add_heading(doc, "4. Exploratory data analysis", 1)
    add_body(
        doc,
        f"The churn base rate is {dataset_info['churn_rate']:.2%} ({int(frame.churn.sum()):,} of "
        f"{len(frame):,}). Customers who churned have a shorter average tenure "
        f"({tenure_churn:.1f} vs {tenure_stay:.1f} months) and a higher average monthly bill "
        f"(${monthly_churn:.2f} vs ${monthly_stay:.2f}). This is consistent with the intuition that "
        "new, high-bill customers are more price-sensitive and less attached.",
    )
    add_heading(doc, "4.1 Churn by contract", 2)
    add_table(
        doc,
        ["Contract", "Customers", "Churn rate"],
        [
            (row["Contract"], f"{int(row['size']):,}", f"{row['mean']:.2%}")
            for _, row in contract_rates.iterrows()
        ],
        widths=[2.4, 1.8, 1.6],
    )
    add_body(
        doc,
        "Month-to-month customers churn far more often than customers on one- or two-year plans. "
        "Contract type is therefore both a strong predictor and a strong retention lever: converting "
        "a month-to-month customer to an annual plan changes the commitment structure, not just the price.",
    )
    add_heading(doc, "4.2 Churn by internet service and payment method", 2)
    add_table(
        doc,
        ["Internet service", "Customers", "Churn rate"],
        [
            (row["InternetService"], f"{int(row['size']):,}", f"{row['mean']:.2%}")
            for _, row in internet_rates.iterrows()
        ],
        widths=[2.4, 1.8, 1.6],
    )
    add_table(
        doc,
        ["Payment method", "Customers", "Churn rate"],
        [
            (row["PaymentMethod"], f"{int(row['size']):,}", f"{row['mean']:.2%}")
            for _, row in payment_rates.iterrows()
        ],
        widths=[2.8, 1.6, 1.6],
    )
    add_body(
        doc,
        "Fiber-optic customers and electronic-check customers are higher-risk segments. These "
        "patterns motivate specific retention rules (plan review, autopay migration) rather than a "
        "generic discount for everyone.",
    )
    add_heading(doc, "4.3 What the EDA does not prove", 2)
    add_body(
        doc,
        "These are marginal associations. They do not prove that raising the monthly bill causes "
        "churn, nor that switching a payment method will retain a customer. The model and the "
        "recommendation engine are decision-support tools; offers should be validated with an A/B "
        "test or an uplift model.",
    )


def section_preprocessing(doc):
    add_heading(doc, "5. Preprocessing and feature engineering", 1)
    add_heading(doc, "5.1 Cleaning and target mapping", 2)
    add_bullets(
        doc,
        [
            "Strip whitespace from column names; keep customerID for joins, never as a feature.",
            "Convert TotalCharges to numeric; fill tenure = 0 blanks with 0 (semantic zero).",
            "Map Churn: Yes → 1, No → 0; validate that no other values exist.",
            "Drop the raw Churn column after creating the binary target.",
        ],
    )
    add_heading(doc, "5.2 Engineered features", 2)
    add_table(
        doc,
        ["Feature", "Definition", "Rationale"],
        [(name, definition, rationale) for name, definition, rationale in FEATURES],
        widths=[1.45, 3.65, 1.7],
    )
    add_body(
        doc,
        "Ratio features such as TotalCharges / tenure were tested and deliberately excluded from the "
        "final model. They are nearly collinear with tenure and monthly charges and produced unstable, "
        "counter-intuitive logistic coefficients and SHAP values. Removing them cost less than 0.001 "
        "ROC-AUC and made the explanations much easier to defend in a viva.",
    )
    add_heading(doc, "5.3 Leak-free pipeline", 2)
    add_body(
        doc,
        "Every model is a single scikit-learn Pipeline: numeric columns go through median imputation "
        "and StandardScaler; categorical columns go through most-frequent imputation and "
        "OneHotEncoder(handle_unknown='ignore'). The pipeline is cloned inside every cross-validation "
        "fold, so imputers, scalers and encoders are fitted only on the training part of that fold. "
        "This prevents data leakage.",
    )
    add_bullets(
        doc,
        [
            "Stratified 80/20 train–test split with random_state = 42.",
            "Scaling is required by KNN and SVM; it is harmless for trees and keeps one pipeline for a fair comparison.",
            "Unseen categories at serving time are ignored by the encoder instead of crashing the API.",
            "The test set is touched once, after model selection and threshold tuning, to avoid optimistic bias.",
        ],
    )


def section_models(doc):
    add_heading(doc, "6. Models and methodology", 1)
    add_body(
        doc,
        "Six model families were compared with deliberately comparable defaults. The goal is a fair "
        "model-family comparison rather than an exhaustive per-model hyperparameter search.",
    )
    add_table(
        doc,
        ["Model", "Role", "Key settings"],
        [
            (
                "Logistic Regression",
                "Linear, interpretable baseline",
                "C = 1.0, lbfgs, max_iter = 2000",
            ),
            (
                "Decision Tree",
                "Rule-based nonlinear baseline",
                "max_depth = 6, min_samples_leaf = 25",
            ),
            (
                "Random Forest",
                "Bagged trees",
                "400 trees, min_samples_leaf = 2, max_features = sqrt",
            ),
            ("XGBoost", "Gradient-boosted trees", "400 rounds, depth 4, lr 0.05, subsample 0.9"),
            (
                "K-Nearest Neighbours",
                "Distance-based learner",
                "k = 25, distance weights, scaled features",
            ),
            (
                "Support Vector Machine",
                "RBF margin classifier",
                "C = 1.0, Platt-calibrated probabilities",
            ),
        ],
        widths=[1.55, 1.65, 3.7],
    )
    add_heading(doc, "6.1 Cross-validation and selection", 2)
    add_body(
        doc,
        "Stratified 5-fold cross-validation is run on the training set only. For each fold, the whole "
        "pipeline is refitted, so preprocessing cannot leak. ROC-AUC is the primary metric because it "
        "measures ranking quality independently of a single threshold and is robust to the 26.5% "
        "class imbalance. Ties are broken by PR-AUC and then F1. The chosen model is refitted on the "
        "full training set and evaluated once on the held-out test set.",
    )
    add_heading(doc, "6.2 Threshold selection", 2)
    add_body(
        doc,
        f"Out-of-fold probabilities from the training set are used to choose the decision threshold. "
        f"The threshold that maximises F1 is {threshold:.2f}. F1 balances missed churners against "
        f"wasted retention offers. The threshold, risk bands and test metrics are stored in the model "
        f"artifact so the API cannot drift from the evaluation.",
    )
    add_heading(doc, "6.3 Metrics used", 2)
    add_table(
        doc,
        ["Metric", "Definition", "Why it matters here"],
        [
            (
                "ROC-AUC",
                "Probability that a random churner is ranked above a random stayer",
                "Primary model-selection metric; threshold-free",
            ),
            (
                "PR-AUC",
                "Area under precision–recall curve",
                "Sensitive to the minority churn class",
            ),
            (
                "Precision",
                "Of predicted churners, how many actually churned",
                "Cost of a wasted retention offer",
            ),
            ("Recall", "Of actual churners, how many were caught", "Cost of missing a churner"),
            ("F1", "Harmonic mean of precision and recall", "Balanced operating-point view"),
            ("Brier score", "Mean squared error of probabilities", "Probability calibration"),
        ],
        widths=[1.3, 3.2, 2.3],
    )


def section_results(doc):
    add_heading(doc, "7. Results and model selection", 1)
    rows = []
    for name in sorted(cv, key=lambda key: -cv[key]["roc_auc"]["mean"]):
        metric = cv[name]["roc_auc"]
        rows.append(
            (
                "★ " + name if name == model_name else name,
                f"{metric['mean']:.4f}",
                f"{metric['std']:.4f}",
                f"{test[name]['roc_auc']:.4f}",
                f"{test[name]['f1']:.4f}",
                f"{test[name]['pr_auc']:.4f}",
            )
        )
    add_table(
        doc,
        ["Model", "CV ROC-AUC", "CV σ", "Test ROC-AUC", "Test F1 @0.5", "Test PR-AUC"],
        rows,
        widths=[1.85, 1.0, 0.7, 1.1, 1.05, 1.0],
    )
    add_body(
        doc,
        f"{model_display} is selected because it has the highest mean 5-fold CV ROC-AUC. XGBoost is "
        f"close behind, but its additional nonlinearity does not justify the extra complexity on this "
        f"dataset, and the linear model is easier to explain. The selected model is not changed after "
        f"looking at test results.",
    )
    add_heading(doc, "7.1 Final held-out performance", 2)
    conf = final["confusion"]
    add_table(
        doc,
        ["Metric", "Value"],
        [
            ("Decision threshold", f"{threshold:.2f} (F1-maximising on out-of-fold predictions)"),
            ("ROC-AUC", f"{final['roc_auc']:.4f}"),
            ("PR-AUC", f"{final['pr_auc']:.4f}"),
            ("Recall", f"{final['recall']:.4f}"),
            ("Precision", f"{final['precision']:.4f}"),
            ("F1", f"{final['f1']:.4f}"),
            ("Accuracy", f"{final['accuracy']:.4f}"),
            ("Brier score", f"{final['brier']:.4f}"),
            ("Log loss", f"{final['log_loss']:.4f}"),
        ],
        widths=[2.2, 4.3],
    )
    add_heading(doc, "7.2 Confusion matrix", 2)
    add_table(
        doc,
        ["", "Predicted stay", "Predicted churn"],
        [
            ("Actual stay", f"{conf['true_negative']:,}", f"{conf['false_positive']:,}"),
            ("Actual churn", f"{conf['false_negative']:,}", f"{conf['true_positive']:,}"),
        ],
        widths=[2.2, 2.1, 2.1],
    )
    add_body(
        doc,
        f"At the tuned threshold the model catches {conf['true_positive']} of "
        f"{conf['true_positive'] + conf['false_negative']} churners while accepting "
        f"{conf['false_positive']} false positives. The high recall is intentional: a missed churner "
        f"is usually more expensive than a wasted retention call. The trade-off can be changed by "
        f"adjusting the threshold.",
    )
    add_heading(doc, "7.3 Why not accuracy?", 2)
    add_body(
        doc,
        "A naive model that predicts 'stay' for every customer would be about 73% accurate while "
        "catching zero churners. Accuracy alone is therefore misleading on this imbalanced dataset. "
        "ROC-AUC, PR-AUC, recall, F1 and the confusion matrix are used together.",
    )


def section_explainability(doc):
    add_heading(doc, "8. Explainability", 1)
    add_body(
        doc,
        "Explainability is a first-class requirement, not an afterthought. The system exposes global "
        "drivers, per-customer drivers and native model importance, and documents the difference "
        "between conditional model explanations and causal effects.",
    )
    add_heading(doc, "8.1 Methods", 2)
    add_table(
        doc,
        ["Method", "Scope", "Notes"],
        [
            ("LinearSHAP", "Selected logistic model", "Exact SHAP values for a linear classifier"),
            (
                "TreeSHAP",
                "Decision Tree, Random Forest, XGBoost",
                "Exact game-theoretic attribution for trees",
            ),
            (
                "Permutation SHAP",
                "KNN/SVM fallback",
                "Model-agnostic approximation; sampled for speed",
            ),
            ("Coefficients", "Logistic Regression", "Signed log-odds, globally interpretable"),
            ("Native feature importance", "Tree models", "Impurity/gain based importance"),
        ],
        widths=[1.6, 2.2, 3.1],
    )
    add_heading(doc, "8.2 Global drivers", 2)
    add_table(
        doc,
        ["Rank", "Driver", "Mean |SHAP|"],
        [
            (index, row["label"], f"{row['importance']:.4f}")
            for index, row in enumerate(global_importance[:8], start=1)
        ],
        widths=[0.7, 3.8, 1.6],
    )
    add_body(
        doc,
        "Internet service, contract type, tenure and monthly charges dominate the model's global "
        "behaviour. These are also the levers the retention playbook targets.",
    )
    add_heading(doc, "8.3 Per-customer explanations", 2)
    add_body(
        doc,
        "For a single customer the API returns the five strongest signed contributions. One-hot "
        "columns are collapsed back to the category the customer actually holds, so the response "
        "never says 'Fiber optic' for a customer with no internet. The top risk-increasing driver is "
        "exposed separately as top_risk_driver and is used in customer-facing copy.",
    )
    add_callout(
        doc,
        "Read SHAP correctly",
        "SHAP values are conditional on the other features. In this dataset monthly charges have a "
        "positive marginal association with churn, yet for a new fiber customer with streaming "
        "add-ons the incremental price contribution can be negative because the rest of the profile "
        "already explains the risk. SHAP answers 'why this prediction, given this profile', not "
        "'what happens if we raise the price by $10'.",
    )


def section_risk(doc):
    add_heading(doc, "9. Risk scoring and business value", 1)
    total = sum(risk.values())
    bands = metadata["risk_bands"]
    add_table(
        doc,
        ["Risk band", "Probability", "Customers", "Share"],
        [
            (
                band["level"].title(),
                f"{band['min_probability']:.2f} – {band['max_probability']:.2f}",
                f"{risk.get(band['level'], 0):,}",
                f"{risk.get(band['level'], 0) / total:.1%}",
            )
            for band in bands
        ],
        widths=[1.4, 1.8, 1.6, 1.3],
    )
    add_body(
        doc,
        "The low/medium boundary is the deployed decision threshold, so a customer is never both "
        "'low risk' and 'predicted to churn'. The bands are stored in the model artifact and returned "
        "by the API.",
    )
    add_heading(doc, "9.1 Financial formulas", 2)
    add_code_block(
        doc,
        "annual_revenue_at_risk = MonthlyCharges × 12 × P(churn)\n"
        "expected_remaining_months = min(1 / P(churn), 72)\n"
        "estimated_clv = MonthlyCharges × expected_remaining_months",
    )
    add_body(
        doc,
        "This CLV is an expected-revenue upper bound for prioritisation, excluding margin and "
        "discounting. It is not an accounting figure. Probabilities are model outputs and are not "
        "separately calibrated; Brier score and a reliability diagram are reported for transparency.",
    )


def section_recommendations(doc):
    add_heading(doc, "10. Retention recommendation engine", 1)
    add_body(
        doc,
        "The engine combines model evidence with a curated retention playbook. It is deliberately "
        "rule-based so every suggestion is auditable. Priority scores combine risk band, whether the "
        "triggering feature is a top SHAP driver and rule-specific business value. They are heuristics, "
        "not causal uplift estimates.",
    )
    add_table(
        doc,
        ["ID", "Trigger", "Action", "Offer", "Category"],
        RULES,
        widths=[0.55, 1.35, 2.15, 1.75, 0.85],
        font_size=7.5,
    )
    add_body(
        doc,
        "The API returns the five highest-priority actions by default. Low-risk customers receive a "
        "nurture track rather than discounts, and actions triggered by an absent service (for example "
        "tech support for a customer with no internet) are suppressed.",
    )


def section_architecture(doc):
    add_heading(doc, "11. System architecture and API", 1)
    add_table(
        doc,
        ["Layer", "Components", "Responsibility"],
        [
            (
                "Presentation",
                "RetainIQ dashboard (/app/)",
                "Dark SPA: overview, customers, scoring, insights, queue, history",
            ),
            (
                "API",
                "FastAPI + Pydantic",
                "Validation, prediction, explanations, analytics, actions, audit trail",
            ),
            (
                "Application",
                "ChurnService + ActionRepository",
                "Scoring orchestration, SHAP, risk bands, playbook, persistence",
            ),
            (
                "ML",
                "scikit-learn / XGBoost / SHAP pipeline",
                "Preprocessing + classifier + explanations",
            ),
            (
                "Data",
                "IBM CSV, joblib artifact, SQLite",
                "Customer book, trained model, predictions, feedback, actions",
            ),
        ],
        widths=[1.2, 2.2, 3.5],
    )
    add_body(
        doc,
        "The model is loaded once at API startup. The bundle contains the fitted pipeline, the decision "
        "threshold, a background sample for SHAP, the feature list and full experiment metadata. The "
        "bundle is written atomically so a running API never reads a partially written model.",
    )
    add_heading(doc, "11.1 Selected API endpoints", 2)
    add_table(
        doc,
        ["Method", "Endpoint", "Purpose"],
        [
            ("GET", "/health", "Liveness and loaded model/version/threshold"),
            ("GET", "/dashboard/summary", "KPI payload for the overview page"),
            ("GET", "/model/info", "Model, dataset, risk bands, top drivers, test metrics"),
            ("GET", "/model/metrics", "CV/test results and ROC/PR points"),
            ("GET", "/model/features", "Input field specification and example payload"),
            ("GET", "/model/card", "Generated model card"),
            ("POST", "/predict", "Score one customer with drivers and playbook"),
            ("POST", "/predict/batch", "Score 1–1,000 customers"),
            ("GET", "/customers/high-risk", "Ranked customer work queue"),
            ("GET", "/customers/{id}", "Live score, SHAP drivers and playbook"),
            ("GET", "/eda/summary", "Segment churn rates and correlations"),
            ("POST", "/actions", "Save a recommendation to the retention queue"),
            ("GET", "/actions", "List/filter saved actions"),
            ("PATCH", "/actions/{id}", "Update workflow status or note"),
            ("GET", "/history", "Recent prediction audit trail"),
            ("POST", "/feedback", "Record whether a scored customer actually churned"),
            ("GET", "/db/status", "SQLite engine, tables and size"),
        ],
        widths=[0.65, 2.15, 4.2],
        font_size=7.8,
    )


def section_frontend(doc):
    add_heading(doc, "12. Frontend, database and step-by-step tutorial", 1)
    add_body(
        doc,
        "The frontend is a React 19 + Vite single-page application served by FastAPI at /app/. The "
        "compiled bundle lives in frontend/dist/, so the demo does not require Node.js or a separate "
        "dev server at run time. The React source stays maintainable in frontend/src/. The visual "
        "language follows the supplied reference: "
        "near-black surfaces, neon mint accents, translucent glass panels with backdrop blur, thin "
        "borders, compact data-dense cards and a dark retention command-center feel.",
    )
    add_heading(doc, "12.1 Pages", 2)
    add_bullets(
        doc,
        [
            "Overview: hero, KPI cards, risk donut, contract churn chart, model gauge, global drivers and the highest-risk table.",
            "Customers: risk-band tabs, instant search, pagination, CSV export and a click-through drawer.",
            "Score customer: validated form, high/low demo profiles, probability gauge, SHAP drivers and playbook.",
            "Model insights: six-model comparison, ROC curve, SHAP drivers, segment charts and report gallery.",
            "Retention queue: saved actions with pending/contacted/accepted/declined workflow.",
            "Score history: every API prediction, outcome feedback and SQLite status.",
        ],
    )
    for filename, caption in [
        (
            "overview.png",
            "Overview: KPIs, risk distribution, model performance and the priority queue.",
        ),
        (
            "customer_drawer.png",
            "Customer drill-down: live probability, signed SHAP drivers and the retention playbook.",
        ),
        (
            "insights.png",
            "Model insights: comparison table, ROC curves, SHAP drivers and generated report figures.",
        ),
    ]:
        path = SCREENSHOTS / filename
        if path.exists():
            doc.add_picture(str(path), width=Inches(6.55))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption_paragraph = doc.add_paragraph()
            caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = caption_paragraph.add_run(caption)
            run.italic = True
            run.font.size = Pt(8)
            run.font.color.rgb = MUTED

    add_heading(doc, "12.2 SQLite: no install, no sign-in", 2)
    add_body(
        doc,
        "SQLite is embedded in Python's standard library. No database server, credentials or network "
        "service is required. The operational database lives at data/processed/churn.db and is created "
        "automatically on first API start. This is why the demo needs no sign-in: it is a local, "
        "single-team workspace.",
    )
    add_table(
        doc,
        ["Table", "Purpose", "Key fields"],
        [
            (
                "predictions",
                "Audit trail of every score served",
                "id, created_at, customer_id, probability, risk, threshold, revenue, payload",
            ),
            (
                "feedback",
                "Observed outcome for a prediction",
                "prediction_id, actual_churn, notes, created_at",
            ),
            (
                "retention_actions",
                "Saved playbook actions",
                "customer_id, recommendation_id, title, offer, status, note, updated_at",
            ),
        ],
        widths=[1.35, 2.35, 3.3],
    )
    add_body(
        doc,
        "WAL journaling keeps reads and writes stable during the demo. The action table enforces a "
        "unique (customer_id, recommendation_id) pair, so saving the same recommendation twice updates "
        "the existing action instead of duplicating it.",
    )
    frontend_tutorial(doc)


def frontend_tutorial(doc):
    """Step-by-step operating manual for the React dashboard."""

    def tutorial_image(filename, caption):
        path = SCREENSHOTS / filename
        if not path.exists():
            return
        doc.add_picture(str(path), width=Inches(6.55))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption_paragraph = doc.add_paragraph()
        caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = caption_paragraph.add_run(caption)
        run.italic = True
        run.font.size = Pt(8)
        run.font.color.rgb = MUTED

    add_heading(doc, "12.3 Step-by-step frontend tutorial", 2)
    add_body(
        doc,
        "This tutorial walks through the complete RetainIQ workflow, from starting the server to "
        "saving a retention action and recording the real outcome. It is written for the viva demo "
        "and for a first-time user who has never seen the system. No sign-in is required at any step.",
    )

    add_heading(doc, "12.3.1 Before you start", 3)
    add_body(
        doc,
        "The dashboard is served by FastAPI from the prebuilt React bundle. You only need Node.js if "
        "you want to modify the React source; the demo runs with Python alone.",
    )
    add_table(
        doc,
        ["What you want to do", "Requirements", "Command", "Open"],
        [
            (
                "Run the demo (recommended)",
                "Python 3.12, uv, trained artifacts",
                "uv run churn-serve",
                "http://127.0.0.1:8000/app/",
            ),
            (
                "Train first / retrain",
                "Dataset in data/raw/",
                "uv run churn-train",
                "Then start the server",
            ),
            (
                "Edit the React frontend",
                "Node.js 22+, npm",
                "cd frontend && npm install && npm run dev",
                "http://127.0.0.1:5173/app/",
            ),
            (
                "Rebuild the production bundle",
                "Node.js 22+, npm",
                "cd frontend && npm run build",
                "FastAPI serves frontend/dist/",
            ),
        ],
        widths=[1.55, 1.45, 2.05, 1.65],
        font_size=7.9,
    )
    add_steps(
        doc,
        [
            "Open a terminal in the project root.",
            "If artifacts/model.joblib does not exist, run `uv run churn-train` first (about 30 seconds).",
            "Start the server with `uv run churn-serve`. The default URL is http://127.0.0.1:8000.",
            "Open http://127.0.0.1:8000/app/ in Chrome, Firefox or Edge. Keep the trailing slash.",
            "Check the sidebar status chip. It should read 'Model online' with the model name and version.",
            "Check the topbar: it shows the current page and a Refresh button. If the page is already cached, press Ctrl+F5.",
            "Optional: open http://127.0.0.1:8000/docs for the interactive API reference.",
        ],
    )
    add_callout(
        doc,
        "Fast path for the viva",
        "Run `uv run churn-train` once, then `uv run churn-serve`, then open /app/. The prebuilt React "
        "bundle is already in the repository, so Node.js is not needed on the presentation machine. "
        "The SQLite database is created automatically and starts empty.",
    )

    add_heading(doc, "12.3.2 A 30-second interface tour", 3)
    add_table(
        doc,
        ["Interface element", "Where it is", "What it does"],
        [
            ("Sidebar", "Left", "Switch between Overview, Customers, Score customer, Insights, Queue and History; shows pending queue count and model status."),
            ("Topbar", "Top", "Breadcrumb, live data timestamp, Refresh, and a shortcut to Score customer."),
            ("KPI cards", "Overview", "Customer book, churn rate, high-risk count and annual revenue at risk."),
            ("Risk tabs", "Customers", "Switch between high, medium and low risk bands."),
            ("Search box", "Customers", "Filters the loaded band by customer ID, contract, payment method, internet service or top driver."),
            ("Table row", "Customers", "Opens the customer drawer with a live score, SHAP drivers and playbook."),
            ("Drawer", "Right side", "Detailed explanation and recommendations; closes with X, Esc or a click on the dimmed background."),
            ("Queue badge", "Sidebar", "Number of pending retention actions waiting for the team."),
            ("Toast", "Bottom right", "Confirms scoring, saving actions, status changes and feedback; errors appear in red."),
        ],
        widths=[1.25, 1.1, 4.35],
        font_size=8.0,
    )

    add_heading(doc, "12.3.3 Tutorial 1 — read the overview", 3)
    add_steps(
        doc,
        [
            "Open /app/. The Overview page loads automatically.",
            "Read the four KPI cards from left to right: total customers (7,043), historical churn (26.5%), high-risk customers (1,002) and annual revenue at risk ($705,663 for the high band).",
            "Inspect the risk donut. Red is high risk, amber is medium and mint is low. The legend shows counts and shares.",
            "Look at 'Churn by contract'. Month-to-month customers churn at 42.7%, versus 11.3% for one year and 2.8% for two years. This motivates the annual-contract playbook.",
            "Read the 'Model performance' panel. The gauge shows the held-out test ROC-AUC (0.846); the rows show recall at the deployed threshold, precision, F1 and Brier score.",
            "Check 'Global churn drivers'. The bars are mean absolute SHAP values. Internet service, contract, tenure and monthly charges dominate.",
            "Use 'Priority signals' on the hero to click a customer, or use 'Review high-risk queue' to open the full customer book.",
            "Scroll to 'Recent scores' and 'Database'. On a fresh install both are empty; they populate as soon as you score a customer or save an action.",
        ],
    )

    add_heading(doc, "12.3.4 Tutorial 2 — find and open a customer", 3)
    add_steps(
        doc,
        [
            "Click 'Customers' in the sidebar.",
            "Use the High risk / Medium / Low tabs to choose a band. The default is High risk.",
            "Type in the search box to filter by customer ID, contract, internet service, payment method or top risk driver.",
            "Use the pagination arrows or page numbers to move through the loaded list. The header shows how many customers are loaded and how many exist in the band.",
            "Click any table row. The drawer opens on the right with the live score.",
            "Read the drawer header: customer ID, risk badge, probability gauge, decision threshold and the 'Likely to churn / Likely to stay' verdict.",
            "Read the financial row: monthly charges, annual revenue at risk and estimated CLV.",
            "Check 'Why this score'. A red bar increases churn risk; a green bar decreases it. The value shown is the customer's actual category/value, not a category the customer does not have.",
            "Review 'Retention playbook'. Each card shows the action, description, concrete offer, category and priority (critical / high / medium).",
            "Close the drawer with the X button, the Esc key, or a click on the dark backdrop.",
        ],
    )

    add_heading(doc, "12.3.5 Tutorial 3 — score a customer", 3)
    add_steps(
        doc,
        [
            "Click 'Score customer' in the sidebar or the topbar.",
            "Fill the Account, Services and Billing sections. Tenure and Monthly charges are mandatory; the other fields have defaults but should be completed for a realistic score.",
            "Leave Total charges empty if you do not know it: the API derives it as tenure × monthly charges.",
            "Click 'High-risk demo' to load a month-to-month fiber customer with a short tenure, or 'Low-risk demo' for a two-year customer with support services.",
            "Click 'Score customer'. The right panel shows a loading state while the API computes the probability and SHAP values.",
            "Read the probability gauge and compare it with the threshold. A score above 32% is flagged as a predicted churner.",
            "Read the summary sentence. It names the strongest risk-increasing driver; the full signed list is shown below.",
            "Inspect the three financial boxes: monthly charges, annual revenue at risk and estimated CLV.",
            "Review the playbook. Add any action to the retention queue with its 'Add to queue' button; an ad-hoc demo profile is supported as long as a customer ID is present.",
            "Try the low-risk demo and compare the drivers. The low-risk result should show protective factors and far fewer aggressive offers.",
        ],
    )
    tutorial_image(
        "predict_result.png",
        "Score customer result: probability gauge, signed SHAP drivers, financial exposure and the ranked retention playbook.",
    )
    add_callout(
        doc,
        "Required fields and normalisation",
        "The API requires tenure and MonthlyCharges. If you select InternetService = No, internet add-ons are "
        "normalised to 'No internet service'; if PhoneService = No, MultipleLines becomes 'No phone service'. "
        "Invalid values such as tenure > 100, unknown categories or an extra field return a clear 422 error.",
    )

    add_heading(doc, "12.3.6 Tutorial 4 — save an action and work the queue", 3)
    add_steps(
        doc,
        [
            "In a customer drawer (or a prediction result), click 'Add to queue' on a recommendation.",
            "Wait for the button to change to 'Saved to queue ✓'. A toast confirms the write.",
            "Open 'Retention queue' from the sidebar. The pending badge decreases/increases with the workflow state.",
            "Use the All / pending / contacted / accepted / declined tabs to filter the table.",
            "Read a row: customer, recommendation title, offer, risk badge, status and last update time.",
            "Change the Status dropdown to contacted, accepted or declined. The change is persisted immediately in SQLite.",
            "Click 'Open' to return to the customer's live score and playbook.",
            "Save the same recommendation again if needed: the database updates the existing row instead of creating a duplicate.",
            "The queue needs no sign-in and survives an API restart because it is stored in data/processed/churn.db.",
        ],
    )
    tutorial_image(
        "queue.png",
        "Retention queue: saved playbook actions with a persistent pending/contacted/accepted/declined workflow.",
    )

    add_heading(doc, "12.3.7 Tutorial 5 — explore model insights", 3)
    add_steps(
        doc,
        [
            "Click 'Model insights' in the sidebar.",
            "Read the four KPI cards: CV ROC-AUC, test ROC-AUC, recall at the deployed threshold and Brier score.",
            "In the model comparison table, confirm that Logistic Regression is selected and compare it with XGBoost, Random Forest, Decision Tree, KNN and SVM.",
            "Read the ROC curve. The deployed model is drawn in solid mint; the other candidates are faded.",
            "Inspect 'Key churn drivers' and the segment charts for contract, internet service, payment method and tenure.",
            "Scroll to the Explainability gallery. Click any image to open the full-resolution training figure: SHAP beeswarm, ROC, PR, calibration, segments and confusion matrix.",
            "Open 'Model card' from the top-right button for the complete methodology and limitations.",
        ],
    )

    add_heading(doc, "12.3.8 Tutorial 6 — review history and close the loop", 3)
    add_steps(
        doc,
        [
            "Click 'Score history' in the sidebar.",
            "Read the operational KPIs: total predictions, predicted churners, observed churn rate and database details.",
            "Find a recent score in the table. The row shows when it was scored, the customer, risk band, probability, top driver and outcome status.",
            "Click 'Churned' or 'Retained' under an awaiting-feedback row to record the real outcome.",
            "Wait for the success toast. The outcome badge and observed churn rate update immediately.",
            "Open 'Database status' to confirm the SQLite file, size and row counts.",
            "Use the 'API reference' button if you want to inspect the same data from Swagger.",
        ],
    )

    add_heading(doc, "12.3.9 Tutorial 7 — export, reset and demo checklist", 3)
    add_body(doc, "Exporting the customer book:")
    add_steps(
        doc,
        [
            "Open Customers and choose a risk band.",
            "Optionally type a search query to narrow the loaded list.",
            "Click 'Export CSV'. The browser downloads a file named retainiq-<band>-risk.csv.",
            "Open it in Excel, LibreOffice or pandas for a viva appendix or offline review.",
        ],
    )
    add_body(doc, "Resetting the demo database (optional):")
    add_steps(
        doc,
        [
            "Stop the API with Ctrl+C.",
            "Delete data/processed/churn.db, churn.db-wal and churn.db-shm. The scored customer CSV is not affected.",
            "Start the API again with `uv run churn-serve`. The database is recreated empty.",
            "The Queue and History pages will show their empty states until you score or save something.",
        ],
    )
    add_body(doc, "Five-minute viva demo checklist:")
    add_table(
        doc,
        ["Minute", "Do this", "Say this"],
        [
            ("0:00–0:40", "Open Overview", "7,043 customers, 26.5% historical churn, 1,002 high-risk, 14.2% of the book."),
            ("0:40–1:30", "Customers → open a row", "The model scores 90% risk; the top driver is short tenure; the playbook is specific."),
            ("1:30–2:10", "Add action → Queue", "The action persists in SQLite; change its status; no sign-in is required."),
            ("2:10–3:00", "Score customer → high demo", "Show the gauge, threshold, SHAP signs and revenue at risk."),
            ("3:00–4:00", "Model insights", "Six models, 5-fold CV selection on ROC-AUC, SHAP and calibration."),
            ("4:00–4:40", "History → feedback", "Every score is audited; record the real outcome to close the loop."),
            ("4:40–5:00", "Close", "Business value, limitations, future work, questions."),
        ],
        widths=[1.05, 1.6, 4.0],
        font_size=8.0,
    )

    add_heading(doc, "12.4 Troubleshooting", 2)
    add_table(
        doc,
        ["Symptom", "Likely cause", "Fix"],
        [
            ("/app/ shows 404 or a blank page", "Server not running, wrong URL, or frontend/dist missing", "Start `uv run churn-serve`; open http://127.0.0.1:8000/app/; rebuild with `cd frontend && npm run build`."),
            ("API offline / red status chip", "Backend crashed or port conflict", "Check the terminal for the traceback; stop the conflicting process; restart `uv run churn-serve`."),
            ("503 'Model is not loaded'", "No trained artifact", "Run `uv run churn-train`, then restart the server."),
            ("Queue or History is empty", "Fresh SQLite database", "Score a customer and save an action; the tables populate automatically."),
            ("'Recommendation is not active' or save fails", "Customer/recommendation mismatch, or missing customer ID", "Open the customer from the scored book and save one of the currently returned recommendations; for ad-hoc scores provide a customer ID."),
            ("Port 8000 already in use", "Another process owns the port", "Run `CHURN_PORT=8010 uv run churn-serve` and open :8010/app/, or stop the conflicting process."),
            ("npm: command not found", "Node.js not installed on this machine", "The prebuilt bundle works without Node; install Node 22+ only if you need to rebuild the React source."),
            ("UI looks stale after an edit", "Browser cache or old bundle", "Hard-refresh Ctrl+F5; rebuild with `npm run build`; confirm the new hashed JS is served."),
            ("CORS error from another origin", "Frontend served from a different host/port", "Use the same origin /app/; or set CHURN_CORS_ORIGINS to the frontend origin."),
            ("Screenshots/doc out of date", "Frontend or model changed", "Re-run `uv run python scripts/generate_project_docs.py` after refreshing docs/screenshots."),
        ],
        widths=[1.55, 1.65, 3.5],
        font_size=8.0,
    )
    add_heading(doc, "12.5 How to read a result correctly", 2)
    add_bullets(
        doc,
        [
            "Probability is a model score, not a guarantee. The risk band is a business grouping; the threshold is the operational cut-off.",
            "The low/medium boundary equals the deployed threshold, so 'low risk' never means 'predicted churner'.",
            "SHAP values are conditional on the rest of the profile. A protective contribution does not mean the feature is always good; it means it is protective for this customer relative to the model baseline.",
            "top_risk_driver is the strongest risk-increasing factor and is the right field for customer-facing copy. top_drivers keeps the full signed list for analysts.",
            "Recommendations are rule-based heuristics; validate expensive offers with an A/B test or an uplift model.",
            "Annual revenue at risk = MonthlyCharges × 12 × P(churn). Estimated CLV is a revenue-only upper bound, not an accounting figure.",
        ],
    )


def section_testing(doc):
    add_heading(doc, "13. Testing and quality", 1)
    add_body(
        doc,
        "The repository contains 166 automated tests plus linting and a real headless-browser smoke "
        "test. The suite uses a small synthetic Telco-shaped dataset, so it runs without the Kaggle "
        "download or network access. Tests that need the real dataset or the trained artifact skip "
        "automatically when those files are absent.",
    )
    add_table(
        doc,
        ["Area", "What is verified"],
        [
            (
                "Data",
                "Cleaning, semantic TotalCharges fill, target mapping, split, engineered features",
            ),
            (
                "Features",
                "All six pipelines, unseen categories, imputation, deterministic probabilities",
            ),
            ("Models", "Registry, probability support, deterministic fits, coefficient alignment"),
            ("Evaluation", "Metric math, threshold tuning, curve downsampling, CV summaries"),
            (
                "Explainability",
                "SHAP shape/additivity, actual-category drivers, tree/permutation paths, native importance",
            ),
            (
                "Recommendations",
                "All 14 rules, priority ordering, limits, low-risk nurture, no-internet suppression",
            ),
            ("Risk", "Band boundaries, threshold alignment, revenue/CLV formulas"),
            (
                "API",
                "Every route, validation, 404/503, batch, dashboard, history, feedback, actions, static frontend",
            ),
            (
                "Persistence",
                "Prediction log, feedback, action CRUD, idempotent upsert, shared database file",
            ),
            (
                "End-to-end",
                "Fast training run, artifacts, metadata, scored CSV, 13 figures and model card",
            ),
        ],
        widths=[1.3, 5.4],
        font_size=8.2,
    )
    add_body(
        doc,
        "A Playwright smoke test exercised the live UI end to end: overview, customers, drawer, "
        "saving an action, the queue, scoring a customer, insights and history. It reported zero "
        "console errors and zero failed network requests.",
    )
    add_callout(
        doc,
        "Reproduction commands",
        "uv sync  →  uv run python scripts/download_data.py  →  uv run churn-train  →  "
        "uv run churn-serve  →  open http://127.0.0.1:8000/app/",
    )


def section_limits(doc):
    add_heading(doc, "14. Limitations, ethics and future work", 1)
    add_heading(doc, "14.1 Limitations", 2)
    add_bullets(
        doc,
        [
            "Observational data: associations are not causal effects; offers need A/B or uplift validation.",
            "The dataset is US-centric and partly synthetic; performance may drift in other markets.",
            "Probabilities are not post-hoc calibrated; Brier score and reliability are reported.",
            "The threshold optimises F1, not the real monetary cost of a missed churner versus a wasted offer.",
            "Recommendations are hand-written heuristics, not learned uplift. Offers need eligibility and cost constraints.",
            "CLV is revenue-only, with a capped expected tenure and no margin or discounting.",
            "SHAP explains the model, not the customer's true reason for leaving.",
        ],
    )
    add_heading(doc, "14.2 Responsible use", 2)
    add_bullets(
        doc,
        [
            "Use the model to target support and offers, never to deny service or price discriminatorily.",
            "Review gender and senior-status usage; monitor for disparate impact.",
            "Keep a human in the loop for customer-facing offers.",
            "Do not expose raw customer payloads beyond the local demo; add authentication and role-based access before production.",
            "Monitor drift in feature distributions, calibration and business outcomes; retrain when the product portfolio changes.",
        ],
    )
    add_heading(doc, "14.3 Future work", 2)
    add_bullets(
        doc,
        [
            "Nested cross-validation and Bayesian/random hyperparameter search.",
            "Probability calibration (isotonic or Platt) and cost-sensitive threshold optimisation per channel.",
            "Uplift modelling and causal retention targeting.",
            "Scheduled retraining, drift monitoring and model registry/versioning.",
            "PostgreSQL/MySQL + authentication for a multi-user deployment.",
            "Docker, CI/CD, rate limiting and audit logging.",
            "Frontend A/B testing of retention offers and a closed-loop dashboard.",
        ],
    )


def section_viva(doc):
    add_heading(doc, "15. Viva preparation: 40 questions and answers", 1)
    qa = [
        (
            "What is customer churn?",
            "Churn is the loss of an existing customer — cancellation, non-renewal or migration to a competitor. In this dataset it is the binary Churn column.",
        ),
        (
            "Why is churn prediction important?",
            "Recurring revenue falls and acquisition costs rise. Early identification lets the business intervene before the customer leaves.",
        ),
        (
            "Why use machine learning instead of fixed rules?",
            "Churn depends on many interacting attributes. A model learns nonlinear and multivariate patterns and produces a probability, while rules remain useful for the action layer.",
        ),
        (
            "Is this supervised or unsupervised learning?",
            "Supervised binary classification: the historical Churn label is the target.",
        ),
        (
            "Why is accuracy a bad primary metric?",
            "The classes are imbalanced (~26.5% churn). Predicting 'stay' for everyone gives ~73% accuracy while catching zero churners.",
        ),
        (
            "Describe the dataset.",
            "7,043 IBM Telco customers, 21 raw columns, one row per customer, 26.5% churn.",
        ),
        (
            "What is the target distribution?",
            "About 1,869 churners and 5,174 non-churners, a roughly 1:2.8 imbalance.",
        ),
        (
            "What was wrong with TotalCharges?",
            "Eleven blank strings for customers with tenure = 0. They are semantic zeros, so they are filled with 0 rather than the median.",
        ),
        (
            "Why not use customerID?",
            "It is an arbitrary identifier with no generalisable signal; using it risks memorisation and leakage.",
        ),
        (
            "Which features were engineered?",
            "NumServices, SupportServices, StreamingServices, IsNewCustomer and HasFamily.",
        ),
        (
            "Why were ratio features removed?",
            "TotalCharges/tenure is strongly collinear with tenure and monthly charges; it produced unstable coefficients and counter-intuitive SHAP values for less than 0.001 ROC-AUC.",
        ),
        (
            "What is a train/test split?",
            "A hold-out partition used to estimate generalisation. Here it is stratified 80/20 with random_state 42.",
        ),
        (
            "Why stratify the split?",
            "To preserve the churn rate in both partitions, which stabilises evaluation on an imbalanced dataset.",
        ),
        (
            "What is data leakage?",
            "Information from outside the training fold (or from the future) influencing training. It produces optimistic scores that collapse in production.",
        ),
        (
            "How is leakage prevented?",
            "All preprocessing lives inside a Pipeline that is cloned and fitted within each CV fold; the test set is touched once.",
        ),
        (
            "Why use a Pipeline?",
            "It bundles imputation, scaling, encoding and the classifier into one reproducible object and makes serving identical to training.",
        ),
        (
            "Why one-hot encode categoricals?",
            "Models need numeric input; one-hot avoids implying an order between categories such as contract types.",
        ),
        (
            "What happens to an unseen category at serving time?",
            "OneHotEncoder(handle_unknown='ignore') emits all zeros for that feature instead of raising an error.",
        ),
        (
            "Why scale features?",
            "KNN and SVM are distance/gradient sensitive. Scaling is harmless for trees and keeps a common preprocessing path.",
        ),
        (
            "What is 5-fold cross-validation?",
            "The training set is split into five folds; each fold is held out once while the model trains on the other four. The five scores are averaged.",
        ),
        (
            "Why was ROC-AUC the selection metric?",
            "It measures ranking quality across all thresholds and is insensitive to the class prior; the project specification selected on CV ROC-AUC.",
        ),
        (
            "Why not select on test performance?",
            "That would leak the test set into model choice and give an optimistic final estimate.",
        ),
        (
            "Why is Logistic Regression the final model?",
            f"It has the highest mean CV ROC-AUC ({cv[model_name]['roc_auc']['mean']:.4f}); XGBoost was close but adds complexity without enough gain.",
        ),
        (
            "What is the logistic regression equation?",
            "P(churn) = 1 / (1 + exp(-(β0 + β1x1 + … + βnxn))). Coefficients are log-odds changes.",
        ),
        (
            "How does a Decision Tree differ?",
            "It recursively splits the feature space into leaves; interpretable but high variance, controlled here with depth and leaf-size limits.",
        ),
        (
            "Random Forest vs XGBoost?",
            "Random Forest averages many deep, independent trees (bagging). XGBoost builds trees sequentially, each correcting the previous residual (boosting).",
        ),
        (
            "Why were KNN and SVM weaker?",
            "KNN suffers from high-dimensional one-hot distance concentration; the RBF SVM is competitive but slightly behind and harder to explain.",
        ),
        (
            "What does ROC-AUC mean intuitively?",
            "The probability that a randomly chosen churner receives a higher risk score than a randomly chosen stayer.",
        ),
        (
            "What is PR-AUC and when is it better?",
            "Area under the precision–recall curve. It focuses on the minority positive class and is more informative under strong imbalance.",
        ),
        (
            "Precision vs recall in this business?",
            "Recall is the share of churners caught; precision is the share of predicted churners who really churn. Missed churners are usually more expensive than wasted offers.",
        ),
        (
            "Why is the threshold 0.32?",
            "It maximises F1 on out-of-fold training predictions, raising recall to about 74% at the cost of some precision.",
        ),
        (
            "What does the confusion matrix show?",
            f"At the tuned threshold: {final['confusion']['true_positive']} true churners caught, {final['confusion']['false_negative']} missed, {final['confusion']['false_positive']} false alarms and {final['confusion']['true_negative']} correct stays.",
        ),
        (
            "What is the Brier score?",
            "Mean squared difference between predicted probabilities and 0/1 outcomes; lower is better and it rewards calibration.",
        ),
        (
            "What is SHAP?",
            "SHAP assigns each feature a contribution to a prediction using Shapley values from cooperative game theory. Contributions are additive.",
        ),
        (
            "LinearSHAP vs TreeSHAP vs permutation SHAP?",
            "LinearSHAP is exact for linear models, TreeSHAP is exact for tree ensembles, and permutation SHAP is model-agnostic but approximate.",
        ),
        (
            "Global vs local explanation?",
            "Global importance averages |SHAP| across customers; local explanation shows the signed drivers for one customer.",
        ),
        (
            "Why can monthly charges have a negative SHAP value?",
            "SHAP is conditional. For a new fiber customer with streaming add-ons, the rest of the profile already explains the risk; the incremental price contribution can be protective. This is not a marginal causal effect.",
        ),
        (
            "How are risk bands defined?",
            "Low < 0.32, medium 0.32–0.60, high ≥ 0.60. The low/medium cut-off is the deployed threshold, so bands and predictions cannot contradict.",
        ),
        (
            "How are recommendations generated?",
            "A 14-rule engine combines the risk band, service/contract attributes and SHAP driver alignment, then ranks actions with a priority score.",
        ),
        (
            "How does the system persist data?",
            "SQLite stores the prediction audit trail, outcome feedback and saved retention actions in data/processed/churn.db. No server or sign-in is needed for the local demo.",
        ),
    ]
    for index, (question, answer) in enumerate(qa, start=1):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(f"Q{index}. {question}")
        run.bold = True
        run.font.color.rgb = DARK
        run.font.size = Pt(10)
        answer_paragraph = doc.add_paragraph()
        answer_paragraph.paragraph_format.space_after = Pt(5)
        answer_paragraph.paragraph_format.left_indent = Cm(0.45)
        run = answer_paragraph.add_run(answer)
        run.font.size = Pt(9.4)
        run.font.color.rgb = RGBColor(0x2B, 0x3D, 0x35)

    add_heading(doc, "15.1 Five-minute demo script", 2)
    add_table(
        doc,
        ["Time", "What to show", "What to say"],
        [
            (
                "0:00–0:40",
                "Overview",
                "This is the retention command center: 7,043 customers, 26.5% historical churn and 1,002 high-risk customers.",
            ),
            (
                "0:40–1:30",
                "Customers → drawer",
                "Open a high-risk customer; point to the probability, tenure driver, revenue at risk and the playbook.",
            ),
            (
                "1:30–2:10",
                "Save action → queue",
                "Save a recommendation; show it persisted in SQLite and update the workflow status.",
            ),
            (
                "2:10–3:00",
                "Score customer",
                "Score the high-risk demo; explain the gauge, SHAP signs and the candidate offers.",
            ),
            (
                "3:00–4:00",
                "Model insights",
                "Show the six-model table, ROC curve, model selection and SHAP drivers.",
            ),
            (
                "4:00–4:40",
                "History/feedback",
                "Every score is audited; record an outcome to close the loop.",
            ),
            (
                "4:40–5:00",
                "Close",
                "Summarise the business value, limitations and future work; invite questions.",
            ),
        ],
        widths=[1.1, 1.7, 4.0],
        font_size=8.1,
    )


def section_contributions(doc):
    add_heading(doc, "16. Team contributions", 1)
    add_body(
        doc,
        "The project was delivered by a three-person team. Pushkar led the machine-learning and backend "
        "work; Karan owned research and the frontend; Shaurya supported data validation, testing and "
        "documentation. The percentages reflect relative effort agreed by the team.",
    )
    add_table(
        doc,
        ["Member", "Primary role", "Key contributions", "Share"],
        [
            (
                "Pushkar",
                "Project lead · ML & backend",
                "Problem framing; data cleaning and feature engineering; six-model CV comparison; threshold tuning; SHAP pipeline; FastAPI endpoints; SQLite integration; test suite; end-to-end integration; documentation lead.",
                "45%",
            ),
            (
                "Karan",
                "Research · frontend & visual design",
                "Literature and model-family research; SHAP and retention-strategy research; dashboard UX and visual design; frontend implementation; screenshot and presentation visuals.",
                "35%",
            ),
            (
                "Shaurya",
                "Data validation · testing & documentation support",
                "EDA sanity checks; TotalCharges and segment validation; test-case review; documentation formatting; viva rehearsal support.",
                "20%",
            ),
        ],
        widths=[1.0, 1.4, 3.6, 0.7],
        font_size=8.0,
    )
    add_callout(
        doc,
        "Contribution policy",
        "Pushkar carries the largest share because he owns the critical ML and backend path. Shaurya "
        "has the smallest share, focused on support tasks. Karan combines research and frontend work "
        "as requested.",
    )


CLAUDE_PROMPT = """You are a senior presentation designer and data storyteller. Create a complete, presentation-ready, 16:9 PowerPoint deck for a 3rd-semester machine-learning project called "Telco Churn Intelligence" (product name: RetainIQ). The deck must be suitable for a 10-minute viva presentation and a 5-minute demo.

NON-NEGOTIABLE CONSTRAINTS
- Use only free, open, no-paywall tools and assets. Do not use paid templates, paywalled stock-photo sites, login-gated plugins, watermarked assets or premium AI slide generators.
- Authentication is out of scope. Do not add login, signup, paywall or subscription screens. The demo is a local, no-auth dashboard.
- Generate the deck with python-pptx (free and open source). Return ONE complete runnable Python script in a single code block, plus the exact install command.
- Do NOT invent metrics, names or features. Use only the project facts below. If a fact is missing, write [VERIFY] instead of guessing.
- Use native editable charts and shapes where possible; do not embed random internet images. If local screenshots are available, reference these paths: docs/screenshots/overview.png, docs/screenshots/customer_drawer.png, docs/screenshots/insights.png.
- Keep text large and sparse: title 30-36pt, body 16-20pt, footnotes 10-12pt, maximum 5 bullets per slide.

PROJECT FACTS (exact)
- Dataset: IBM Telco Customer Churn, 7,043 customers, 21 raw columns, 26.5% churn; stratified 80/20 split (5,634 train / 1,409 test).
- Task: supervised binary classification (churn vs stay).
- Models compared: Logistic Regression, Decision Tree, Random Forest, XGBoost, KNN, SVM.
- 5-fold CV ROC-AUC: LR 0.8475, XGBoost 0.8409, Random Forest 0.8359, Decision Tree 0.8265, KNN 0.8117, SVM 0.7984.
- Selected model: Logistic Regression (highest CV ROC-AUC; XGBoost close but more complex).
- Test metrics at threshold 0.32: ROC-AUC 0.8456, PR-AUC 0.6519, recall 0.7406, precision 0.5410, F1 0.6253, Brier 0.1362.
- Confusion matrix: TN 800, FP 235, FN 97, TP 277.
- Risk bands: low < 0.32 (4,552 customers), medium 0.32-0.60 (1,489), high >= 0.60 (1,002).
- Engineered features: NumServices, SupportServices, StreamingServices, IsNewCustomer, HasFamily. Ratio features were removed due to collinearity and unstable SHAP.
- Explainability: LinearSHAP for the selected model, TreeSHAP for tree models, permutation SHAP fallback, coefficients and native feature importance.
- Top global drivers: internet service, contract, tenure, monthly charges, streaming services, payment method, new-customer status, online security.
- Recommendation engine: 14 rules, e.g. annual contract conversion, fiber plan review, autopay migration, tech-support trial, onboarding, loyalty review, senior support, bill clarity, streaming bundle, device protection, targeted save offer, low-risk nurture.
- Risk formulas: annual revenue at risk = monthly charges x 12 x P(churn); expected remaining months = min(1/P(churn), 72); estimated CLV = monthly charges x expected remaining months.
- System: FastAPI + Pydantic backend; scikit-learn/XGBoost/SHAP model bundle; SQLite for prediction history, feedback and saved actions; React + Vite dashboard served at /app/.
- Dashboard pages: Overview, Customers, Score customer, Model insights, Retention queue, Score history.
- Key API endpoints: /dashboard/summary, /model/info, /model/metrics, /model/features, /predict, /predict/batch, /customers/high-risk, /customers/{id}, /eda/summary, /actions, /history, /feedback.
- Testing: 166 automated tests, ruff clean, Playwright UI smoke test with zero console errors.
- Team: Pushkar (project lead, ML & backend, 45%), Karan (research, frontend & visual design, 35%), Shaurya (data validation, testing & documentation support, 20%).
- Demo URL: http://127.0.0.1:8000/app/
- Dataset source: IBM Telco Customer Churn, Kaggle (blastchar/telco-customer-churn).
- The system is a decision-support prototype. SHAP is not causality; recommendations are heuristics, not uplift estimates.

DECK STRUCTURE (16 slides)
1. Title: Telco Churn Intelligence / RetainIQ. Subtitle: explainable churn prediction and retention. Team names.
2. The business problem: churn reduces recurring revenue and raises acquisition cost; basic predictions do not explain or act.
3. Project objectives: predict, explain, prioritise and recommend.
4. Dataset at a glance: 7,043 customers, 21 columns, 26.5% churn, key attributes.
5. EDA story: contract, internet, payment and tenure insights (use 2-3 headline numbers).
6. Cleaning and feature engineering: TotalCharges semantic zeros, engineered features, withheld customerID.
7. Leak-free pipeline: train/test split, imputation, scaling, one-hot, pipeline inside CV.
8. Six models compared: why each family, 5-fold CV protocol, selection on ROC-AUC.
9. Results: CV table and held-out metrics; Logistic Regression selected; XGBoost close.
10. Threshold and confusion matrix: why 0.32; recall vs precision trade-off.
11. Explainability: SHAP global and local; show "tenure increases risk" and "month-to-month increases risk".
12. Risk scoring and business value: three bands, revenue at risk, CLV.
13. Personalised retention: 14-rule playbook; show three concrete examples.
14. System architecture and demo: FastAPI, model bundle, SQLite, dashboard pages; include a screenshot placeholder.
15. Testing, limitations and responsible use.
16. Conclusion, team contributions, Q&A.

DESIGN SYSTEM
- 16:9 widescreen.
- Background: near-black #07100D with subtle dark-green radial/dot texture.
- Primary accent: mint green #2FF0A3; secondary: amber #F4B860 and coral #FF6379 for risk.
- Text: warm white #EAF8F2; muted #7D978D.
- Font: Inter or Calibri fallback; bold headings, generous whitespace.
- Use thin 1px borders and rounded rectangles; no gradients on text except the title accent.
- Charts: mint bars/curves on dark grid; label axes and values; avoid 3D charts.
- Each slide: a small section label, a large takeaway headline (not just a topic label), one visual, 3-5 short bullets, and a source footnote.
- Use simple shapes/Unicode symbols as icons; do not download paid icons.

SPEAKER NOTES
For every slide include 60-110 words of speaker notes written in a confident student-presenter voice. Include one likely examiner question and a one-line answer in the notes for slides 8-14.

DELIVERABLE
1. The complete python-pptx script (one code block), with a `main()` and `if __name__ == "__main__":`.
2. The install command: `pip install python-pptx`.
3. A short README block explaining how to run it and where the .pptx is saved.
4. A one-page handout outline with the 10 most important facts.
5. Do not use Markdown tables inside slides; build tables with python-pptx shapes.
Return only the final script and the short instructions."""

PROMPT_OUTPUT.write_text(CLAUDE_PROMPT, encoding="utf-8")


def section_prompt(doc):
    add_heading(doc, "17. Master prompt for a free Claude presentation", 1)
    add_body(
        doc,
        "The following prompt is designed to be pasted into Claude. It asks for a complete, editable "
        "PowerPoint generated with python-pptx, using only free tools and assets. It deliberately "
        "excludes authentication, paid templates and paywalled stock imagery. The same text is saved "
        "separately as docs/claude_ppt_master_prompt.txt for easy copy-paste.",
    )
    add_heading(doc, "17.1 Copy-paste prompt", 2)
    add_code_block(doc, CLAUDE_PROMPT)
    add_callout(
        doc,
        "How to use it",
        "Paste the prompt into Claude. Ask Claude to run or return the python-pptx script. Save the "
        "script as make_deck.py, run `pip install python-pptx`, then `python make_deck.py`. The result "
        "is a fully editable .pptx. No login, subscription or paid asset is required. If Claude cannot "
        "run code, it will still return the script and speaker notes for you to run locally.",
    )
    add_heading(doc, "17.2 Presentation tips", 2)
    add_bullets(
        doc,
        [
            "Rehearse the 10-minute flow, not the whole document. The demo script in section 15.1 is the spine.",
            "Lead with the business problem and the result, then explain the method; examiners remember the story.",
            "Show one customer end to end: score → driver → playbook → saved action.",
            "Be explicit about limitations: SHAP is not causality and the recommendations are heuristics.",
            "Keep the live demo on a local server; have screenshots ready as a fallback.",
        ],
    )


def section_glossary(doc):
    add_heading(doc, "18. Glossary", 1)
    terms = [
        ("Churn", "Loss of an existing customer through cancellation or non-renewal."),
        ("Churn rate", "Share of customers who churn in a period; here 26.5%."),
        ("Binary classification", "Predicting one of two classes, e.g. churn vs stay."),
        ("Feature", "An input variable used by the model."),
        ("Target", "The label the model learns to predict; Churn 1/0."),
        ("Train/test split", "Partition of data into fitting and final evaluation sets."),
        ("Stratified split", "Split that preserves the class ratio in both parts."),
        ("Cross-validation", "Repeated train/validation splits to estimate generalisation."),
        ("Stratified K-fold", "K-fold CV that preserves class balance in each fold."),
        ("Data leakage", "Using information unavailable at prediction time, inflating scores."),
        (
            "Imputation",
            "Filling missing values; median for numeric, most-frequent for categorical.",
        ),
        ("Standardisation", "Scaling features to zero mean and unit variance."),
        ("One-hot encoding", "Representing a categorical variable as binary indicator columns."),
        ("Class imbalance", "Unequal class frequencies; churn is the minority class."),
        ("Overfitting", "Learning noise in the training data and failing to generalise."),
        ("Hyperparameter", "A model setting chosen before fitting, e.g. tree depth."),
        ("ROC curve", "True-positive rate vs false-positive rate across thresholds."),
        ("ROC-AUC", "Area under the ROC curve; probability of ranking a churner above a stayer."),
        ("PR curve", "Precision vs recall across thresholds."),
        ("PR-AUC", "Area under the precision–recall curve."),
        ("Precision", "Of predicted churners, the share that truly churn."),
        ("Recall", "Of actual churners, the share the model catches."),
        ("F1 score", "Harmonic mean of precision and recall."),
        ("Brier score", "Mean squared error of probability predictions."),
        ("Calibration", "Agreement between predicted probabilities and observed frequencies."),
        ("Decision threshold", "Probability cut-off used to convert a score into a class."),
        ("SHAP", "Shapley-value attribution of a prediction to its features."),
        ("Coefficient", "Log-odds weight of a feature in a linear model."),
        ("Feature importance", "Native tree measure of how useful a feature is for splits."),
        ("Risk band", "Business grouping of probabilities: low, medium, high."),
        ("CLV", "Customer lifetime value; expected revenue from a customer over time."),
        ("Uplift", "Causal effect of an intervention on retention, not just churn risk."),
        ("SQLite", "Embedded, serverless SQL database included with Python."),
        ("FastAPI", "Python web framework used for the prediction API."),
        ("WAL", "Write-ahead logging; a SQLite journal mode that improves concurrency."),
        ("Audit trail", "Chronological record of predictions and decisions for review."),
    ]
    add_table(
        doc,
        ["Term", "Definition"],
        terms,
        widths=[1.65, 5.05],
        font_size=8.0,
    )


def section_references(doc):
    add_heading(doc, "19. References", 1)
    references = [
        "IBM. Telco Customer Churn dataset. Kaggle: blastchar/telco-customer-churn.",
        "Pedregosa et al. Scikit-learn: Machine Learning in Python. JMLR, 2011.",
        "Chen & Guestrin. XGBoost: A Scalable Tree Boosting System. KDD, 2016.",
        "Lundberg & Lee. A Unified Approach to Interpreting Model Predictions. NeurIPS, 2017.",
        "Breiman. Random Forests. Machine Learning, 2001.",
        "Hastie, Tibshirani & Friedman. The Elements of Statistical Learning. Springer.",
        "Géron. Hands-On Machine Learning with Scikit-Learn, Keras & TensorFlow. O'Reilly.",
        "FastAPI documentation: https://fastapi.tiangolo.com/",
        "SQLite documentation: https://www.sqlite.org/docs.html",
        "SHAP documentation: https://shap.readthedocs.io/",
    ]
    for index, reference in enumerate(references, start=1):
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        run = paragraph.add_run(f"[{index}] ")
        run.bold = True
        run.font.color.rgb = GREEN
        paragraph.add_run(reference)
    add_body(
        doc,
        "All metrics in this document were generated by the reproducible training pipeline in this "
        "repository. The dataset is publicly available; the code is released under the MIT licence.",
        italic=True,
        size=9,
        color=MUTED,
    )


def build():
    doc = Document()
    style_document(doc)
    cover(doc)
    page_break(doc)
    contents(doc)
    page_break(doc)
    section_summary(doc)
    page_break(doc)
    section_problem(doc)
    page_break(doc)
    section_dataset(doc)
    page_break(doc)
    section_eda(doc)
    page_break(doc)
    section_preprocessing(doc)
    page_break(doc)
    section_models(doc)
    page_break(doc)
    section_results(doc)
    page_break(doc)
    section_explainability(doc)
    page_break(doc)
    section_risk(doc)
    page_break(doc)
    section_recommendations(doc)
    page_break(doc)
    section_architecture(doc)
    page_break(doc)
    section_frontend(doc)
    page_break(doc)
    section_testing(doc)
    page_break(doc)
    section_limits(doc)
    page_break(doc)
    section_viva(doc)
    page_break(doc)
    section_contributions(doc)
    page_break(doc)
    section_prompt(doc)
    page_break(doc)
    section_glossary(doc)
    page_break(doc)
    section_references(doc)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(f"Saved {OUTPUT}")
    print(f"Saved {PROMPT_OUTPUT}")


if __name__ == "__main__":
    build()
