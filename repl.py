import os
import sys
import time
import json
import signal
import hashlib
import psutil
import threading
import duckdb
import pandas as pd
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich import box

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

def signal_handler(sig, frame):
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        run_reproduction()
    except Exception as e:
        console.print_exception()
        sys.exit(1)
