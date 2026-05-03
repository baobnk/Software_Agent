# SKILL: WBS Estimation

## Purpose
Decompose BRD Functional Requirements into a 4-level Work Breakdown Structure
following BnK Solution's standard template and estimation heuristics.

## Hierarchy Reference

```
L1 — Phase        I, II, III            No effort (rollup)
L2 — Sub-phase    I.A, I.B, II.A        No effort (rollup)
L3 — Module       I.A.1, I.A.2          No effort (rollup)
L4 — Task         REQ-01, BE-01, FE-01  HAS md_be and/or md_fe
```

## Standard BnK Phase Template

```
I. Project Setup & Requirements
   I.A. Project initiation
     I.A.1. Kickoff & environment setup
       SETUP-01  Development environment         BE:0.5  FE:0.5
       SETUP-02  CI/CD pipeline setup            BE:1.0  FE:0.0
     I.A.2. Architecture design
       ARC-01    System architecture document    BE:2.0  FE:1.0
   I.B. Requirement finalization
     I.B.1. BRD review & sign-off
       REQ-01    Requirements workshop           BE:0.5  FE:0.5
       REQ-02    BRD finalization                BE:1.0  FE:0.0

II. Development
   II.A. [FR1 Module Name]
     II.A.1. Backend
       BE-01     [Task name]                     BE:X.X  FE:0.0
     II.A.2. Frontend
       FE-01     [Task name]                     BE:0.0  FE:X.X
   II.B. [FR2 Module Name]
     ...

III. Testing & Deployment
   III.A. System testing & QA
     III.A.1. Test execution
       QC-01     Test case writing               BE:0.5  FE:0.5
       QC-02     System test execution           BE:1.0  FE:1.0
   III.B. UAT & bug fixing
     III.B.1. UAT support
       UAT-01    UAT session facilitation        BE:1.0  FE:0.5
       UAT-02    Bug fixing                      BE:2.0  FE:1.0
   III.C. Deployment
     III.C.1. Production deployment
       DEP-01    Production deployment           BE:1.0  FE:0.5
       DEP-02    Post-deployment monitoring      BE:0.5  FE:0.0
       DEP-03    Knowledge transfer & handover   BE:1.0  FE:1.0
```

## Effort Estimation Heuristics (man-days)

| Feature Type                        | BE    | FE    |
|-------------------------------------|-------|-------|
| Simple CRUD (list + form)           | 1.0   | 1.5   |
| Complex form (multi-step, validation)| 1.5  | 2.5   |
| Authentication (login/register/reset)| 2.0  | 1.5   |
| Role-based access control (RBAC)    | 2.0   | 1.0   |
| Dashboard / chart page              | 1.0   | 2.5   |
| Analytical report (filter + export) | 2.0   | 2.0   |
| File upload / download              | 1.5   | 1.0   |
| Email / notification service        | 1.5   | 0.5   |
| 3rd party API integration           | 3.0   | 0.5   |
| Real-time (WebSocket / SSE)         | 2.0   | 2.0   |
| AI/ML inference endpoint            | 3.0   | 1.0   |
| AI/ML model training pipeline       | 5.0+  | 0.0   |
| Data migration script               | 2.0   | 0.0   |
| Search (full-text)                  | 1.5   | 1.0   |

## Auto-computed Roles (DO NOT set manually)
BA  = total_dev × pct_ba  (default 10%)
QC  = total_dev × pct_qc  (default 30%)
PM  = total_dev × pct_pm  (default 5%)

## Traceability Rule
Every L4 task in Phase II MUST have source_feature_id pointing to a real FR id.
Phase I (Setup) and Phase III (Testing/Deploy) tasks can omit source_feature_id.
