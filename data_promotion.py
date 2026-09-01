"""
Prefect flows for CPI MySQL data promotion, split into two deployments:

  1) cpi_db_dump    — mysqldump from dev, strip incompatible lines, upload to S3.
  2) cpi_db_restore — download a dump from S3 and restore into qa / stage / prod.

Running them as separate deployments lets you dump once and restore into multiple
target environments (each restore is its own run and audit trail).
"""

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import boto3
from prefect import flow, task, get_run_logger
from prefect.flow_runs import pause_flow_run

from main_prefect import get_mysql_credentials, notify_completion

S3_BUCKET = os.getenv("S3_BUCKET", "ccdi-nonprod-cpi-source-data")
S3_DUMP_PREFIX = os.getenv("S3_DUMP_PREFIX", "db-dumps")
SOURCE_SECRET = os.getenv("SOURCE_DB_SECRET", "ccdi-dev-cpi-mysql")
DB_NAME = os.getenv("DB_NAME", "cpi")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Lines that RDS mysqldump emits but the target RDS refuses on restore.
# Matches the two lines the user was removing manually in Workbench.
_STRIP_PATTERNS = [
    re.compile(r"@@GLOBAL\.GTID_PURGED"),
    re.compile(r"@@SESSION\.SQL_LOG_BIN"),
]

VALID_ENVS = {"qa", "stage", "prod"}


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"`{name}` binary not found on PATH. Install mysql-client in the work-pool image."
        )
    return path


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError(f"Invalid s3 URI: {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


# ── Dump-side tasks ───────────────────────────────────────────────────────────

@task(name="dump_source_db", retries=1, retry_delay_seconds=30)
def dump_source_db(work_dir: str) -> str:
    logger = get_run_logger()
    mysqldump = _require_binary("mysqldump")
    creds = get_mysql_credentials(SOURCE_SECRET)

    ts = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    dump_path = Path(work_dir) / f"cpi_dump_{ts}.sql"

    cmd = [
        mysqldump,
        "-h", creds["host"],
        "-P", str(creds.get("port", 3306)),
        "-u", creds["user_name"],
        "--single-transaction",
        "--set-gtid-purged=OFF",   # avoids the GTID_PURGED line entirely
        "--column-statistics=0",   # dropped automatically if unsupported
        "--routines",
        "--triggers",
        "--events",
        DB_NAME,
    ]
    env = {**os.environ, "MYSQL_PWD": creds["password"]}

    logger.info(f"Dumping {DB_NAME}@{creds['host']} to {dump_path}")
    with open(dump_path, "wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=env, check=False)
    if proc.returncode != 0 and b"unknown variable 'column-statistics'" in proc.stderr:
        logger.warning("mysqldump does not support --column-statistics; retrying without it.")
        cmd.remove("--column-statistics=0")
        with open(dump_path, "wb") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump failed: {proc.stderr.decode('utf-8', 'replace')}")

    size_mb = dump_path.stat().st_size / (1024 * 1024)
    logger.info(f"Dump complete: {dump_path} ({size_mb:.1f} MB)")
    return str(dump_path)


@task(name="sanitize_dump")
def sanitize_dump(dump_path: str) -> str:
    logger = get_run_logger()
    src = Path(dump_path)
    cleaned = src.with_name(src.stem + "_clean.sql")
    stripped = 0
    with open(src, "r", encoding="utf-8", errors="replace") as fin, \
         open(cleaned, "w", encoding="utf-8") as fout:
        for line in fin:
            if any(p.search(line) for p in _STRIP_PATTERNS):
                stripped += 1
                logger.info(f"Stripped line: {line.rstrip()[:120]}")
                continue
            fout.write(line)
    logger.info(f"Sanitized dump written to {cleaned} (stripped {stripped} lines)")
    return str(cleaned)


@task(name="upload_dump_to_s3", retries=2, retry_delay_seconds=10)
def upload_dump_to_s3(dump_path: str) -> str:
    logger = get_run_logger()
    ts = datetime.now(ZoneInfo("America/New_York")).strftime("%Y/%m/%d")
    key = f"{S3_DUMP_PREFIX}/{ts}/{Path(dump_path).name}"
    s3 = boto3.client("s3", region_name=AWS_REGION)
    s3.upload_file(dump_path, S3_BUCKET, key)
    uri = f"s3://{S3_BUCKET}/{key}"
    logger.info(f"Uploaded dump to {uri}")
    return uri


# ── Restore-side tasks ────────────────────────────────────────────────────────

@task(name="resolve_dump_s3_uri")
def resolve_dump_s3_uri(s3_uri: str) -> str:
    """Return s3_uri as-is, or find the newest dump under S3_DUMP_PREFIX when 'latest'."""
    logger = get_run_logger()
    if s3_uri and s3_uri.lower() != "latest":
        return s3_uri

    s3 = boto3.client("s3", region_name=AWS_REGION)
    paginator = s3.get_paginator("list_objects_v2")
    latest = None
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=f"{S3_DUMP_PREFIX}/"):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".sql"):
                continue
            if latest is None or obj["LastModified"] > latest["LastModified"]:
                latest = obj
    if latest is None:
        raise RuntimeError(
            f"No .sql dumps found under s3://{S3_BUCKET}/{S3_DUMP_PREFIX}/"
        )
    uri = f"s3://{S3_BUCKET}/{latest['Key']}"
    logger.info(f"Resolved 'latest' to {uri} (LastModified={latest['LastModified']})")
    return uri


