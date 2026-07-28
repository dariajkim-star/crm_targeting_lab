"""Customer-facing marts: the committed contract surface (AD-2).

`marts/` is the ONE artifact tree this project commits (data/ and models/ are
gitignored). Everything here assembles a stable, audited frame from the upstream
lane outputs and owns nothing of the math - the math lives in crm.segment /
crm.churn / crm.campaign and is CONSUMED, never re-derived (AD-9, AD-11, AD-12).

Lane membership (AD-1): `crm.marts.customers` is judged Lane A (it assembles the
BankChurners segment/churn lane) and may never import `crm.ltv`. A future
`crm.marts.ltv` (story 4-2) would be Lane B; the two mart modules must not
import each other. The lane guard enforces this per registered MODULE - this
`__init__` itself is registered in NO lane (registering the `crm.marts` prefix
would drag the future ltv mart into Lane A), so it must stay import-free: a
convenience import here would bypass the lane guard entirely. A test asserts
this file contains no import statements (code review E5).
"""
