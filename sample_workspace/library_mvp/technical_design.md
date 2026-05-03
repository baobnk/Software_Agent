# Technical Design — Library MVP

## 1. Problem Confirmation
Replace paper-based library tracking with a small web app. Public search +
staff CRUD + borrowing tracker. On-prem, low budget.

## 2. Approach
**Recommended:** monolithic web app (Flask + SQLite + simple HTML/HTMX UI).
- Pros: minimal infra, easy to deploy, cheap to maintain
- Cons: limited scale (fine for 800 members)

## 3. Architecture
- Single Flask app on a Linux VM
- SQLite database (file-based)
- HTMX for interactive UI without heavy JS
- Nginx reverse proxy + Let's Encrypt
- Daily SQLite backup via cron

## 4. Module Decomposition

| Module | Sub-modules | FR Coverage | Complexity |
|--------|-------------|-------------|------------|
| Auth | login, role | (cross-cutting) | Low |
| Catalog | book CRUD, ISBN lookup | FR1, FR3 | Low |
| Circulation | borrow, return, overdue | FR2, FR4 | Medium |
| Public UI | search, availability | FR3 | Low |
| Admin Reports | overdue report, exports | FR4 | Low |

## 5. Tech Stack
- Backend: Python 3.12 + Flask 3.0
- DB: SQLite (single-file, with WAL)
- Frontend: HTMX + Tailwind CSS
- Auth: Flask-Login + bcrypt
- Deployment: systemd + nginx

## 6. Integration Design
None — fully self-contained. Optional ISBN lookup via OpenLibrary public API.

## 7. Scope

### In Scope
- Catalog CRUD (FR1)
- Borrow/Return tracking (FR2)
- Public search page (FR3)
- Overdue report (FR4)
- Staff login + 2 roles (admin, librarian)

### Out of Scope
- Mobile app
- Reservations / holds
- Fine collection / payment
- Patron self-service portal

## 8. Estimation Assumptions

- 1 BE developer + 0.3 FE allocation (HTMX is lightweight)
- ISBN dataset is OpenLibrary (free)
- Existing VM available (no infra cost)

## 9. Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| HTMX learning curve for team | Medium | Low | 2-day spike before sprint 1 |
| OpenLibrary API rate limits | Low | Low | Local cache table |
| Backup not tested | Medium | High | Test restore weekly in dev |
