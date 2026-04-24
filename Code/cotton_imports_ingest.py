"""
Hardmine — TDM Cotton Imports Ingest
======================================
Usage:
    python cotton_imports_ingest.py            # incremental
    python cotton_imports_ingest.py --full     # full history from 201701

Saves to: ../Database/tdm_cotton_imports.parquet
"""

import argparse
import io
import logging
import sys
from datetime import datetime
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd
import requests

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "cotton_imports_ingest.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

API_KEY  = "xngwppoelwepdtqylwakbfmyqxuytfnl"
BASE_URL = "https://www1.tdmlogin.com/tdm/api/api.asp"

REPORTERS = "KR,UA,PE,TW,SG,CN,NZ,US,TR"

HS_CODES = ["52"]

FLOW         = "I"
LEVEL        = "4"
FREQUENCY    = "M"
SEPARATOR    = "T"
AGG_PARTNERS = "Y"
CONV         = "1"

PERIOD_FULL_BEGIN = "201701"
PERIOD_END        = "203012"

OUT_FILE = Path(__file__).parents[1] / "Database" / "tdm_cotton_imports.parquet"

COLUMNS    = ["REPORTER", "PARTNER", "COMMODITY", "YEAR", "MONTH", "QTY1"]
DEDUP_KEYS = ["REPORTER", "PARTNER", "COMMODITY", "YEAR", "MONTH"]

HS4_TAG = {
    "5201": "Raw Cotton",
    "5202": "Cotton Waste",
    "5203": "Cotton, Carded/Combed",
    "5204": "Cotton Sewing Thread",
    "5205": "Cotton Yarn >=85%",
    "5206": "Cotton Yarn <85%",
    "5207": "Cotton Yarn Retail",
    "5208": "Woven Fabric >=85% <=200g",
    "5209": "Woven Fabric >=85% >200g",
    "5210": "Woven Fabric <85% <=200g",
    "5211": "Woven Fabric <85% >200g",
    "5212": "Other Woven Cotton",
}

REPORTER_REGION = {
    "Korea, Republic of":           "Asia",
    "Ukraine":                      "Europe",
    "Peru":                         "LATAM",
    "Taiwan":                       "Asia",
    "Taiwan, Province of China":    "Asia",
    "Singapore":                    "Asia",
    "China":                        "Asia",
    "China, People's Republic of":  "Asia",
    "New Zealand":                  "Oceania",
    "United States":                "NAM",
    "United States of America":     "NAM",
    "Turkey":                       "Europe",
    "Türkiye":                      "Europe",
}

PARTNER_FIX = {
    "United States":            "United States of America",
    "Russia":                   "Russian Federation",
    "South Korea":              "Korea, Republic of",
    "Iran":                     "Iran, Islamic Republic of",
    "Vietnam":                  "Viet Nam",
    "Venezuela":                "Venezuela, Bolivarian Republic of",
    "Bolivia":                  "Bolivia, Plurinational State of",
    "Tanzania":                 "Tanzania, United Republic of",
    "Taiwan":                   "Taiwan, Province of China",
    "Cote d'Ivoire":            "Cote d'Ivoire",
    "Congo (ROC)":              "Congo",
    "Congo (DROC)":             "Democratic Republic of the Congo",
    "Netherlands Antilles":     "Other",
    "Duty Free Shops":          "Other",
    "Stores and Provisions":    "Other",
    "Other Asia, nes":          "Other",
    "Free Zones":               "Other",
    "High Seas":                "Other",
    "Unidentified":             "Other",
}

NAM = {"Canada", "United States of America", "Bermuda", "Greenland"}
LATAM = {
    "Argentina","Belize","Bolivia, Plurinational State of","Brazil","Chile",
    "Colombia","Costa Rica","Cuba","Dominican Republic","Ecuador","El Salvador",
    "French Guiana","Guatemala","Guyana","Haiti","Honduras","Jamaica","Mexico",
    "Nicaragua","Panama","Paraguay","Peru","Suriname","Trinidad and Tobago",
    "Uruguay","Venezuela, Bolivarian Republic of",
}


