# Legacy User Data Migration Guide

**Status:** DRAFT — Reference Implementation  
**Date:** 2026-07-01  
**Version:** 1.0  
**Purpose:** Step-by-step guide for migrating legacy user data (eShop, employees, cafe walk-ins) to the target architecture

---

## Overview

This guide covers migration of three legacy user data sources to the target `users_identity` + extension tables:

| Source | Legacy Location | Target Table | Records Migrated |
|--------|----------------|--------------|------------------|
| **Employees** | `legacy_dump.users_kurouser` (PG) | `users_identity` + `users_employee` | 67 |
| **Cafe Walk-ins** | `KungOS_Mongo_One.reb_users` + `kuropurchase.reb_users` (MongoDB) | `users_identity` + `caf_platform_walkins` | 2,416 |
| **eShop Users** | `kg_eshop_latest.users_customuser` (PG) | `users_identity` | 909 |

**Target Architecture:**
- `users_identity` — Unified identity table (replaces CustomUser, reb_users, employees, players)
- `users_employee` — Employee extension (FK → users_identity)
- `caf_platform_walkins` — Walk-in customer extension (FK → users_identity)
- `users_customer` — Customer extension (FK → users_identity) — NOT USED for eShop in this migration

---

## Prerequisites

### Database Access

| Database | Purpose | Connection |
|----------|---------|------------|
| `kuro-cadence` | Target database | `psql -U postgres -d kuro-cadence` |
| `legacy_dump` | Legacy employee data | `psql -U postgres -d legacy_dump` |
| `KungOS_Mongo_One` | Legacy walk-in data | `mongo --eval "db.getSiblingDB('KungOS_Mongo_One')"` |
| `kuropurchase` | Legacy walk-in data (LB Nagar) | `mongo --eval "db.getSiblingDB('kuropurchase')"` |
| `kg_eshop_latest` | Legacy eShop data | `psql -U postgres -d kg_eshop_latest` |

### Required Tools

- `psql` — PostgreSQL client
- `mongo` — MongoDB shell
- `python3` with `psycopg2` and `pymongo` libraries
- `pg_restore` — For restoring PostgreSQL backups

---

## Migration 1: Employees

### Source Schema

**Legacy Table:** `legacy_dump.users_kurouser` (68 records)

| Field | Type | Notes |
|-------|------|-------|
| `userid` | varchar | Employee ID (e.g., KCAD001, KCAD002) |
| `role` | varchar | Role type (KC Admin, KC Staff, KG Staff, RE Staff) |
| `primary_bg` | varchar | Primary business group |
| `joining_date` | date | Employment start date |
| `gender` | varchar | Gender |
| `dob` | date | Date of birth |
| `phone` | varchar | Phone number |
| `salary` | numeric | Salary amount |
| `pan` | varchar | PAN number |
| `bank_name` | varchar | Bank name |
| `bank_ac_no` | varchar | Bank account number |
| `ifsc_code` | varchar | IFSC code |
| `address` | text | Address |
| `emergency_contact` | text | Emergency contact details |

### Target Schema

**Target Tables:** `users_identity` + `users_employee`

```sql
-- users_identity (core identity)
identity_id CHAR(20) PRIMARY KEY,
phone VARCHAR(20),
name VARCHAR(255),
email VARCHAR(255),
bg_code VARCHAR(20),
div_code VARCHAR(20),
branch_code VARCHAR(20),
status VARCHAR(20),
phone_verified BOOLEAN,
created_at TIMESTAMP,
updated_at TIMESTAMP

-- users_employee (extension)
identity_id CHAR(20) PRIMARY KEY,  -- FK → users_identity
role VARCHAR(50),
department VARCHAR(100),
joining_date DATE,
salary NUMERIC(10,2),
bank_name VARCHAR(100),
bank_ac_no VARCHAR(50),
ifsc_code VARCHAR(20),
address TEXT,
emergency_contact TEXT,
created_at TIMESTAMP,
updated_at TIMESTAMP
```

### Migration Steps

#### Step 1: Restore Legacy Database

```bash
# Download latest backup from S3
aws s3 cp s3://kuro-db-backup/kg-backup/default-ip-172-31-26-151-2026-06-30-153005.psql.bin /tmp/kg_latest.psql.bin

# Restore to temporary database
pg_restore --dbname=legacy_dump /tmp/kg_latest.psql.bin
```

#### Step 2: Create Migration Script

**Script:** `/tmp/migrate_employees.py`

