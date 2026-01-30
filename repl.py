import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import psutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich import box
from rich.prompt import Confirm, Prompt

from pkg_20251223_word_tables.src._vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
    RIGHT_NAME_COL,
)
from pkg_20251223_word_tables.src.data_models import (
    FragmentType,
    InnerDict,
    MatchingProcedure,
    NameKey,
    OuterDict,
    RegisteredResource,
    ResourceGroup,
    SourceKey,
)
from pkg_20251223_word_tables.src.name_utils import unify_first_last
from pkg_20251223_word_tables.src.parse_docx import parse_docx_table

# ==============================================================================
# CONFIGURATION & REPRODUCIBILITY CONTRACT
# ==============================================================================
# The user (you) must calculate these once and hardcode them to ensure
# anyone else running this script uses the EXACT same inputs.
# ==============================================================================

FILES_CONFIG = {
    "hit_papers_0": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level0.parquet",
        "sha256": "453bf5e5fe4bd2427b467c35aaea36a9d5c1b8b61d1e01d84496fd7fd5e6d6aa", 
        "desc": "Hit Papers Level 0"
    },
    "hit_papers_1": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level1.parquet",
        "sha256": "f79ddf6e417e9d601ae04e6c898c72bc7b60118d3967cb03fe6fc708eab953ae",
        "desc": "Hit Papers Level 1"
    },
    "authors_paper": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors_paperid.parquet",
        "sha256": "c97f4552f22d8e05b1c2bb70746b5a16f29c41c2807738d3c49f3852573910f2",
        "desc": "Authors -> Paper IDs"
    },
    "author_details": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_author_details.parquet",
        "sha256": "62c373c747d74879585c3b1cfbbe70971c86927ec4fbc601482d3c2513ad9c1a",
        "desc": "Author Details (Names)"
    },
    "fields": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet",
        "sha256": "f78b1fc5287de26aee57665943a50c95aa980420449d7c099c351600cd584c7a",
        "desc": "Field Definitions"
    },
    "input_df": {
        "path": "/Volumes/home/anonymous/research-integrity-ktp/analyses/2025-12-23_pilot_sampler/pilot_sample_2025-07-24.csv",  # Assuming pickle or csv for the pandas df
        "sha256": "29d32fa214c3e6d2a77c52005035fba9f48392c22c0d58240ce064c353c221cd",
        "desc": "User Input DataFrame (60k rows)"
    }
}

# Benchmarks from the "Master Run" (Populate these after your first successful run)
REFERENCE_METRICS = {
    "peak_ram_gb": 8.47,  # e.g., 4.5
    "total_time_s": 27.3  # e.g., 340
}

DB_FILE = "data/scisci_process.duckdb"
STATE_FILE = "data/pipeline_state.json"
OUTPUT_FILE = "data/enriched_researchers.csv"

HCR_FIRST_NAME = "hcr.first_name"
HCR_LAST_NAME = "hcr.last_name"

console = Console()

# ==============================================================================
# KTP WORD-TABLE ENRICHMENT CONSTANTS
# ==============================================================================

PANDOC_REFERENCE_DOCX_PATH = (
    Path(__file__).parent / "pkg_20251223_word_tables" / "resources" / "pandoc-custom-reference.docx"
)

TOTAL_DRAWS = 310  # e.g., as of 2025-12-23 (including pilot)

INTRODUCTION = """## Introduction
**Draw number** is the sequential order in which rows were sampled from HCR tables.

Name is displayed as **Last Name, First Name**.

Last modified (introduction): December 23, 2025

Date of report: {}
"""

CSV_ROW_INDEX_COL = "ktp.csv_row_index"
DOCX_TABLE_INDEX_COL = "ktp.docx_table_index"
DOCX_ROW_INDEX_COL = "ktp.docx_row_index"
DOCX_FRAGMENT_COL = "ktp.docx_fragment"
SOURCE_KEY_COL = "ktp.source_key"

# ==============================================================================
# UTILITIES: MONITORING & HASHING
# ==============================================================================

class ResourceMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.running = False
        self.peak_memory = 0
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor)
        self.thread.start()

    def _monitor(self):
        while self.running:
            mem = self.process.memory_info().rss
            if mem > self.peak_memory:
                self.peak_memory = mem
            time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        return self.peak_memory / (1024 ** 3)  # GB

def calculate_sha256(filepath, progress, task_id):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read in chunks to avoid loading file into memory
        for byte_block in iter(lambda: f.read(4096 * 1024), b""):
            sha256_hash.update(byte_block)
            progress.update(task_id, advance=len(byte_block))
    return sha256_hash.hexdigest()


def compute_sha256(path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


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


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"ktp.table_1_{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


class CsvDuckdbMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


class DocxDuckdbMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def _register_resources(
    paths: list[Path],
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    description: str | None = None,
) -> dict[str, RegisteredResource]:
    resources: dict[str, RegisteredResource] = {}
    for path in paths:
        resource = RegisteredResource(
            name=path.name,
            hash=compute_sha256(path),
            group=group,
            fragment_type=fragment_type,
            description=description,
            url=path.resolve().as_uri(),
        )
        resources[path.name] = resource
    return resources


def _load_csv_files(csv_files: list[Path]) -> pd.DataFrame:
    frames = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        df = df.reset_index(drop=False).rename(columns={"index": CSV_ROW_INDEX_COL})
        df[KTP_FILENAME_COL] = csv_path.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _apply_unified_names(csv_df: pd.DataFrame) -> pd.DataFrame:
    unified_names = csv_df.apply(unify_first_last, axis=1, result_type="expand")
    first_data = pd.DataFrame(unified_names[0].tolist(), index=csv_df.index)
    last_data = pd.DataFrame(unified_names[1].tolist(), index=csv_df.index)
    for data in (first_data, last_data):
        for col in data.columns:
            csv_df[col] = data[col]
    return csv_df


def _load_docx_tables(docx_files: list[Path]) -> pd.DataFrame:
    all_frames = []
    for docx_path in docx_files:
        tables = parse_docx_table(docx_path)
        for table_index, df in enumerate(tables):
            df = df.copy()
            df.columns = [normalize_docx_column_name(col) for col in df.columns]
            df[KTP_FILENAME_COL] = docx_path.name
            df[DOCX_TABLE_INDEX_COL] = table_index
            df[DOCX_ROW_INDEX_COL] = range(len(df))
            df[DOCX_FRAGMENT_COL] = [
                f"table{table_index}_row{row_index}" for row_index in range(len(df))
            ]
            all_frames.append(df)
    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


def _resolve_docx_name_column(docx_df: pd.DataFrame) -> str:
    if RIGHT_NAME_COL in docx_df.columns:
        return RIGHT_NAME_COL
    normalized = normalize_docx_column_name(RIGHT_NAME_COL)
    if normalized in docx_df.columns:
        return normalized
    raise ValueError(
        f"Docx data does not contain expected name column '{RIGHT_NAME_COL}' "
        f"or normalized '{normalized}'."
    )


def _append_matches(
    outer_dict: OuterDict,
    matches: pd.DataFrame,
    procedure: MatchingProcedure,
    resources: dict[str, RegisteredResource],
    *,
    fragment_col: str,
) -> None:
    for record in matches.to_dict("records"):
        name_key = record.pop("name_key")
        record.pop("docx_clean", None)
        filename = record.get(KTP_FILENAME_COL)
        resource = resources.get(filename)
        if resource is None:
            raise ValueError(f"Missing registered resource for filename '{filename}'")
        fragment = record.get(fragment_col)
        source_key = SourceKey(resource=resource, fragment=str(fragment)).to_string_key()
        record[SOURCE_KEY_COL] = source_key
        inner = InnerDict.from_mapping(record, procedure)
        outer_dict.add_inner_by_key(name_key, inner)


def process_documents(
    docx_dir: Path,
    csv_dir: Path,
    recursive: bool,
    output_dir: Path,
    output_format: str,
) -> None:
    """DuckDB-backed processing logic for DOCX + CSV enrichment."""
    docx_files = find_files_by_extension(docx_dir, "docx", recursive)
    if not docx_files:
        console.print("[red]No DOCX files found in specified directory.[/red]")
        return

    console.print(f"[green]Found {len(docx_files)} DOCX file(s)[/green]")

    csv_files = find_files_by_extension(csv_dir, "csv", recursive)
    if not csv_files:
        console.print("[red]No CSV files found in specified directory.[/red]")
        return

    console.print(f"[green]Found {len(csv_files)} CSV file(s)[/green]")

    if not validate_csv_headers(csv_files):
        console.print("[red]CSV files have different headers. Aborting.[/red]")
        return

    csv_resources = _register_resources(
        csv_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.CSV_ROW,
        description="KTP CSV input dataset",
    )
    docx_resources = _register_resources(
        docx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
        description="KTP DOCX input dataset",
    )

    csv_df = _load_csv_files(csv_files)
    csv_df = _apply_unified_names(csv_df)
    docx_df = _load_docx_tables(docx_files)

    if csv_df.empty:
        console.print("[red]CSV data is empty after load.[/red]")
        return
    if docx_df.empty:
        console.print("[red]DOCX data is empty after parse.[/red]")
        return

    docx_name_column = _resolve_docx_name_column(docx_df)

    unique_names = (
        csv_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    outer_dict = build_outer_dict_from_names(unique_names)

    names_df = unique_names.copy()
    names_df["name_key"] = [
        NameKey(first_name=row[KTP_FIRST_NAME_COL], last_name=row[KTP_LAST_NAME_COL]).to_json_key()
        for row in names_df.to_dict("records")
    ]

    conn = duckdb.connect()
    conn.register("ktp_csv_df", csv_df)
    conn.register("ktp_docx_df", docx_df)
    conn.register("ktp_names_df", names_df)

    conn.execute("CREATE OR REPLACE TABLE ktp_csv_norm AS SELECT * FROM ktp_csv_df")
    conn.execute("CREATE OR REPLACE TABLE ktp_docx_norm AS SELECT * FROM ktp_docx_df")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE ktp_names AS
        SELECT
            name_key,
            "{KTP_FIRST_NAME_COL}",
            "{KTP_LAST_NAME_COL}"
        FROM ktp_names_df
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE ktp_csv_matches AS
        SELECT n.name_key, c.*
        FROM ktp_csv_norm c
        JOIN ktp_names n
          ON c."{KTP_FIRST_NAME_COL}" = n."{KTP_FIRST_NAME_COL}"
         AND c."{KTP_LAST_NAME_COL}" = n."{KTP_LAST_NAME_COL}"
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE ktp_docx_matches AS
        WITH names AS (
            SELECT
                name_key,
                "{KTP_FIRST_NAME_COL}" AS first_name,
                "{KTP_LAST_NAME_COL}" AS last_name,
                regexp_replace(lower("{KTP_FIRST_NAME_COL}"), '[^0-9a-z]+', '', 'g') AS first_clean,
                regexp_replace(lower("{KTP_LAST_NAME_COL}"), '[^0-9a-z]+', '', 'g') AS last_clean
            FROM ktp_names
            WHERE "{KTP_FIRST_NAME_COL}" IS NOT NULL
              AND "{KTP_LAST_NAME_COL}" IS NOT NULL
              AND "{KTP_FIRST_NAME_COL}" <> ''
              AND "{KTP_LAST_NAME_COL}" <> ''
        ),
        docx AS (
            SELECT
                *,
                regexp_replace(
                    lower(COALESCE("{docx_name_column}", '')),
                    '[^0-9a-z]+',
                    '',
                    'g'
                ) AS docx_clean
            FROM ktp_docx_norm
        )
        SELECT n.name_key, d.*
        FROM names n
        CROSS JOIN docx d
        WHERE n.first_clean <> ''
          AND n.last_clean <> ''
          AND d.docx_clean <> ''
          AND POSITION(n.first_clean IN d.docx_clean) > 0
          AND POSITION(n.last_clean IN d.docx_clean) > 0
        """
    )

    csv_matches = conn.execute("SELECT * FROM ktp_csv_matches").df()
    docx_matches = conn.execute("SELECT * FROM ktp_docx_matches").df()
    conn.close()

    _append_matches(
        outer_dict,
        csv_matches,
        CsvDuckdbMatchProcedure(),
        csv_resources,
        fragment_col=CSV_ROW_INDEX_COL,
    )
    _append_matches(
        outer_dict,
        docx_matches,
        DocxDuckdbMatchProcedure(),
        docx_resources,
        fragment_col=DOCX_FRAGMENT_COL,
    )

    cards: dict[str, str] = {}
    today = datetime.now(ZoneInfo("America/Toronto")).strftime("%B %d, %Y")
    intro = INTRODUCTION.format(today) + "\n\n"
    excluded_cols = {
        KTP_FILENAME_COL,
        SOURCE_KEY_COL,
        CSV_ROW_INDEX_COL,
        DOCX_TABLE_INDEX_COL,
        DOCX_ROW_INDEX_COL,
        DOCX_FRAGMENT_COL,
    }

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
                if col in excluded_cols or pd.isna(val):
                    continue
                if "\n" in str(val):
                    card += f"**{col}**:\n\n{str(val).replace('\n','\n\n')}\n\n"
                else:
                    card += f"**{col}**: {str(val)}\n\n"
        cards[docx_filename] = card

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{csv_dir.name}_combined_cards.zip"

    if output_format == "txt":
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_paths = []
            for filename, card in cards.items():
                txt_path = Path(tmpdir) / f"{filename}.txt"
                txt_path.write_text(intro + card, encoding="utf-8")
                txt_paths.append(txt_path)
            with ZipFile(zip_path, "w") as zipf:
                for path in txt_paths:
                    zipf.write(path, arcname=path.name)
        console.print(f"[green]Saved Markdown (*.txt) files to: {zip_path}[/green]")
        return

    if output_format == "docx":
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_ref_path = Path(tmpdir) / Path(PANDOC_REFERENCE_DOCX_PATH).name
            shutil.copy(PANDOC_REFERENCE_DOCX_PATH, tmp_ref_path)
            docx_paths: list[Path] = []
            for filename, card in cards.items():
                md_path = Path(tmpdir) / f"{filename}.md"
                docx_path = Path(tmpdir) / f"{filename}.docx"
                md_path.write_text(intro + card, encoding="utf-8")
                subprocess.run(
                    [
                        "pandoc",
                        str(md_path),
                        "-o",
                        str(docx_path),
                        "--reference-doc",
                        str(tmp_ref_path),
                    ],
                    check=True,
                )
                docx_paths.append(docx_path)
            with ZipFile(zip_path, "w") as zipf:
                for path in docx_paths:
                    zipf.write(path, arcname=path.name)
        console.print(f"[green]Saved DOCX files to: {zip_path}[/green]")
        return

    console.print(f"[red]Unsupported output format: {output_format}[/red]")

# ==============================================================================
# PIPELINE MANAGEMENT
# ==============================================================================

class PipelineManager:
    def __init__(self):
        self.state = self._load_state()
        self.conn = None

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {"steps_completed": []}

    def save_state(self, step_name):
        if step_name not in self.state["steps_completed"]:
            self.state["steps_completed"].append(step_name)
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f)

    def is_done(self, step_name):
        return step_name in self.state["steps_completed"]

    def connect_db(self):
        # Persistent DB allows us to resume state if python crashes
        self.conn = duckdb.connect(DB_FILE)
        # 20GB limit to be safe within 24GB RAM
        self.conn.execute("SET memory_limit='20GB'")
        # Enable unaccent for name matching
        self.conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;") 

    def close(self):
        if self.conn:
            self.conn.close()

# ==============================================================================
# MAIN LOGIC
# ==============================================================================

def run_reproduction():
    monitor = ResourceMonitor()
    monitor.start()
    
    pm = PipelineManager()
    
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )
    
    title = f"SciSciNet Enrichment Pipeline | {datetime.now().year}"
    layout["header"].update(Panel(title, style="bold white on blue"))
    layout["footer"].update(Panel(f"Target: Reproducible Output @ {OUTPUT_FILE}", style="italic grey50"))

    start_time = time.time()

    with Live(layout, refresh_per_second=4, console=console) as live:
        
        def log(msg, style="white"):
            layout["body"].update(Panel(msg, style=style, title="Current Task"))

        # ------------------------------------------------------------------
        # STEP 1: VERIFY INPUTS
        # ------------------------------------------------------------------
        if not pm.is_done("verify_inputs"):
            log("Verifying Input Integrity (SHA256)...", style="cyan")
            
            # Create a progress table for hashing
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                "•",
                TextColumn("{task.fields[filename]}"),
            )
            layout["body"].update(Panel(progress, title="Integrity Check"))

            for key, conf in FILES_CONFIG.items():
                if not os.path.exists(conf["path"]):
                    console.print(f"[bold red]ERROR: Missing file {conf['path']}[/bold red]")
                    console.print("Please download from HuggingFace/Source and place in directory.")
                    sys.exit(1)
                
                # Skip hash check if placeholder is still there (developer mode)
                if conf["sha256"].startswith("REPLACE"):
                    continue

                task = progress.add_task(f"Hashing {conf['desc']}", total=os.path.getsize(conf["path"]), filename=conf["path"])
                computed = calculate_sha256(conf["path"], progress, task)
                
                if computed != conf["sha256"]:
                    layout["body"].update(Panel(f"HASH MISMATCH: {conf['path']}\nExpected: {conf['sha256']}\nGot: {computed}", style="bold red"))
                    sys.exit(1)

            pm.save_state("verify_inputs")

        # ------------------------------------------------------------------
        # STEP 2: LOAD & PREP INPUT DATAFRAME
        # ------------------------------------------------------------------
        pm.connect_db()
        
        if not pm.is_done("prep_input"):
            log("Loading and Normalizing Input DataFrame...", style="yellow")
            
            # Load user pandas DF
            # Assuming pickle for speed, but could be csv
            try:
                if FILES_CONFIG["input_df"]["path"].endswith(".pkl"):
                    df = pd.read_pickle(FILES_CONFIG["input_df"]["path"])
                else:
                    df = pd.read_csv(FILES_CONFIG["input_df"]["path"])
            except Exception as e:
                console.print(f"[red]Failed to load input df: {e}[/red]")
                sys.exit(1)

            # Pre-calculate match key in Python to save DB compute
            # Strip diacritics via simple string methods if simple, but DB unaccent is better for robust logic.
            #
            # For reference:
            # unaccent(VARCHAR) → VARCHAR
            # Provides a more comprehensive transliteration of a string. It first strips all diacritics and then converts other special characters and ligatures (e.g., Æ → AE, ø → o, ß → ss) to their basic Latin equivalents.
            # https://github.com/moj-analytical-services/splink_udfs
            
            # Here we just ensure we have the columns.
            df['match_name'] = (df[HCR_FIRST_NAME] + " " + df[HCR_LAST_NAME]).astype(str)
            
            # Register into DuckDB
            pm.conn.register('df_source', df)
            
            # Create a persistent table for the input, normalizing names
            pm.conn.execute("""
                CREATE OR REPLACE TABLE input_researchers AS 
                SELECT 
                    *, 
                    lower(unaccent(match_name)) as match_key_norm
                FROM df_source
            """)
            
            pm.save_state("prep_input")

        # ------------------------------------------------------------------
        # STEP 3: FIND AUTHORS (The Heavy Join)
        # ------------------------------------------------------------------
        if not pm.is_done("match_authors"):
            log("Matching Authors against 4GB Details File...", style="magenta")

            ### DEBUG ###
            # Run your query
            # res = pm.conn.execute(f"""
            #     SELECT
            #         authorid,
            #         display_name,
            #         display_name_alternatives,
            #         length(display_name_alternatives) AS len,
            #         unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
            #     FROM read_parquet('{FILES_CONFIG["author_details"]["path"]}')
            #     LIMIT 10;
            # """)

            # # Fetch all rows
            # rows = res.fetchall()

            # # Print them nicely
            # for row in rows:
            #     print(row)

            # exit(0)
            ### END DEBUG ###
            
            # Technique: We don't load the parquet. We query it directly.
            # We handle the "serialized list" by treating it as string manipulation 
            # because JSON parsing can be strict about quotes.
            # Assumption: serialized list looks like `["Name A", "Name B"]`
            
            strict_query = f"""
                CREATE OR REPLACE TABLE matched_authors_bridge AS
                WITH parq AS (
                    SELECT 
                        authorid, 
                        display_name,
                        display_name_alternatives,
                        unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
                    FROM read_parquet('{FILES_CONFIG["author_details"]["path"]}')
                    
                    UNION ALL
                    
                    SELECT
                        authorid,
                        display_name,
                        display_name_alternatives,
                        display_name as alt_name
                    FROM read_parquet('{FILES_CONFIG["author_details"]["path"]}')
                )
                SELECT DISTINCT
                    i.match_key_norm,
                    p.authorid,
                    p.display_name,
                    p.display_name_alternatives
                FROM input_researchers i
                JOIN parq p ON lower(unaccent(p.alt_name)) = i.match_key_norm
            """
            
            # Executing the query
            pm.conn.execute(strict_query)
            pm.save_state("match_authors")

        # ------------------------------------------------------------------
        # STEP 4: RETRIEVE PAPERS (Graph Traversal)
        # ------------------------------------------------------------------
        if not pm.is_done("get_papers"):
            log("Retrieving Paper IDs (Filtering 12GB file)...", style="blue")
            
            # Since we have the authors now (likely < 100k rows), this join is fast
            # DuckDB pushes the filter down to the parquet reader
            pm.conn.execute(f"""
                CREATE OR REPLACE TABLE author_papers AS
                SELECT 
                    b.match_key_norm,
                    b.authorid,
                    pap.paperid
                FROM matched_authors_bridge b
                JOIN read_parquet('{FILES_CONFIG["authors_paper"]["path"]}') pap 
                ON b.authorid = pap.authorid
            """)
            pm.save_state("get_papers")

        # ------------------------------------------------------------------
        # STEP 5: ENRICH HITS & FIELDS
        # ------------------------------------------------------------------
        if not pm.is_done("enrich_stats"):
            log("Enriching with Hits and Fields...", style="green")
            
            # 1. Union the hit files virtually
            pm.conn.execute(f"""
                CREATE OR REPLACE VIEW all_hits AS 
                SELECT paperid, fieldid, hit_1pct, 'level0' as level FROM read_parquet('{FILES_CONFIG["hit_papers_0"]["path"]}')
                UNION ALL
                SELECT paperid, fieldid, hit_1pct, 'level1' as level FROM read_parquet('{FILES_CONFIG["hit_papers_1"]["path"]}')
            """)
            
            # 2. Join Papers to Hits and Fields
            # We aggregate here
            pm.conn.execute(f"""
                CREATE OR REPLACE TABLE final_agg AS
                SELECT 
                    ap.match_key_norm,
                    ap.authorid,
                    
                    -- Sum Hits
                    SUM(COALESCE(h.hit_1pct, 0)) as sum_hit_1pct,
                    
                    -- Collect Paper IDs (Serialized List)
                    list(ap.paperid) FILTER (WHERE h.level = 'level0') as paperids_level0_list,
                    list(ap.paperid) FILTER (WHERE h.level = 'level1') as paperids_level1_list,
                    
                    -- Fields (arbitrarily taking one if author maps to multiple papers with diff fields, 
                    -- OR do we want list of fields? Requirement says "all cols of fields left joined".
                    -- Usually fields are per paper. If we group by author, we need to decide how to represent fields.
                    -- Assuming requirement implies: "For the author, what is their Field?" 
                    -- But fields are linked to papers. 
                    -- Let's assume we take the Mode (most common) field or the field of the most cited paper.
                    -- SIMPLIFICATION: I will List_Agg the field IDs for now, or take the first non-null.
                    -- *Re-reading requirement*: "enrich my pandas df... left joined by fieldid = id"
                    -- This implies the INPUT df has fieldid? No, input only has names.
                    -- Hit papers has fieldid.
                    -- Context implies: One author -> Many Papers -> Many Fields.
                    -- Strategy: We will list_agg unique field IDs.
                    
                    LIST(DISTINCT h.fieldid) as field_ids
                    
                FROM author_papers ap
                LEFT JOIN all_hits h ON ap.paperid = h.paperid
                GROUP BY ap.match_key_norm, ap.authorid
            """)
            
            # 3. Join with Fields Definition (Tiny file)
            # Since an author might have multiple fields, we can't just join one row.
            # However, to keep the output tabular as requested (>60k rows ok), 
            # maybe we explode? No, requirement says "keep pandas normalized... when >1 matching authorid separate rows".
            # It didn't say separate rows for papers.
            # I will serialize the lists as requested strings.
            
            pm.save_state("enrich_stats")

        # ------------------------------------------------------------------
        # STEP 6: EXPORT
        # ------------------------------------------------------------------
        if not pm.is_done("export"):
            log("Finalizing and Exporting...", style="white")
            
            # We join back to the normalized inputs
            # We need to cast lists to strings to match "serialized list[str]" requirement
            final_query = """
                SELECT 
                    i.*, -- Original cols
                    f.authorid,
                    mb.display_name,
                    mb.display_name_alternatives,
                    f.sum_hit_1pct,
                    CAST(f.paperids_level0_list AS VARCHAR) as paperids_level0,
                    CAST(f.paperids_level1_list AS VARCHAR) as paperids_level1,
                    CAST(f.field_ids AS VARCHAR) as field_ids_list
                FROM input_researchers i
                JOIN matched_authors_bridge mb ON i.match_key_norm = mb.match_key_norm
                LEFT JOIN final_agg f ON (f.authorid = mb.authorid)
            """
            
            df_final = pm.conn.execute(final_query).df()
            
            # Save
            df_final.to_csv(OUTPUT_FILE, index=False)
            pm.save_state("export")

    # ==============================================================================
    # SUMMARY
    # ==============================================================================
    peak_ram = monitor.stop()
    total_time = time.time() - start_time
    pm.close()

    # Display Metrics
    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    m_table.add_column("Reference", style="dim")

    m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB", f"{REFERENCE_METRICS['peak_ram_gb']} GB")
    m_table.add_row("Total Time", f"{total_time:.1f} s", f"{REFERENCE_METRICS['total_time_s']} s")
    m_table.add_row("Output Rows", str(len(df_final)) if 'df_final' in locals() else "N/A", "> 60000")

    console.print(m_table)
    console.print(f"[bold green]Success! Output saved to: {OUTPUT_FILE}[/bold green]")
    console.print("[italic]Note: Update the 'REFERENCE_METRICS' dictionary in the script with these values for future runs.[/italic]")


def run_ktp_interactive() -> None:
    """Run the KTP enrichment pipeline in interactive mode."""
    console.print("[bold blue]Document Enrichment Tool - Interactive Mode[/bold blue]\n")

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

    output_format = Prompt.ask("Output format", choices=["txt", "docx"], default="txt")

    process_documents(docx_dir, csv_dir, recursive, output_dir, output_format)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Data enrichment pipelines.")
    subparsers = parser.add_subparsers(dest="command")

    process_parser = subparsers.add_parser(
        "process", help="Process DOCX files and enrich with CSV data."
    )
    process_parser.add_argument("docx_dir", type=Path)
    process_parser.add_argument("csv_dir", type=Path)
    process_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search recursively for DOCX and CSV files",
    )
    process_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Output directory (default: ./output)",
    )
    process_parser.add_argument(
        "--output-format",
        choices=["txt", "docx"],
        default="txt",
        help="Output format: txt (markdown) or docx (default: txt)",
    )

    subparsers.add_parser("interactive", help="Run KTP enrichment interactively.")
    subparsers.add_parser("sciscinet", help="Run SciSciNet enrichment pipeline.")

    args = parser.parse_args(argv)
    if args.command is None:
        run_reproduction()
        return
    if args.command == "interactive":
        run_ktp_interactive()
        return
    if args.command == "process":
        process_documents(
            args.docx_dir,
            args.csv_dir,
            args.recursive,
            args.output_dir,
            args.output_format,
        )
        return
    if args.command == "sciscinet":
        run_reproduction()
        return

    parser.print_help()

def signal_handler(sig, frame):
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        main()
    except Exception:
        console.print_exception()
        sys.exit(1)
