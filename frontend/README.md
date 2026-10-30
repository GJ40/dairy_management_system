# Dairy Management System — frontend

React 19 + Vite single-page app with two experiences in one bundle:

- **Staff app** (`/login`, `/dashboard`, `/buffaloes`, `/production`, `/stock`,
  `/customers`, `/customer-orders`, `/customer-queries`, `/sales`, `/invoices`,
  `/reports`, `/portal-accounts`, `/users`, `/expenses`) — the existing dairy
  operations UI plus the customer-order and customer-query queues.
- **Customer portal** (`/portal/login`, `/portal/activate`, `/portal`,
  `/portal/orders`, `/portal/invoices`, `/portal/queries`, `/portal/profile`) —
  customers only; staff routes are unchanged.

## Setup

```powershell
Set-Location -LiteralPath 'D:\Projects\dairy_management_system\frontend'
npm install
npm run dev        # Vite dev server, defaults to http://localhost:5173
```

The API defaults to `http://localhost:8000/api/v1`. Override it, and the two
non-secret session-hint cookie names, with a local `.env` (names only — never commit
values):

```ini
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_SESSION_HINT_COOKIE=dairy_session
VITE_CUSTOMER_SESSION_HINT_COOKIE=dairy_customer_session
```

Both clients send `withCredentials: true`: the access token is held in memory only and
the refresh token lives in an httpOnly cookie, so the browser talks to the API directly
(CORS is configured on the backend for this origin).

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Production bundle into `dist/` |
| `npm run preview` | Serve the built bundle locally |
| `npm run lint` | ESLint (flat config, React Hooks + React Compiler rules) |

There is no frontend test runner; `npm run lint` and `npm run build` are the gates.
Last verified 2026-10-30: lint exit 0, build exit 0 (2077 modules, ~7 s, JS 685 kB /
176 kB gzip, only the pre-existing >500 kB chunk-size warning).

## Notes

- Staff and customer sessions are completely separate: `src/api/client.js` and
  `src/api/customerClient.js`, each with its own in-memory token, single-flight refresh
  and 401 handling.
- Dates are rendered in `Asia/Kolkata`; money and litres come from the API as
  two-decimal strings and are formatted, never re-rounded, in the UI.