```python
#!/usr/bin/env python3
"""
Migrate employees from legacy_dump to new system.

Maps: users_kurouser → users_identity + users_employee
"""
import psycopg2
from datetime import datetime

def migrate_employees():
    """Migrate employee data to new system."""
    # Connect to legacy database
    legacy_conn = psycopg2.connect(dbname='legacy_dump', user='postgres')
    legacy_cursor = legacy_conn.cursor()
    
    # Connect to new database
    new_conn = psycopg2.connect(dbname='kuro-cadence', user='postgres')
    new_cursor = new_conn.cursor()
    
    # Get all employees from legacy
    legacy_cursor.execute("""
        SELECT userid, role, primary_bg, joining_date, gender, dob, 
               phone, salary, pan, bank_name, bank_ac_no, ifsc_code,
               address, emergency_contact
        FROM users_kurouser
        ORDER BY userid
    """)
    employees = legacy_cursor.fetchall()
    print(f"Found {len(employees)} employees to migrate")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for i, emp in enumerate(employees):
        try:
            userid, role, primary_bg, joining_date, gender, dob, \
                phone, salary, pan, bank_name, bank_ac_no, ifsc_code, \
                address, emergency_contact = emp
            
            # Map role to department
            role_map = {
                'KC Admin': 'Administration',
                'KC Staff': 'Kuro Gaming',
                'KG Staff': 'Gaming',
                'RE Staff': 'Rebellion',
            }
            department = role_map.get(role, role)
            
            # Generate identity_id from userid
            identity_id = userid  # e.g., KCAD001, KCAD002
            
            # Check if identity already exists
            new_cursor.execute("SELECT identity_id FROM users_identity WHERE identity_id = %s", (identity_id,))
            if new_cursor.fetchone():
                print(f"  Skipping {userid}: identity already exists")
                skipped += 1
                continue
            
            # Create Identity for employee
            new_cursor.execute("""
                INSERT INTO users_identity (identity_id, phone, name, email, bg_code, div_code, branch_code, status, phone_verified, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', false, %s, %s)
                RETURNING identity_id
            """, (
                identity_id,
                phone or '',
                userid,  # Use userid as name if name is not available
                '',  # Email not available in legacy
                'KURO0001',
                'KURO0001_001',
                'KURO0001_001_001',
                'active',
                joining_date or datetime.now(),
                datetime.now(),
            ))
            
            result = new_cursor.fetchone()
            new_identity_id = result[0]
            
            # Create EmployeeProfile
            new_cursor.execute("""
                INSERT INTO users_employee (identity_id, role, department, joining_date, salary, 
                                           bank_name, bank_ac_no, ifsc_code, address, emergency_contact,
                                           created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                new_identity_id,
                role or '',
                department,
                joining_date,
                salary,
                bank_name or '',
                bank_ac_no or '',
                ifsc_code or '',
                address or '',
                emergency_contact or '',
                datetime.now(),
                datetime.now(),
            ))
            
            migrated += 1
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(employees)}...")
            
        except Exception as e:
            print(f"Error migrating {userid}: {e}")
            errors += 1
            continue
    
    legacy_cursor.close()
    legacy_conn.close()
    new_cursor.close()
    new_conn.close()
    
    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total: {len(employees)}")

if __name__ == '__main__':
    migrate_employees()
```

#### Step 3: Execute Migration

```bash
python3 /tmp/migrate_employees.py
```

#### Step 4: Validate Migration

```sql
-- Check employee count
SELECT COUNT(*) FROM users_employee;

-- Check identity count for employees
SELECT COUNT(*) FROM users_identity 
WHERE identity_id LIKE 'K%';

-- Verify employee details
SELECT i.identity_id, i.phone, e.role, e.department, e.joining_date
FROM users_identity i
JOIN users_employee e ON i.identity_id = e.identity_id
LIMIT 10;
```

---

## Migration 2: Cafe Walk-ins

### Source Schema

**Legacy Collections:** `KungOS_Mongo_One.reb_users` + `kuropurchase.reb_users` (MongoDB)

| Field | Type | Notes |
|-------|------|-------|
| `_id` | ObjectId | MongoDB document ID |
| `phone` | string | Phone number |
| `name` | string | Customer name |
| `email` | string | Email address |
| `bg_code` | string | Business group code |
| `div_code` | string | Division code |
| `branch_code` | string | Branch code |

### Target Schema

**Target Tables:** `users_identity` + `caf_platform_walkins`

