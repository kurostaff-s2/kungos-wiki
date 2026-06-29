# Accounts Domain Spec

**Status:** Active — 47/55 endpoints migrated to ViewSets (85% complete)  
**Base Path:** `/api/v1/accounts/`  
**Last Updated:** 2026-06-29  

---

## Overview

The Accounts domain provides RESTful endpoints for all financial operations including invoices, payments, purchase orders, credit/debit notes, financial reports, and settlements.

---

## Modules

### 1. Inward Invoices (Purchase Invoices)

**Endpoint:** `/api/v1/accounts/inward-invoices`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all inward invoices |
| POST | create | Create new inward invoice |
| GET | retrieve | Get invoice by ID (`/inward-invoices/<pk>`) |
| PATCH | update | Update invoice (`/inward-invoices/<pk>`) |
| DELETE | destroy | Delete invoice (`/inward-invoices/<pk>`) |

**ViewSet:** `InwardInvoiceViewSet`  
**Status:** ✅ Migrated

---

### 2. Outward Invoices (Sales Invoices)

**Endpoint:** `/api/v1/accounts/outward-invoices`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all outward invoices |
| POST | create | Create new outward invoice |
| GET | retrieve | Get invoice by ID (`/outward-invoices/<pk>`) |
| PATCH | update | Update invoice (`/outward-invoices/<pk>`) |
| DELETE | destroy | Delete invoice (`/outward-invoices/<pk>`) |

**ViewSet:** `OutwardInvoiceViewSet`  
**Status:** ✅ Migrated

---

### 3. Inward Payments (Purchase Payments)

**Endpoint:** `/api/v1/accounts/inward-payments`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all inward payments |
| POST | create | Create new inward payment |
| GET | retrieve | Get payment by ID (`/inward-payments/<pk>`) |
| PATCH | update | Update payment (`/inward-payments/<pk>`) |
| DELETE | destroy | Delete payment (`/inward-payments/<pk>`) |

**ViewSet:** `InwardPaymentViewSet`  
**Status:** ✅ Migrated

---

### 4. Outward Payments (Sales Payments)

**Endpoint:** `/api/v1/accounts/outward-payments`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all outward payments |
| POST | create | Create new outward payment |
| GET | retrieve | Get payment by ID (`/outward-payments/<pk>`) |
| PATCH | update | Update payment (`/outward-payments/<pk>`) |
| DELETE | destroy | Delete payment (`/outward-payments/<pk>`) |

**ViewSet:** `OutwardPaymentViewSet`  
**Status:** ✅ Migrated

---

### 5. Payment Vouchers

**Endpoint:** `/api/v1/accounts/payment-vouchers`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all payment vouchers |
| POST | create | Create new payment voucher |
| GET | retrieve | Get voucher by ID (`/payment-vouchers/<pk>`) |
| PATCH | update | Update voucher (`/payment-vouchers/<pk>`) |
| DELETE | destroy | Delete voucher (`/payment-vouchers/<pk>`) |

**ViewSet:** `PaymentVoucherViewSet`  
**Status:** ✅ Migrated

---

### 6. Purchase Orders

**Endpoint:** `/api/v1/accounts/purchase-orders`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all purchase orders |
| POST | create | Create new purchase order |
| GET | retrieve | Get order by ID (`/purchase-orders/<pk>`) |
| PATCH | update | Update order (`/purchase-orders/<pk>`) |
| DELETE | destroy | Delete order (`/purchase-orders/<pk>`) |

**ViewSet:** `PurchaseOrderViewSet`  
**Status:** ✅ Migrated

---

### 7. Credit/Debit Notes

#### Outward Credit Notes (Business Issues)
**Endpoint:** `/api/v1/accounts/outward-credit-notes`  
**ViewSet:** `OutwardCreditNoteViewSet`  
**Status:** ✅ Migrated

#### Outward Debit Notes (Business Issues)
**Endpoint:** `/api/v1/accounts/outward-debit-notes`  
**ViewSet:** `OutwardDebitNoteViewSet`  
**Status:** ✅ Migrated

#### Inward Credit Notes (Vendor Issues)
**Endpoint:** `/api/v1/accounts/inward-credit-notes`  
**ViewSet:** `InwardCreditNoteViewSet`  
**Status:** ✅ Migrated

#### Inward Debit Notes (Vendor Issues)
**Endpoint:** `/api/v1/accounts/inward-debit-notes`  
**ViewSet:** `InwardDebitNoteViewSet`  
**Status:** ✅ Migrated

---

### 8. Accounts (Sundry Creditors/Debtors, Banks, Partners, Loans)

**Endpoint:** `/api/v1/accounts/accounts`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all accounts |
| POST | create | Create new account |
| PATCH | update | Update account (`/accounts/<pk>`) |

**ViewSet:** `AccountsViewSet`  
**Status:** ✅ Migrated

---

### 9. Financial Reports

#### Financials
**Endpoint:** `/api/v1/accounts/financials`  
**ViewSet:** `FinancialsViewSet`  
**Status:** ✅ Migrated

