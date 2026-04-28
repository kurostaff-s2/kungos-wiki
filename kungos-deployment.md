# Kungos Production Deployment Guide

## MongoDB Dump Restore

### Quick Start

```bash
# 1. Backup existing database
python manage.py backup_kuropurchase

# 2. Dry run to preview
python manage.py restore_kuropurchase --dump /path/to/dump --dry-run

# 3. Full restore
python manage.py restore_kuropurchase --dump /path/to/dump --restore

# 4. Or use the deployment orchestrator
python manage.py deploy_restore --dump /path/to/dump --verify
```

### From S3 Backup

```bash
# Download and restore from S3
python manage.py deploy_restore --s3-key s3://kuro-db-backup/kc-backup/mongo-ip-172-31-33-158-2026-04-26-040005.dump --verify

# With custom MongoDB connection
python manage.py deploy_restore --s3-key s3://bucket/path/dump --host 10.0.0.5 --port 27017 --verify
```

### Production Checklist

#### Pre-Deployment
- [ ] Backup existing database: `python manage.py backup_kuropurchase`
- [ ] Verify backup: `ls -la backend/backups/`
- [ ] Test in staging first
- [ ] Notify team of maintenance window

#### During Deployment
- [ ] Stop application: `systemctl stop kteam-dj-chief`
- [ ] Run deployment: `python manage.py deploy_restore --dump /path/to/dump --verify`
- [ ] Wait for completion
- [ ] Start application: `systemctl start kteam-dj-chief`

#### Post-Deployment
- [ ] Check API endpoints: `curl http://localhost:8000/api/v1/kuroadmin/purchaseorders`
- [ ] Verify entity field population
- [ ] Generate deployment report: `python manage.py deploy_restore --output report.json`
- [ ] Notify team of completion

### Entity Distribution

After restore, data will be distributed as follows:

| Entity | Documents | Percentage |
|--------|-----------|------------|
| kurogaming | 25,428 | 54.1% |
| rebellion | 17,787 | 37.8% |
| None | 3,734 | 7.9% |

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Duplicate Key Errors | Expected behavior - 52 duplicates are automatically skipped |
| S3 Download Failures | Install boto3: `pip install boto3` |
| MongoDB Connection Errors | Verify MongoDB is running: `mongosh --eval "db.runCommand({ ping: 1 })"` |
| Empty Restore | Verify dump file is valid: `file /path/to/dump` |

### Rollback

If something goes wrong:

```bash
# Restore from backup
python manage.py backup_kuropurchase --output /tmp/rollback_backup

# Or use git revert
git revert HEAD
```

## Related

- [[KungOS_v2]] — Master modernization plan
- [[kungos-migration-tools]] — Migration tool documentation
- [[kungos-log]] — Kungos departure log
