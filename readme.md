
# CCDI CPI ETL

Prefect-based ETL pipeline for the Cancer Participant Index (CPI). It reads participant mapping data from MySQL, builds a relationship graph, writes results back to the database, and updates statistics.

## How it works

1. Reads participant mappings from the `cpi.mapping` table
2. Builds an undirected graph with NetworkX and computes all-pairs shortest paths
3. Writes the linked sets as JSON and uploads to S3
4. Updates `cpi.participant.alternative_participants` in bulk
5. Records a new version and updates `cpi.domain_counts` and `cpi.statistic`
6. Sends start/completion notifications via SNS

## Prerequisites

- Python 3.9+
- [Prefect](https://docs.prefect.io) 3.2.14+
- AWS credentials with access to Secrets Manager, S3, and SNS
- A running Prefect work pool named `ccdi-cpi-2gb-prefect-3.2.14-python3.9`

## Setup

```bash
pip install -r requirements.txt
```

## Deploy

```bash
prefect deploy --all
```

## Run

```bash
prefect deployment run cpi-etl-pipeline/cpi-etl-on-demand
```

## Key files

| File | Purpose |
|---|---|
| `main_prefect.py` | Prefect flow and tasks — sole entry point |
| `prefect.yaml` | Deployment configuration |
| `requirements.txt` | Python dependencies |