#### ITC & GST
**Endpoint:** `/api/v1/accounts/itc-gst`  
**ViewSet:** `ITCGSTViewSet`  
**Status:** ✅ Migrated

#### Revenue
**Endpoint:** `/api/v1/accounts/revenue`  
**ViewSet:** `RevenueViewSet`  
**Status:** ✅ Migrated

#### Expenditure
**Endpoint:** `/api/v1/accounts/expenditure`  
**ViewSet:** `ExpenditureViewSet`  
**Status:** ✅ Migrated

#### Profit & Loss
**Endpoint:** `/api/v1/accounts/profit-loss`  
**ViewSet:** `ProfitLossViewSet`  
**Status:** ✅ Migrated

#### Balance Sheet
**Endpoint:** `/api/v1/accounts/balance-sheet`  
**ViewSet:** `BalanceSheetViewSet`  
**Status:** ✅ Migrated

---

### 10. Bulk Payments

**Endpoint:** `/api/v1/accounts/bulk-payments`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List bulk payment batches |
| POST | create | Create bulk payment batch |

**ViewSet:** `BulkPaymentViewSet`  
**Status:** ✅ Migrated

---

### 11. Analytics

**Endpoint:** `/api/v1/accounts/analytics`  
**ViewSet:** `AnalyticsViewSet`  
**Status:** ✅ Migrated

---

### 12. Settlements

**Endpoint:** `/api/v1/accounts/settlements`

| Method | Action | Description |
|--------|--------|-------------|
| GET | list | List all settlements |
| POST | create | Create new settlement |

**ViewSet:** `SettlementsViewSet`  
**Status:** ✅ Migrated

---

### 13. Exports

**Endpoint:** `/api/v1/accounts/export`

| Method | Action | Description |
|--------|--------|-------------|
| GET | export_data | Export data (generic) |
| GET | export_inward_invoices | Export inward invoices |
| GET | export_outward_invoices | Export outward invoices |
| GET | export_inward_payments | Export inward payments |

**ViewSet:** `ExportViewSet`  
**Status:** ✅ Migrated

**Aliases:** Frontend can call `accounts/inward-invoices` with `exportType` param directly.

---

## Migration Status

| Module | Status | Notes |
|--------|--------|-------|
| Inward Invoices | ✅ Complete | Full CRUD |
| Outward Invoices | ✅ Complete | Full CRUD |
| Inward Payments | ✅ Complete | Full CRUD |
| Outward Payments | ✅ Complete | Full CRUD |
| Payment Vouchers | ✅ Complete | Full CRUD |
| Purchase Orders | ✅ Complete | Full CRUD |
| Credit/Debit Notes | ✅ Complete | 4 ViewSets (outward/inward × credit/debit) |
| Accounts | ✅ Complete | Sundry creditors/debtors, banks, partners, loans |
| Financial Reports | ✅ Complete | 6 report endpoints |
| Bulk Payments | ✅ Complete | Batch processing |
| Analytics | ✅ Complete | Financial analytics |
| Settlements | ✅ Complete | Settlement management |
| Exports | ✅ Complete | CSV/PDF exports |
| Legacy (teams/financial.py) | ⏳ Pending | Must be fully migrated |

**Overall:** 47/55 endpoints migrated (85% complete)

---

## Data Models

### Invoice Models
- `InwardInvoice` — Purchase invoices
- `OutwardInvoice` — Sales invoices

### Payment Models
- `InwardPayment` — Purchase payments
- `OutwardPayment` — Sales payments
- `PaymentVoucher` — Payment vouchers

### Order Models
- `PurchaseOrder` — Purchase orders

### Note Models
- `OutwardCreditNote` — Credit notes issued
- `OutwardDebitNote` — Debit notes issued
- `InwardCreditNote` — Credit notes received
- `InwardDebitNote` — Debit notes received

### Account Models
- `SundryCreditor` — Sundry creditors
- `SundryDebtor` — Sundry debtors
- `Bank` — Bank accounts
- `Partner` — Business partners
- `Loan` — Loans

### Report Models
- `FinancialPosition` — Financial position aggregation
- `ITCGST` — Input Tax Credit & GST
- `Revenue` — Sales/revenue
- `Expenditure` — Purchase/expenditure
- `ProfitLoss` — Profit & loss statement
- `BalanceSheet` — Balance sheet

---

## Error Handling

All endpoints follow the standard API error format (see `endpoint_contract_spec.md` §8.2):

```json
{
  "status": "error",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {}
  }
}
```

---

## Authentication

All endpoints require authentication via HttpOnly JWT cookie (`jwt_token`).

---

## Multi-Tenancy

All endpoints are scoped to the active business group via `bg_code` in the JWT token.

---

## References

- **URL Configuration:** `domains/accounts/urls.py`
- **ViewSets:** `domains/accounts/viewsets.py`
- **Services:** `domains/accounts/services.py`
- **Financials:** `domains/accounts/financials/`
- **Expenditure:** `domains/accounts/expenditure/`
- **Sales:** `domains/accounts/sales/`
- **Tax:** `domains/accounts/tax/`

---

**Document Status:** Active — Created 2026-06-29 to fill gap identified in frontend alignment handoff (RF-7)
