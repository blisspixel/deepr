import os
import argparse
from docx import Document
from normalize import normalize_markdown
import style
from docx2pdf import convert

def convert_report(txt_path, convert_pdf=False):
    txt_path = txt_path.strip('"').strip("'")  # Remove quotes if present

    if not os.path.exists(txt_path):
        print(f"❌ File not found: {txt_path}")
        return

    base_name = os.path.splitext(os.path.basename(txt_path))[0]
    report_dir = os.path.dirname(txt_path)
    docx_path = os.path.join(report_dir, f"{base_name}.docx")

    print(f"📄 Reading: {txt_path}")
    with open(txt_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    md_text = normalize_markdown(raw_text)

    doc = Document()
    title = "Reformatted Report"
    para = doc.add_paragraph(title, style="Heading 1")
    style.format_paragraph(para, spacing_after=12)
    style.apply_styles_to_doc(doc, md_text)
    doc.save(docx_path)

    print(f"✅ DOCX saved to: {docx_path}")

    if convert_pdf:
        try:
            convert(docx_path)
            print(f"✅ PDF saved to: {docx_path.replace('.docx', '.pdf')}")
        except Exception as e:
            print(f"⚠️ PDF conversion failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Convert raw .txt report to styled .docx")
    parser.add_argument("txt_path", nargs="?", help="Path to the .txt file (quoted or not)")
    parser.add_argument("--pdf", action="store_true", help="Also convert to PDF")
    args = parser.parse_args()

    if args.txt_path:
        convert_report(args.txt_path, convert_pdf=args.pdf)
    else:
        txt_path = input("Enter path to .txt file: ").strip()
        convert_report(txt_path, convert_pdf=args.pdf)

if __name__ == "__main__":
    main()
