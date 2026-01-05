#!/usr/bin/env python
# coding: utf-8

# In[9]:


from docx import Document
import pandas as pd
import re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from zipfile import ZipFile
import tempfile
import subprocess

DOCX_PATH = "/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs/rdrive/RI_pilot_extraction_2025AUG19_HI (n=10)_fixed_space.docx"
CSV_PATH = "/Volumes/home/anonymous/research-integrity-ktp/analyses/2025-12-23_pilot_sampler/pilot_sample_2025-07-24.csv"
LEFT_LAST_NAME_COL = "hcr.last_name"
LEFT_FIRST_NAME_COL = "hcr.first_name"
DRAW_LABEL = 'ktp.draw_number'

RIGHT_NAME_COL = "Researcher/author"
TOTAL_DRAWS = 310  # e.g., as of 2025-12-23 (including pilot)

INTRODUCTION = """## Introduction
**Draw number** is the sequential order in which rows were sampled from HCR tables.

Name is displayed as **Last Name, First Name**.

Last modified (introduction): December 23, 2025

Date of report: {}
"""

doc = Document(DOCX_PATH)

dfs = []
for t in doc.tables:
    rows = []
    for row in t.rows:
        rows.append([cell.text.strip() for cell in row.cells])

    df = pd.DataFrame(rows)

    # optional: first row as header
    df.columns = df.iloc[0]
    df = df.iloc[1:].reset_index(drop=True)

    dfs.append(df)

# load csv
csv_df = pd.read_csv(CSV_PATH)

# docx table (already extracted)
docx_df = dfs[0]

# csv join key
csv_df["join_name"] = csv_df[LEFT_FIRST_NAME_COL] + " " + csv_df[LEFT_LAST_NAME_COL]

# docx join key
docx_df["join_name"] = docx_df[RIGHT_NAME_COL]

# ---- left join ----
joined_df = csv_df.merge(
    docx_df,
    on="join_name",
    how="left"
)

# optional cleanup
joined_df = joined_df.drop(columns=["join_name"])
joined_df.rename(  # normalize header row for docx table
    columns=lambda col: (
        'ktp.table_1_' + re.sub(r'\s', '_', re.sub(r'[^\w\s]', '_', str(col).lower()))
        if not re.match(r'^[\w_]+\.', str(col)) else col
    ),
    inplace=True,
)

# Create markdown cards for each row
cards = {}
intro = INTRODUCTION.format(
    today := (
        datetime.now(ZoneInfo('America/Toronto'))
        .strftime('%B %d, %Y')
    )
) + "\n\n"  # will merge later so as not to spoil cards
for _, row in joined_df.iterrows():
    card = f"### Draw #{row.pop(DRAW_LABEL)} of {TOTAL_DRAWS}: {row.get(LEFT_LAST_NAME_COL)}, {row.get(LEFT_FIRST_NAME_COL)}\n"
    docx_filename = re.sub(r'\s+', '_', re.sub(r'[^A-Za-z0-9\s]+', '', card)).strip('_')
    for col, val in row.items():
        if '\n' in str(val):
            # treat as code block
            card += f"**{col}**:\n\n{str(val).replace('\n','\n\n')}\n\n"
        else:
            card += f"**{col}**: {str(val)}\n\n"
    cards[docx_filename] = card

# Join all cards into a single markdown string
md_content = intro + "\n---\n".join(cards.values())

# Display in notebook (if using Jupyter)
from IPython.display import Markdown, display
display(Markdown(md_content))

# Save to a markdown file
with open(Path("2025-12-23_word_tables") / (Path(CSV_PATH).stem + "_table_1.md"), "w", encoding="utf-8") as f:
    f.write(md_content)

# Save to standalone Word docx's and zip them
zip_path = Path("2025-12-23_word_tables") / (Path(CSV_PATH).stem + "_cards.zip")
with tempfile.TemporaryDirectory() as tmpdir:
    docx_paths: list[Path] = []
    for filename, card in cards.items():
        md_path = Path(tmpdir) / f"{filename}.md"
        docx_path = Path(tmpdir) / f"{filename}.docx"
        md_path.write_text(intro + card, encoding="utf-8")
        subprocess.run([
            "pandoc",
            str(md_path),
            "-o",
            str(docx_path)
        ], check=True)
        docx_paths.append(docx_path)
        with ZipFile(zip_path, "w") as zipf:
            for path in docx_paths:
                zipf.write(path, arcname=path.name)