```sql
-- users_identity (core identity)
identity_id CHAR(20) PRIMARY KEY,
phone VARCHAR(20),
name VARCHAR(255),
email VARCHAR(255),
bg_code VARCHAR(20),
div_code VARCHAR(20),
branch_code VARCHAR(20),
status VARCHAR(20),
phone_verified BOOLEAN,
created_at TIMESTAMP,
updated_at TIMESTAMP

-- caf_platform_walkins (extension)
identity_id CHAR(20) PRIMARY KEY,  -- FK → users_identity
created_at TIMESTAMP,
updated_at TIMESTAMP
```

### Migration Steps

#### Step 1: Create Migration Script

**Script:** `/tmp/migrate_walkins.py`

```python
#!/usr/bin/env python3
"""
Migrate cafe walk-ins from MongoDB to new system.

Maps: reb_users (MongoDB) → users_identity + caf_platform_walkins
"""
import psycopg2
import pymongo
from datetime import datetime
import hashlib

def migrate_walkins():
    """Migrate walk-in data from MongoDB to PostgreSQL."""
    # Connect to MongoDB
    mongo_client = pymongo.MongoClient('mongodb://127.0.0.1:27017/')
    mongo_db = mongo_client['KungOS_Mongo_One']
    reb_users = mongo_db['reb_users']
    
    # Connect to legacy database (kuropurchase)
    legacy_conn = psycopg2.connect(dbname='kuropurchase', user='postgres')
    legacy_cursor = legacy_conn.cursor()
    
    # Connect to new database
    new_conn = psycopg2.connect(dbname='kuro-cadence', user='postgres')
    new_conn.autocommit = True
    new_cursor = new_conn.cursor()
    
    # Get all walk-ins from MongoDB
    mongo_users = list(reb_users.find({}, {'phone': 1, 'name': 1, 'email': 1, 'bg_code': 1, 'div_code': 1, 'branch_code': 1}))
    print(f"Found {len(mongo_users)} walk-ins in MongoDB")
    
    # Get all walk-ins from legacy database
    legacy_cursor.execute("SELECT phone, name, email, bg_code, div_code, branch_code FROM reb_users ORDER BY phone")
    legacy_users = legacy_cursor.fetchall()
    print(f"Found {len(legacy_users)} walk-ins in legacy database")
    
    # Combine and deduplicate
    all_users = {}
    
    for user in mongo_users:
        phone = user.get('phone', '')
        if phone and phone not in all_users:
            all_users[phone] = {
                'phone': phone,
                'name': user.get('name', ''),
                'email': user.get('email', ''),
                'bg_code': user.get('bg_code', 'KURO0001'),
                'div_code': user.get('div_code', 'KURO0001_002'),
                'branch_code': user.get('branch_code', 'KURO0001_002_001'),
                'source': 'mongo'
            }
    
    for user in legacy_users:
        phone = user[0]
        if phone and phone not in all_users:
            all_users[phone] = {
                'phone': phone,
                'name': user[1] or '',
                'email': user[2] or '',
                'bg_code': user[3] or 'KURO0001',
                'div_code': user[4] or 'KURO0001_001',
                'branch_code': user[5] or 'KURO0001_001_001',
                'source': 'legacy'
            }
    
    print(f"Total unique walk-ins: {len(all_users)}")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for i, (phone, user) in enumerate(all_users.items()):
        try:
            # Generate identity_id from phone
            # Use format: REB{first8chars_of_phone}_{hash}
            phone_hash = hashlib.md5(phone.encode()).hexdigest()[:8]
            identity_id = f"REB{phone[:8]}_{phone_hash}"
            
            # Check if identity already exists
            new_cursor.execute("SELECT identity_id FROM users_identity WHERE identity_id = %s", (identity_id,))
            if new_cursor.fetchone():
                print(f"  Skipping {phone}: identity already exists")
                skipped += 1
                continue
            
            # Check if phone already exists in system
            new_cursor.execute("""
                SELECT identity_id FROM users_identity 
                WHERE phone = %s AND bg_code = %s
            """, (phone, user['bg_code']))
            existing = new_cursor.fetchone()
            
            if existing:
                print(f"  Skipping {phone}: phone already exists as {existing[0]}")
                skipped += 1
                continue
            
            # Create Identity for walk-in customer
            new_cursor.execute("""
                INSERT INTO users_identity (identity_id, phone, name, email, bg_code, div_code, branch_code, status, phone_verified, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', false, %s, %s)
                RETURNING identity_id
            """, (
                identity_id,
                phone,
                user['name'],
                user['email'],
                user['bg_code'],
                user['div_code'],
                user['branch_code'],
                'active',
                datetime.now(),
                datetime.now(),
            ))
            
            result = new_cursor.fetchone()
            new_identity_id = result[0]
            
            # Create Walk-in record
            new_cursor.execute("""
                INSERT INTO caf_platform_walkins (identity_id, created_at, updated_at)
                VALUES (%s, %s, %s)
            """, (
                new_identity_id,
                datetime.now(),
                datetime.now(),
            ))
            
            migrated += 1
            
            # Progress indicator
            if (i + 1) % 500 == 0:
                print(f"  Processed {i + 1}/{len(all_users)}...")
            
        except Exception as e:
            print(f"Error migrating {phone}: {e}")
            errors += 1
            continue
    
    legacy_cursor.close()
    legacy_conn.close()
    new_cursor.close()
    new_conn.close()
    mongo_client.close()
    
    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total: {len(all_users)}")

if __name__ == '__main__':
    migrate_walkins()
```