def build_url(period_begin: str) -> str:
    return (
        f"{BASE_URL}?key={API_KEY}"
        f"&flow={FLOW}&reporter={REPORTERS}&partners=all"
        f"&periodBegin={period_begin}&periodEnd={PERIOD_END}"
        f"&hsCode={','.join(HS_CODES)}&levelDetail={LEVEL}"
        f"&frequency={FREQUENCY}&separator={SEPARATOR}"
        f"&aggregatePartners={AGG_PARTNERS}&conv={CONV}"
    )


def decode_response(content: bytes) -> str:
    for enc in ("utf-16", "utf-8-sig", "latin1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def fetch_tdm(period_begin: str) -> pd.DataFrame:
    url = build_url(period_begin)
    log.info("Fetching Cotton Imports from %s ...", period_begin)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(decode_response(resp.content)), sep="\t", low_memory=False)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df = df[COLUMNS].copy()
    log.info("  -> %d rows fetched", len(df))
    return df


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    commodity = df["COMMODITY"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    df["HS4"]            = commodity.str[:4]
    df["CROP_YEAR"]      = df["YEAR"].astype(str)
    df["CROP_MONTH_NUM"] = df["MONTH"]

    p = df["PARTNER"].astype(str).str.strip().replace(PARTNER_FIX)
    cc = coco.CountryConverter()
    logging.getLogger("country_converter").setLevel(logging.ERROR)
    unique = p.dropna().unique().tolist()
    cont_map = dict(zip(unique, cc.convert(names=unique, to="continent", not_found="Other")))
    continent = p.map(cont_map).fillna("Other")

    df["REGION"] = np.select(
        [p.eq("Other"), p.isin(NAM), p.isin(LATAM),
         continent.eq("Europe"), continent.eq("Asia"),
         continent.eq("Africa"), continent.eq("Oceania")],
        ["Other", "NAM", "LATAM", "Europe", "Asia", "Africa", "Oceania"],
        default="Other",
    )
    df["REPORTER_REGION"] = df["REPORTER"].map(REPORTER_REGION).fillna("Other")
    df["COMMODITY_TAG"]   = df["HS4"].map(HS4_TAG).fillna("Other Cotton")
    return df


def incremental_period_begin(existing: pd.DataFrame) -> str:
    return f"{int(existing['YEAR'].max())}01"


def merge_and_dedup(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([old, new], ignore_index=True)
    before = len(merged)
    merged = merged.drop_duplicates(subset=DEDUP_KEYS, keep="last")
    log.info("  Dedup: %d -> %d rows (-%d)", before, len(merged), before - len(merged))
    return merged


def main():
    parser = argparse.ArgumentParser(description="Cotton Imports Ingest")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Cotton Imports Ingest  |  %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("Mode: %s", "FULL" if args.full else "INCREMENTAL")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if args.full or not OUT_FILE.exists():
        period_begin = PERIOD_FULL_BEGIN
    else:
        existing_check = pd.read_parquet(OUT_FILE, columns=["YEAR"])
        period_begin   = incremental_period_begin(existing_check)
        log.info("Incremental from %s", period_begin)

    new_data = fetch_tdm(period_begin)
    new_data = add_derived_columns(new_data)

    if OUT_FILE.exists() and not args.full:
        old_data = pd.read_parquet(OUT_FILE)
        log.info("Existing: %d rows", len(old_data))
        df = merge_and_dedup(old_data, new_data)
    else:
        df = new_data.copy()

    df.to_parquet(OUT_FILE, engine="pyarrow", index=False)
    log.info("Saved -> %s  |  %d rows", OUT_FILE, len(df))
    log.info("=" * 60)


if __name__ == "__main__":
    main()
