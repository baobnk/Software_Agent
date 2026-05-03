# Library Book Management System (MVP)

**Source:** internal product brief
**Analyzed:** 2026-04-29

## 1. Bài toán

A small public library currently tracks books and borrowing on paper. They
need a web app for staff to manage the catalog and member borrowings, plus
a public search page for patrons.

- Current state: paper logs, no central catalog
- Target state: web app with login for staff + public read-only search

## 2. Business Cases

### Business Case 1: Catalog management
- Bối cảnh: 5,000+ books, growing 200/month
- Mục tiêu: digitize catalog, auto-generate barcode labels
- Kết quả: search by title / author / ISBN in <1s

### Business Case 2: Borrowing tracking
- Bối cảnh: 800 members, ~150 transactions/week
- Mục tiêu: track who has which book, due dates, overdue list

### Business Case 3: Public search
- Bối cảnh: patrons want to check availability before visiting
- Mục tiêu: public page (no login) for catalog browse + availability

## 3. Functional Requirements (draft)

| ID  | Name | Priority | Description |
|-----|------|----------|-------------|
| FR1 | Catalog CRUD | Critical | Staff add/edit/delete books with metadata |
| FR2 | Borrow / Return | Critical | Staff record borrow + return with due dates |
| FR3 | Public Search | High | Patrons search catalog without login |
| FR4 | Overdue Report | Medium | Daily report of overdue items |

## 4. Non-Functional Requirements

| Category | Metric | Target |
|----------|--------|--------|
| Performance | Search response | ≤ 500 ms |
| Availability | Uptime | ≥ 99 % business hours |
| Security | Staff auth | OAuth2 + role-based |
| Scalability | Concurrent users | ≥ 30 |

## 5. Stakeholders

- Library Director — sponsor, signs off
- Head Librarian — primary user, BA contact
- 4 staff librarians — daily users
- IT volunteer — deployment support

## 6. Constraints

- On-prem deployment (small Linux server)
- Budget cap: 25 man-days
- 3-month timeline for MVP
