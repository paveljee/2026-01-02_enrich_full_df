import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import click
import pandas as pd
from rich.console import Console
from rich.progress import track
from rich.prompt import Confirm, Prompt

from ._vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
)
from .data_models import NameKey, OuterDict
from .matchers import CsvMatcher, DocxMatcher
from .name_utils import unify_first_last
from .parse_docx import parse_docx_table

console = Console()

PACKAGE_ROOT = Path(__file__).parent
PANDOC_REFERENCE_DOCX_PATH = PACKAGE_ROOT / "resources" / "pandoc-custom-reference.docx"

TOTAL_DRAWS = 310  # e.g., as of 2025-12-23 (including pilot)

INTRODUCTION = """## Introduction
**Draw number** is the sequential order in which rows were sampled from HCR tables.

Name is displayed as **Last Name, First Name**.

Last modified (introduction): December 23, 2025

Date of report: {}
"""

def build_outer_dict_from_names(names: pd.DataFrame) -> OuterDict:
    """Build an OuterDict from a dataframe of unique first/last pairs."""
    name_keys = [
        NameKey(first_name=first, last_name=last)
        for first, last in names.itertuples(index=False, name=None)
    ]
    return OuterDict.from_name_keys(name_keys)


def find_files_by_extension(directory: Path, extension: str, recursive: bool = False) -> list[Path]:
    """Find all files with given extension in directory."""
    pattern = f"*.{extension}"
    if recursive:
        return list(directory.rglob(pattern))
    else:
        return list(directory.glob(pattern))


def validate_csv_headers(csv_files: list[Path]) -> bool:
    """Validate that all CSV files have the same column names."""
    if not csv_files:
        return False
    
    first_df = pd.read_csv(csv_files[0], nrows=0)
    expected_cols = set(first_df.columns)
    
    for csv_path in csv_files[1:]:
        df = pd.read_csv(csv_path, nrows=0)
        if set(df.columns) != expected_cols:
            console.print(f"[red]Column mismatch in {csv_path.name}[/red]")
            console.print(f"Expected: {sorted(expected_cols)}")
            console.print(f"Got: {sorted(df.columns)}")
            return False
    
    return True