#### Step 2: Execute Migration

```bash
python3 /tmp/migrate_walkins.py
```

#### Step 3: Validate Migration

```sql
-- Check walk-in count
SELECT COUNT(*) FROM caf_platform_walkins;

-- Check identity count for walk-ins
SELECT COUNT(*) FROM users_identity 
WHERE identity_id LIKE 'REB%';

-- Verify walk-in details
SELECT i.identity_id, i.phone, i.name, i.bg_code, i.div_code, i.branch_code
FROM users_identity i
JOIN caf_platform_walkins w ON i.identity_id = w.identity_id
LIMIT 10;
```

---

## Migration 3: eShop Users

### Source Schema

**Legacy Table:** `kg_eshop_latest.users_customuser` (2,468 records)

| Field | Type | Notes |
|-------|------|-------|
| `userid` | varchar | User ID (phone number) |
| `name` | varchar | User name |
| `phone` | varchar | Phone number |
| `email` | varchar | Email address |
| `is_active` | boolean | Active status |
| `last_login` | timestamp | Last login time |

### Target Schema

**Target Table:** `users_identity`

```sql
-- users_identity (core identity)
identity_id CHAR(20) PRIMARY KEY,
phone VARCHAR(20),
name VARCHAR(255),
email VARCHAR(255),
bg_code VARCHAR(20),
div_code VARCHAR(20),
branch_code VARCHAR(20),
status VARCHAR(20),
phone_verified BOOLEAN,
created_at TIMESTAMP,
updated_at TIMESTAMP
```

### Migration Steps

#### Step 1: Restore Legacy Database

```bash
# Download latest backup from S3
aws s3 cp s3://kuro-db-backup/kg-backup/default-ip-172-31-26-151-2026-06-30-153005.psql.bin /tmp/kg_eshop_latest.psql.bin

# Restore to temporary database
pg_restore --dbname=kg_eshop_latest /tmp/kg_eshop_latest.psql.bin
```

#### Step 2: Create Migration Script

**Script:** `/tmp/migrate_eshop_users.py`

