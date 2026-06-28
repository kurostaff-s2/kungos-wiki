# Celery & Redis Setup Complete

**Date**: 2026-06-28  
**Status**: ✅ **COMPLETE**

---

## Services Running

| Service | Status | PID | Log |
|---------|--------|-----|-----|
| Redis 7.0.15 | ✅ Running | - | `redis-cli ping` → PONG |
| Celery Worker | ✅ Running | 106389 | `/tmp/celery-worker.log` |
| Celery Beat | ✅ Running | 106410 | `/tmp/celery-beat.log` |

---

## Installation Summary

### 1. Redis
```bash
echo "kuro" | sudo -S apt-get install -y redis-server
echo "kuro" | sudo -S systemctl start redis-server
```

**Version**: 7.0.15  
**Port**: 6379  
**DB**: 1 (configured in settings.py)

### 2. Celery Configuration

**Created**: `backend/celery.py`
```python
app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

**Configured**: `backend/settings.py`
```python
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/1'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/1'
CELERY_BEAT_SCHEDULE = {
    'process-outbox-batch': {
        'task': 'platform.process_outbox_batch',
        'schedule': 300.0,  # 5 minutes
    },
}
```

### 3. Development Mode (No Redis Required)

**Created**: `backend/outbox_dev.py`

For development without Redis:
```bash
python manage.py process_outbox_dev --batch-size 50
```

---

## Starting Services

### Manual Start
```bash
cd /home/chief/Coding-Projects/kteam-dj-chief
source venv/bin/activate

# Start Redis (if not running)
sudo systemctl start redis-server

# Start Celery Worker
nohup celery -A backend worker -l info -Q outbox > /tmp/celery-worker.log 2>&1 &

# Start Celery Beat
nohup celery -A backend beat -l info > /tmp/celery-beat.log 2>&1 &
```

### Verify Running
```bash
# Check Redis
redis-cli ping

# Check Worker
ps aux | grep "celery.*worker" | grep -v grep

# Check Beat
ps aux | grep "celery.*beat" | grep -v grep

# Check Logs
tail -f /tmp/celery-worker.log
tail -f /tmp/celery-beat.log
```

---

## Outbox Worker

**Task**: `platform.process_outbox_batch`  
**Schedule**: Every 5 minutes  
**Queue**: `outbox`

Processes pending outbox events from PostgreSQL to MongoDB.

### Manual Trigger (Development)
```bash
python manage.py process_outbox_dev
```

### Test Event Processing
```python
from plat.outbox.models import OutboxEvent
from plat.outbox.service import publish_in_txn

# Create test event
publish_in_txn(
    event_type='session.ended',
    bg_code='KURO0001',
    payload={'session_id': 123},
)

# Check pending events
print(OutboxEvent.objects.filter(status='pending').count())
```

---

## Files Modified/Created

| File | Action | Purpose |
|------|--------|---------|
| `backend/celery.py` | Created | Celery app configuration |
| `backend/settings.py` | Modified | Added CELERY_* config |
| `backend/outbox_dev.py` | Created | Dev-mode outbox processor |

---

## Next Steps

1. ✅ Redis installed and running
2. ✅ Celery worker running (PID 106389)
3. ✅ Celery Beat running (PID 106410)
4. ⏳ Test outbox event processing
5. ⏳ Verify cross-store consistency (PostgreSQL → MongoDB)

---

## Troubleshooting

### Worker not connecting to Redis
```bash
redis-cli ping  # Should return PONG
redis-cli -n 1 ping  # Test DB 1
```

### Beat not scheduling tasks
```bash
cat /tmp/celery-beat.log
# Check for "Scheduler: Starting..." message
```

### Outbox events not processing
```bash
# Check pending events
python manage.py shell -c "from plat.outbox.models import OutboxEvent; print(OutboxEvent.objects.filter(status='pending').count())"

# Check worker logs
tail -f /tmp/celery-worker.log
```

---

*Setup completed: 2026-06-28*  
*Status: ✅ All services operational*
