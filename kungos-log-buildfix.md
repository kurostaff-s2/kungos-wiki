## [2026-04-23] Navigation & Order Restructure — Build Error Fixes

### Issues resolved

**1. OutwardInvoice.jsx — DatePicker JSX + duplicate declarations**
- Fixed: `<DatePicker value={...}></td>` → `<DatePicker value={...} /></td>`
- Fixed: `const [invoiceData, setinvoiceData] = useState(null)` removed (duplicate with useQuery)
- Fixed: `const invoiceInfo = invoiceData` removed (duplicate with useState)
- Fixed: `setinvoiceData(data)` → `queryClient.invalidateQueries()` in mutation onSuccess
- Fixed: `setinvoiceInfo` → `setlocalInvoiceInfo` for editing state

**2. InwardPayment.jsx — Duplicate declarations**
- Fixed: `const [paymentData, setPaymentData] = useState(null)` → removed (duplicate with useQuery data: paymentData)
- Fixed: Duplicate `const [editPayment, setEditPayment] = useState(null)` removed

**3. GenerateInvoice.jsx — Duplicate banks declaration**
- Fixed: `const [banks, setbanks] = useState(null)` → `const [localBanks, setLocalBanks] = useState(null)`
- useQuery now uses `const { data: banks, isLoading } = useQuery(...)` as source of truth

**4. AuthenticatedRoute.jsx — Dead Switchgroup import**
- Removed: `import Switchgroup from '../../pages/Switchgroup'`
- Replaced: `<Switchgroup />` → `<Spinner />` fallback

**5. api.jsx — Circular store dependency**
- Removed: `import store from './store'`
- Added: Module-level `currentToken` variable with `setToken()` helper
- Fallback: Dynamic `require('@/store')` if module-level token not set

**6. AlertDialog.jsx — Missing Radix UI dependency**
- Replaced: `@radix-ui/react-alert-dialog` primitives with native React implementation
- No external dependencies required
- Full API compatibility (AlertDialog, Content, Header, Footer, Title, Description, Action, Cancel)

**7. main.jsx — 12 dead lazy imports referencing missing files**
Removed:
- `Profile` → `@/pages/Profile` (file doesn't exist)
- `Product` → `@/pages/Product` (file doesn't exist)
- `Estimate` → `@/pages/Estimate` (file doesn't exist)
- `PaymentVoucher` → `@/pages/PaymentVoucher` (file doesn't exist)
- `TPBuild` → `@/pages/TPBuild` (file doesn't exist)
- `Analytics` → `@/pages/Analytics` (file doesn't exist)
- `CreatePV` → `@/pages/CreatePV` (file doesn't exist)
- `OfflineOrders` → `@/pages/OfflineOrders` (file doesn't exist)
- `PreBuilts` → `@/pages/PreBuilts` (file doesn't exist)
- `PortalEditor` → `@/pages/PortalEditor` (file doesn't exist)
- `StockProd` → `@/pages/StockProd` (file doesn't exist)
- `Service` → `@/pages/Service` (file doesn't exist)

### Build status
- Before: 7 build errors
- After: ✓ Build passes (1.57s)
- Warning: `InwardPayment.jsx` dynamically and statically imported (cosmetic)

### Files changed
- `src/components/common/AuthenticatedRoute.jsx`
- `src/components/ui/AlertDialog.jsx`
- `src/lib/api.jsx`
- `src/pages/GenerateInvoice.jsx`
- `src/pages/InwardPayment.jsx`
- `src/pages/OutwardInvoice.jsx`
- `src/routes/main.jsx`
