import os
import re
import unicodedata
from datetime import datetime, timedelta
from tkinter import Tk, filedialog
from pypdf import PdfReader, PdfWriter
import pdfplumber
import shutil


# --- Name and date parsing helpers ---

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def load_hungarian_first_names_local(path="hungarian_names.txt"):
    names = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    names.add(name)
    except FileNotFoundError:
        raise Exception(f"Hungarian names file not found at: {path}")
    return names


def is_first_name(name, names_db):
    # Lowercase + no accents for robust matching
    return remove_accents(name).strip().lower() in {n.lower() for n in names_db}


def parse_name(raw_name, names_db):
    raw_name_no_accents = remove_accents(raw_name.strip())
    if "Company" in raw_name_no_accents:
        raw_name_no_accents = raw_name_no_accents.split("Company")[0].strip()

    parts = raw_name_no_accents.split()
    if len(parts) >= 2:
        if is_first_name(parts, names_db):
            # Swap first two parts
            reordered = [parts, parts] + parts[2:]
            return " ".join(reordered).upper()
    return raw_name_no_accents.upper()


def get_short_name_code(full_name):
    last_name = full_name.split()
    length = len(last_name)
    if length >= 4:
        return last_name[:4].upper()
    elif length == 3:
        return last_name[:3].upper()
    else:
        return last_name.upper()


def parse_dates(text_snippet):
    date_pattern = r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})|(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})'
    matches = re.findall(date_pattern, text_snippet)
    dates = []
    for m in matches:
        if m[0]:  # yyyy.mm.dd
            try:
                dates.append(datetime(int(m), int(m), int(m)))
            except Exception:
                continue
        else:  # dd.mm.yyyy or dd.mm.yy
            d1, d2, y = m, m, m
            if len(y) == 2:
                y = '20' + y
            try:
                dates.append(datetime(int(y), int(d1), int(d2)))
            except ValueError:
                try:
                    dates.append(datetime(int(y), int(d2), int(d1)))
                except ValueError:
                    continue
    dates.sort()
    return dates


def generate_filename(full_text, names_db):
    # Remove any "Period X Starts" lines
    full_text = re.sub(r"^Period\s+\d+\s+Starts.*(?:\n.*)*?", "", full_text,
                       flags=re.IGNORECASE | re.MULTILINE)

    # --- Find and parse the name ---
    name_match = re.search(r"Name:\s*(.+)", full_text, re.IGNORECASE)
    if not name_match:
        raise Exception("Name not found in PDF")
    raw_name = name_match.group(1).strip()
    full_name = parse_name(raw_name, names_db)

    # --- Get date info ---
    date_pos = full_text.lower().find('date')
    if date_pos == -1:
        raise Exception("Date header not found")
    date_text_snippet = full_text[date_pos:]
    dates = parse_dates(date_text_snippet)
    if not dates:
        raise Exception("No valid dates found")

    first_date_str = dates[0].strftime('%m%d')
    last_date_str = dates[-1].strftime('%m%d')
    day_before_last_str = (dates[-1] - timedelta(days=1)).strftime('%m%d')
    short_code = get_short_name_code(full_name)

    return f"{full_name} EKHO - {short_code}_{first_date_str}-{last_date_str} - WE25{day_before_last_str}.pdf"


# --- PDF processing ---

def unlock_pdf_remove_links(input_path):
    reader = PdfReader(input_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if hasattr(writer, "remove_links"):
        writer.remove_links()
    with open(input_path, "wb") as f_out:
        writer.write(f_out)


def process_and_rename_pdfs(folder_path, names_db):
    renamed_folder = os.path.join(folder_path, "RENAMED")
    os.makedirs(renamed_folder, exist_ok=True)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".pdf") and filename != "RENAMED":
            file_path = os.path.join(folder_path, filename)

            try:
                unlock_pdf_remove_links(file_path)
            except Exception as e:
                print(f"Failed to process (unlock) {filename}: {e}")
                continue

            try:
                with pdfplumber.open(file_path) as pdf:
                    full_text = ""
                    total_pages = len(pdf.pages)
                    half_pages = max(total_pages // 2, 1)
                    for page in pdf.pages[:half_pages]:
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n"

                new_name = generate_filename(full_text, names_db)
                new_path = os.path.join(renamed_folder, new_name)

                # Ensure unique name if file already exists
                if os.path.exists(new_path):
                    base, ext = os.path.splitext(new_name)
                    counter = 1
                    while os.path.exists(new_path):
                        new_path = os.path.join(renamed_folder, f"{base} ({counter}){ext}")
                        counter += 1

                shutil.copy(file_path, new_path)  # Copy instead of rename

                print(f"Unlocked & Renamed: {filename} -> {os.path.basename(new_path)}")

            except Exception as e:
                print(f"Failed to extract text or rename {filename}: {e}")


# --- Main app entry point ---

if __name__ == "__main__":
    print("Loading Hungarian first name list from 'hungarian_names.txt' ...")
    hungarian_first_names = load_hungarian_first_names_local()

    root = Tk()
    root.withdraw()
    folder_selected = filedialog.askdirectory(title="Select Input Folder Containing PDFs")
    root.destroy()

    if folder_selected:
        process_and_rename_pdfs(folder_selected, hungarian_first_names)
        print("\n✅ Done! Check the 'RENAMED' folder inside:")
        print(folder_selected)
        input("\nPress Enter to exit...")
    else:
        print("No folder selected.")
        input("\nPress Enter to exit...")