```python
#!/usr/bin/env python3
"""
Migrate eShop users from legacy kuro-gaming-dj-backend to new system.

Maps: users_customuser → users_identity (as customers).
These are eShop customers, not walk-ins.
"""
import psycopg2
from datetime import datetime

def migrate_eshop_users():
    """Migrate eShop users to new system."""
    # Connect to legacy database
    legacy_conn = psycopg2.connect(dbname='kg_eshop_latest', user='postgres')
    legacy_cursor = legacy_conn.cursor()
    
    # Connect to new database
    new_conn = psycopg2.connect(dbname='kuro-cadence', user='postgres')
    new_conn.autocommit = True
    new_cursor = new_conn.cursor()
    
    # Get all eShop users
    legacy_cursor.execute("""
        SELECT userid, name, phone, email, is_active, last_login
        FROM users_customuser
        ORDER BY userid
    """)
    users = legacy_cursor.fetchall()
    print(f"Found {len(users)} eShop users to migrate")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    for i, user in enumerate(users):
        try:
            userid, name, phone, email, is_active, last_login = user
            
            # Generate identity_id from userid (phone number)
            identity_id = f"ESH{userid}"
            
            # Check if identity already exists
            new_cursor.execute("SELECT identity_id FROM users_identity WHERE identity_id = %s", (identity_id,))
            if new_cursor.fetchone():
                skipped += 1
                continue
            
            # Check if phone already exists in system
            new_cursor.execute("""
                SELECT identity_id FROM users_identity 
                WHERE phone = %s AND bg_code = 'KURO0001'
            """, (phone or '',))
            existing = new_cursor.fetchone()
            
            if existing:
                # Phone already exists, skip to avoid duplicate
                print(f"  Skipping {userid}: phone {phone} already exists as {existing[0]}")
                skipped += 1
                continue
            
            # Create Identity for eShop customer
            new_cursor.execute("""
                INSERT INTO users_identity (identity_id, phone, name, email, bg_code, div_code, branch_code, status, phone_verified, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', false, %s, %s)
                RETURNING identity_id
            """, (
                str(identity_id),
                str(phone or ''),
                str(name or ''),
                str(email or ''),
                'KURO0001',
                'KURO0001_001',
                'KURO0001_001_001',
                'active',
                str(last_login) if last_login else datetime.now().isoformat(),
                datetime.now().isoformat(),
            ))
            
            result = new_cursor.fetchone()
            new_identity_id = result[0]
            
            migrated += 1
            
            # Progress indicator
            if (i + 1) % 500 == 0:
                print(f"  Processed {i + 1}/{len(users)}...")
            
        except Exception as e:
            print(f"Error migrating {userid}: {e}")
            errors += 1
            continue
    
    legacy_cursor.close()
    legacy_conn.close()
    new_cursor.close()
    new_conn.close()
    
    print(f"\nMigration complete:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total: {len(users)}")

if __name__ == '__main__':
    migrate_eshop_users()
```

#### Step 3: Execute Migration

```bash
python3 /tmp/migrate_eshop_users.py
```

#### Step 4: Validate Migration

```sql
-- Check eShop user count
SELECT COUNT(*) FROM users_identity 
WHERE identity_id LIKE 'ESH%';

-- Verify eShop user details
SELECT identity_id, phone, name, email, bg_code, div_code, branch_code
FROM users_identity
WHERE identity_id LIKE 'ESH%'
LIMIT 10;
```

---

## Validation & Verification

### Cross-Reference Checks

```sql
-- Total identity count by type
SELECT 
    CASE 
        WHEN identity_id LIKE 'ID%' THEN 'ID (legacy)'
        WHEN identity_id LIKE 'ESH%' THEN 'ESH (eShop)'
        WHEN identity_id LIKE 'REB%' THEN 'REB (walk-in)'
        WHEN identity_id LIKE 'KUP%' THEN 'KUP (kuro purchase)'
        WHEN identity_id LIKE 'K%' THEN 'Employees (K*)'
        ELSE 'Other'
    END as category,
    COUNT(*) as count
FROM users_identity
GROUP BY category
ORDER BY category;

-- Walk-in count by branch
SELECT 
    i.branch_code,
    COUNT(*) as walkin_count
FROM users_identity i
JOIN caf_platform_walkins w ON i.identity_id = w.identity_id
GROUP BY i.branch_code
ORDER BY walkin_count DESC;

-- Employee count by department
SELECT 
    e.department,
    COUNT(*) as employee_count
FROM users_identity i
JOIN users_employee e ON i.identity_id = e.identity_id
GROUP BY e.department
ORDER BY employee_count DESC;
```

### Data Integrity Checks

```sql
-- Check for orphaned walk-ins (no identity)
SELECT COUNT(*) FROM caf_platform_walkins w
LEFT JOIN users_identity i ON w.identity_id = i.identity_id
WHERE i.identity_id IS NULL;

-- Check for orphaned employees (no identity)
SELECT COUNT(*) FROM users_employee e
LEFT JOIN users_identity i ON e.identity_id = i.identity_id
WHERE i.identity_id IS NULL;

-- Check for duplicate phones
SELECT phone, COUNT(*) as count
FROM users_identity
WHERE phone != ''
GROUP BY phone
HAVING COUNT(*) > 1;
```

---

## Rollback Procedure

If migration fails or produces incorrect results:

```sql
-- Delete eShop users
DELETE FROM users_identity WHERE identity_id LIKE 'ESH%';

-- Delete walk-ins
DELETE FROM caf_platform_walkins WHERE identity_id LIKE 'REB%' OR identity_id LIKE 'KUP%';
DELETE FROM users_identity WHERE identity_id LIKE 'REB%' OR identity_id LIKE 'KUP%';

-- Delete employees
DELETE FROM users_employee WHERE identity_id LIKE 'K%';
DELETE FROM users_identity WHERE identity_id LIKE 'K%';
```