def process_documents(docx_dir: Path, csv_dir: Path, recursive: bool, 
                     output_dir: Path, output_format: str):
    """Main processing logic."""
    # Find all DOCX files
    docx_files = find_files_by_extension(docx_dir, "docx", recursive)
    if not docx_files:
        console.print("[red]No DOCX files found in specified directory.[/red]")
        return
    
    console.print(f"[green]Found {len(docx_files)} DOCX file(s)[/green]")
    
    # Find and validate CSV files
    csv_files = find_files_by_extension(csv_dir, "csv", recursive)
    if not csv_files:
        console.print("[red]No CSV files found in specified directory.[/red]")
        return
    
    console.print(f"[green]Found {len(csv_files)} CSV file(s)[/green]")
    
    if not validate_csv_headers(csv_files):
        console.print("[red]CSV files have different headers. Aborting.[/red]")
        return
    
    # Parse DOCX files
    all_dfs = []
    parse_func = parse_docx_table
    
    for docx_path in track(docx_files, description="Parsing DOCX files..."):
        dfs = parse_func(docx_path)
        for df in dfs:
            df[KTP_FILENAME_COL] = docx_path.name
        all_dfs.extend(dfs)
    
    # load and combine all CSV files
    csv_df = pd.concat(
        [
            pd.read_csv(csv_path).assign(**{KTP_FILENAME_COL: csv_path.name})
            for csv_path in csv_files
        ],
        ignore_index=True,
    )

    # docx tables
    docx_df = pd.concat(all_dfs, ignore_index=True)

    # csv join key
    unified_names = csv_df.apply(unify_first_last, axis=1, result_type='expand')
    csv_df[KTP_FIRST_NAME_COL] = unified_names[0].apply(lambda x: x[KTP_FIRST_NAME_COL])
    csv_df[KTP_LAST_NAME_COL] = unified_names[1].apply(lambda x: x[KTP_LAST_NAME_COL])

    docx_df.rename(  # normalize header row for docx table
        columns=lambda col: (
            re.sub(
                pattern=r'_+',  # otherwise consecutive underscores break markdown
                repl='_',
                string=(
                    col if re.match(
                        pattern=r'^[\w_]+\.',  # e.g., starts with `ktp.`, `hcr.` etc.
                        string=str(col),
                    )
                    else 'ktp.table_1_' + re.sub(
                        pattern=r'\s',
                        repl='_',
                        string=re.sub(r'[^\w\s]', '_', str(col).lower()),
                    )
                )
            )
        ),
        inplace=True,
    )

    unique_names = (
        csv_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    outer_dict = build_outer_dict_from_names(unique_names)

    csv_matcher = CsvMatcher(outer_dict)
    docx_matcher = DocxMatcher(outer_dict)

    csv_matcher.match(csv_df)
    docx_matcher.match(docx_df)

    # Create markdown cards for each row
    cards = {}
    today = datetime.now(ZoneInfo("America/Toronto")).strftime("%B %d, %Y")
    intro = INTRODUCTION.format(today) + "\n\n"  # will merge later so as not to spoil cards
    for name_key, inner_dicts in outer_dict.items():
        draw_numbers = []
        for inner in inner_dicts:
            draw_number = inner.data.get(DRAW_LABEL)
            if draw_number is not None and not pd.isna(draw_number):
                draw_numbers.append(str(draw_number))
        draw_numbers = sorted(set(draw_numbers))
        if draw_numbers:
            draw_label = ", ".join(draw_numbers)
            header = (
                f"### Draw #{draw_label} of {TOTAL_DRAWS}: "
                f"{name_key.last_name}, {name_key.first_name}\n"
            )
        else:
            draw_label = ""
            header = f"### {name_key.last_name}, {name_key.first_name}\n"

        fun_fact = ""
        for inner in inner_dicts:
            last_col = inner.data.get(KTP_LAST_NAME_ORIG_COLNAME_COL)
            first_col = inner.data.get(KTP_FIRST_NAME_ORIG_COLNAME_COL)
            if last_col and first_col:
                fun_fact = (
                    f"Fun fact: the last name came from `{last_col}` and the first name – "
                    f"from `{first_col}` in the originating HCR list."
                )
                break
        card = header + (fun_fact + "\n" if fun_fact else "")

        minified_card = (
            f"{draw_label}: {name_key.first_name} {name_key.last_name}"
            if draw_label
            else f"{name_key.first_name} {name_key.last_name}"
        )
        docx_filename = re.sub(
            r"\s+",
            "_",
            re.sub(r"[^A-Za-z0-9\s]+", "", minified_card),
        ).strip("_")

        for inner in inner_dicts:
            filename = inner.data.get(KTP_FILENAME_COL, "unknown")
            card += f"\n\n#### {KTP_FILENAME_COL}: {filename}\n"
            for col, val in inner.data.items():
                if col == KTP_FILENAME_COL or pd.isna(val):
                    continue
                if '\n' in str(val):
                    # treat as code block
                    card += f"**{col}**:\n\n{str(val).replace('\n','\n\n')}\n\n"
                else:
                    card += f"**{col}**: {str(val)}\n\n"
        cards[docx_filename] = card

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as standalone files and zip them
    zip_path = output_dir / f"{csv_dir.name}_combined_cards.zip"
    
    # Save based on output format
    if output_format == "txt":
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_paths = []
            for filename, card in track(
                list(cards.items()),
                description="Creating Markdown (*.txt) files...",
            ):
                txt_path = Path(tmpdir) / f"{filename}.txt"
                txt_path.write_text(intro + card, encoding="utf-8")
                txt_paths.append(txt_path)
            # Zip them all
            with ZipFile(zip_path, "w") as zipf:
                for path in txt_paths:
                    zipf.write(path, arcname=path.name)
        console.print(f"[green]Saved Markdown (*.txt) files to: {zip_path}[/green]")
        
    elif output_format == "docx":
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_ref_path = Path(tmpdir) / Path(PANDOC_REFERENCE_DOCX_PATH).name
            shutil.copy(PANDOC_REFERENCE_DOCX_PATH, tmp_ref_path)
            docx_paths: list[Path] = []
            for filename, card in track(list(cards.items()), description="Creating DOCX files..."):
                md_path = Path(tmpdir) / f"{filename}.md"
                docx_path = Path(tmpdir) / f"{filename}.docx"
                md_path.write_text(intro + card, encoding="utf-8")
                subprocess.run([
                    "pandoc",
                    str(md_path),
                    "-o",
                    str(docx_path),
                    "--reference-doc",
                    str(tmp_ref_path),
                ], check=True)
                docx_paths.append(docx_path)
            with ZipFile(zip_path, "w") as zipf:
                for path in docx_paths:
                    zipf.write(path, arcname=path.name)
        console.print(f"[green]Saved DOCX files to: {zip_path}[/green]")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Document enrichment CLI tool."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactive)


@cli.command()
def interactive():
    """Run in interactive mode with rich prompts."""
    console.print("[bold blue]Document Enrichment Tool - Interactive Mode[/bold blue]\n")
    
    # Get inputs
    docx_dir = Path(Prompt.ask("Path to directory containing DOCX files"))
    while not docx_dir.exists() or not docx_dir.is_dir():
        console.print("[red]Invalid directory path.[/red]")
        docx_dir = Path(Prompt.ask("Path to directory containing DOCX files"))
    
    recursive = Confirm.ask("Search recursively for DOCX files?", default=False)
    
    csv_dir = Path(Prompt.ask("Path to directory containing CSV files"))
    while not csv_dir.exists() or not csv_dir.is_dir():
        console.print("[red]Invalid directory path.[/red]")
        csv_dir = Path(Prompt.ask("Path to directory containing CSV files"))
    
    output_dir = Path(Prompt.ask("Output directory", default="./output"))
    
    output_format = Prompt.ask(
        "Output format",
        choices=["txt", "docx"],
        default="txt"
    )
    
    # Process
    process_documents(docx_dir, csv_dir, recursive, output_dir, output_format)


@cli.command()
@click.argument('docx_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('csv_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('-r', '--recursive', is_flag=True, help='Search recursively for DOCX and CSV files')
@click.option('--output-dir', type=click.Path(path_type=Path), default='./output', 
              help='Output directory (default: ./output)')
@click.option('--output-format', type=click.Choice(['txt', 'docx']), default='txt',
              help='Output format: txt (markdown) or docx (default: txt)')
def process(docx_dir: Path, csv_dir: Path, recursive: bool, output_dir: Path, 
           output_format: str):
    """Process DOCX files and enrich with CSV data.
    
    DOCX_DIR: Directory containing DOCX files
    CSV_DIR: Directory containing CSV files (must have matching headers)
    """
    
    process_documents(docx_dir, csv_dir, recursive, output_dir, output_format)
