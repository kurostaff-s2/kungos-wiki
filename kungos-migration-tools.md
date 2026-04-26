# Kungos Migration Tools

## Overview

Production-ready Django management commands for kuropurchase database restoration and entity field population. These tools are used during the final cutover to restore MongoDB data from S3 backups and populate entity fields for proper tenant isolation.

## Commands

### `restore_kuropurchase`

Parses MongoDB 8.0+ concurrent dump format and restores kuropurchase database with entity field population.

```bash
# Dry run (preview)
python manage.py restore_kuropurchase --dump /path/to/dump --dry-run

# Extract entity report only
python manage.py restore_kuropurchase --dump /path/to/dump --extract

# Full restore
python manage.py restore_kuropurchase --dump /path/to/dump --restore

# From S3 backup
python manage.py restore_kuropurchase --s3-key s3://bucket/path/dump --restore

# With custom MongoDB connection
python manage.py restore_kuropurchase --dump /path/to/dump --restore --host 10.0.0.5 --port 27017

# Generate entity report
python manage.py restore_kuropurchase --dump /path/to/dump --output /path/to/report.json
```

### `backup_kuropurchase`

Backup kuropurchase database before restoration.

```bash
# Backup all collections
python manage.py backup_kuropurchase

# Backup to custom location
python manage.py backup_kuropurchase --output /path/to/backup_dir

# Backup specific collections
python manage.py backup_kuropurchase --collections purchaseorders inwardpayments
```

### `deploy_restore`

Production deployment orchestrator that runs: backup → restore → verify.

```bash
# Standard deployment
python manage.py deploy_restore --dump /path/to/dump

# From S3 backup
python manage.py deploy_restore --s3-key s3://bucket/path/dump

# With verification
python manage.py deploy_restore --dump /path/to/dump --verify

# Force deployment (no confirmation)
python manage.py deploy_restore --dump /path/to/dump --force

# Generate deployment report
python manage.py deploy_restore --dump /path/to/dump --output /path/to/report.json
```

## Entity Distribution

After restore, data is distributed as follows:

| Entity | Documents | Percentage |
|--------|-----------|------------|
| kurogaming | 25,428 | 54.1% |
| rebellion | 17,787 | 37.8% |
| None | 3,734 | 7.9% |

## Files

- `kuroadmin/management/commands/restore_kuropurchase.py`
- `kuroadmin/management/commands/backup_kuropurchase.py`
- `kuroadmin/management/commands/deploy_restore.py`
- `kuroadmin/management/commands/README.md`
- `PRODUCTION_DEPLOYMENT.md`

## Related

- [[kungos]] — Master modernization plan
- [[kungos-log]] — Kungos departure log
- [[kungos-deployment]] — Production deployment guide