---

## Migration Scripts Reference

| Script | Purpose | Location |
|--------|---------|----------|
| `migrate_employees.py` | Migrate employees from legacy_dump | `/tmp/migrate_employees.py` |
| `migrate_walkins.py` | Migrate walk-ins from MongoDB | `/tmp/migrate_walkins.py` |
| `migrate_eshop_users.py` | Migrate eShop users from kg_eshop_latest | `/tmp/migrate_eshop_users.py` |

---

## Notes & Considerations

1. **Identity ID Format:**
   - Employees: `K{userid}` (e.g., `KAD001`, `KTM003`)
   - Walk-ins: `REB{first8chars_of_phone}_{hash}` (e.g., `REB09876543_a1b2c3d4`)
   - eShop: `ESH{userid}` (e.g., `ESH8168371280`)

2. **Phone Number Conflicts:**
   - If a phone number already exists in the system, the new record is skipped
   - This prevents duplicate identities

3. **Branch/Division Assignment:**
   - Employees: Assigned to `KURO0001_001` (division) and `KURO0001_001_001` (branch)
   - Walk-ins: Assigned based on source (Madhapur or LB Nagar)
   - eShop: Assigned to `KURO0001_001` (division) and `KURO0001_001_001` (branch)

4. **Status:**
   - All migrated records are set to `active` status
   - `phone_verified` is set to `false` (no OTP verification in legacy data)

5. **Email:**
   - Employee emails are not available in legacy data
   - Walk-in emails are preserved from MongoDB
   - eShop emails are preserved from legacy database

---

## Next Steps

After migration:

1. **Update Application Code:**
   - Update ViewSets to read from `users_identity` instead of `CustomUser`, `reb_users`, etc.
   - Update wallet and session management to use `identity_id` instead of `phone`

2. **Create Indexes:**
   ```sql
   CREATE UNIQUE INDEX uq_identity_tenant_phone ON users_identity (bg_code, phone);
   CREATE INDEX idx_identity_tenant ON users_identity (bg_code, div_code);
   CREATE INDEX idx_identity_email ON users_identity (email);
   CREATE INDEX idx_identity_status ON users_identity (status);
   ```

3. **Update Foreign Keys:**
   - Update `caf_platform_wallets` FK from `CustomUser` to `users_identity`
   - Update `caf_platform_sessions` FK from `CustomUser` to `users_identity`

4. **Deprecate Legacy Tables:**
   - Archive `users_customuser` (CustomUser)
   - Archive `users_kurouser` (employees)
   - Archive `reb_users` (MongoDB walk-ins)

---

## Appendix: Legacy Schema Reference

### users_customuser (Django Auth Model)

| Field | Type | Notes |
|-------|------|-------|
| `userid` | varchar(20) | Primary key, USERNAME_FIELD |
| `name` | varchar(255) | Display name |
| `phone` | varchar(20) | Phone number, UNIQUE |
| `email` | varchar(255) | Email address |
| `is_active` | boolean | Account status |
| `created_date` | timestamp | Account creation date |
| `last_login` | timestamp | Last login time |

### users_kurouser (Employee Profile)

| Field | Type | Notes |
|-------|------|-------|
| `userid` | varchar(20) | Primary key |
| `role` | varchar(50) | Role type |
| `primary_bg` | varchar(20) | Primary business group |
| `joining_date` | date | Employment start date |
| `gender` | varchar(10) | Gender |
| `dob` | date | Date of birth |
| `phone` | varchar(20) | Phone number |
| `salary` | numeric(10,2) | Salary amount |
| `pan` | varchar(20) | PAN number |
| `bank_name` | varchar(100) | Bank name |
| `bank_ac_no` | varchar(50) | Bank account number |
| `ifsc_code` | varchar(20) | IFSC code |
| `address` | text | Address |
| `emergency_contact` | text | Emergency contact details |

### reb_users (MongoDB Walk-in)

| Field | Type | Notes |
|-------|------|-------|
| `_id` | ObjectId | MongoDB document ID |
| `phone` | string | Phone number |
| `name` | string | Customer name |
| `email` | string | Email address |
| `bg_code` | string | Business group code |
| `div_code` | string | Division code |
| `branch_code` | string | Branch code |