@task(name="download_dump_from_s3", retries=2, retry_delay_seconds=10)
def download_dump_from_s3(s3_uri: str, work_dir: str) -> str:
    logger = get_run_logger()
    bucket, key = _parse_s3_uri(s3_uri)
    dest = Path(work_dir) / Path(key).name
    boto3.client("s3", region_name=AWS_REGION).download_file(bucket, key, str(dest))
    logger.info(f"Downloaded {s3_uri} → {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    return str(dest)


@task(name="restore_target_db", retries=0)
def restore_target_db(dump_path: str, target_env: str) -> None:
    logger = get_run_logger()
    mysql = _require_binary("mysql")
    secret_name = f"ccdi-{target_env}-cpi-mysql"
    creds = get_mysql_credentials(secret_name)

    cmd = [
        mysql,
        "-h", creds["host"],
        "-P", str(creds.get("port", 3306)),
        "-u", creds["user_name"],
        DB_NAME,
    ]
    env = {**os.environ, "MYSQL_PWD": creds["password"]}

    logger.info(f"Restoring dump into {DB_NAME}@{creds['host']} ({target_env})")
    with open(dump_path, "rb") as fh:
        proc = subprocess.run(cmd, stdin=fh, stderr=subprocess.PIPE, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"mysql restore failed for {target_env}: "
            f"{proc.stderr.decode('utf-8', 'replace')}"
        )
    logger.info(f"Restore into {target_env} complete.")


# ── Flows ─────────────────────────────────────────────────────────────────────

@flow(name="cpi-db-dump")
def cpi_db_dump() -> str:
    """Dump dev CPI DB, strip incompatible lines, upload to S3. Returns the S3 URI."""
    logger = get_run_logger()
    with tempfile.TemporaryDirectory(prefix="cpi_dump_") as work_dir:
        raw_dump = dump_source_db(work_dir)
        clean_dump = sanitize_dump(raw_dump)
        s3_uri = upload_dump_to_s3(clean_dump)

    logger.info(f"Dump artifact: {s3_uri}")
    notify_completion(
        message=f"CPI DB dump uploaded to {s3_uri}",
        subject="CPI DB dump succeeded",
    )
    return s3_uri


@flow(name="cpi-db-restore")
def cpi_db_restore(
    target_env: str,
    s3_uri: str = "latest",
    require_approval_for_prod: bool = True,
) -> None:
    """Restore an S3-hosted dump into qa / stage / prod.

    s3_uri: full s3://bucket/key of the dump, or 'latest' to pick the newest
    file under S3_DUMP_PREFIX in S3_BUCKET.
    """
    logger = get_run_logger()
    target_env = target_env.lower().strip()
    if target_env not in VALID_ENVS:
        raise ValueError(f"target_env must be one of {sorted(VALID_ENVS)}, got {target_env!r}")

    resolved_uri = resolve_dump_s3_uri(s3_uri)

    if target_env == "prod" and require_approval_for_prod:
        logger.warning(f"Prod restore of {resolved_uri} requested — pausing for approval.")
        pause_flow_run(timeout=3600)

    with tempfile.TemporaryDirectory(prefix="cpi_restore_") as work_dir:
        dump_path = download_dump_from_s3(resolved_uri, work_dir)
        try:
            restore_target_db(dump_path, target_env)
        except Exception as e:
            notify_completion(
                message=f"CPI restore to {target_env} FAILED: {e}\nDump: {resolved_uri}",
                subject=f"CPI restore FAILED ({target_env})",
            )
            raise

    notify_completion(
        message=f"CPI restore to {target_env} succeeded.\nDump: {resolved_uri}",
        subject=f"CPI restore succeeded ({target_env})",
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or sys.argv[1] not in {"dump", "restore"}:
        print("Usage: python data_promotion.py dump")
        print("       python data_promotion.py restore <qa|stage|prod> [s3_uri|latest]")
        sys.exit(1)
    if sys.argv[1] == "dump":
        cpi_db_dump()
    else:
        env = sys.argv[2] if len(sys.argv) > 2 else "qa"
        uri = sys.argv[3] if len(sys.argv) > 3 else "latest"
        cpi_db_restore(target_env=env, s3_uri=uri)
