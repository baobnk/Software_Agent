# SKILL: BRD Generation

## Purpose
Generate a complete BRD (Business Requirements Document) conforming to the
BnK Solution BRD Template v1.0.

## BRD Section Map

| Section | Field in AST | Notes |
|---------|-------------|-------|
| 1. Introduction | purpose, scope, intended_use, abbreviations | |
| 2. General Description | user_needs, assumptions | |
| 3. Functional Requirements | functional_requirements[] | Each FR = one screen/feature |
| 4. External Interfaces | ui_notes, hardware, tech_stack, nfr | |
| Appendix | analysis_models, issues | Optional |

## FR Writing Standard

A good Functional Requirement has:
- **id**: FR1, FR2, … sequential, no gaps
- **name**: Noun phrase (e.g. "User Authentication", "Report Export")
- **priority**: Critical (blocks launch) / High (important) / Medium / Low / Future
- **short_description**: ≤ 20 words for the summary table
- **description**: 3-6 sentences covering:
  1. What the system does
  2. Who triggers it
  3. What data is involved
  4. What the output/result is
  5. Edge cases or exceptions (if notable)
- **interface_notes**: API endpoints, screens, data flows
- **data_fields**: List key input/output fields with types

## NFR Writing Standard

Every NFR row in performance/security/safety/quality MUST have:
- **aspect**: Short label (e.g. "API Response Time")
- **requirement**: What is required (e.g. "All API calls complete within threshold")
- **target**: Measurable value WITH unit (e.g. "p95 ≤ 500ms", "99.9% uptime", "AES-256")

## Common NFR Categories

**Performance**
- API response time: p95 ≤ 500ms for read, ≤ 2s for write
- Concurrent users: ≥ N users without degradation
- Report generation: ≤ 30s for large datasets

**Security**
- Authentication: JWT / OAuth 2.0
- Data encryption: AES-256 at rest, TLS 1.2+ in transit
- Session timeout: ≤ 30 minutes idle

**Quality**
- Unit test coverage: ≥ 80%
- Bug SLA: Critical ≤ 4h, Major ≤ 24h
- Uptime: 99.5% monthly

## Language Rules
- Vietnamese project → Vietnamese descriptions
- Technical terms (API, JWT, CRUD) stay in English regardless
- Never use marketing language ("powerful", "seamless", "cutting-edge")
