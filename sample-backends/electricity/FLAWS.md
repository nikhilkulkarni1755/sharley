# Planted flaw (ground truth for evaluating Sharley; never shown to the test writer)

**FLAW-FREE-POWER:** tariff lookup is `TARIFFS.get(code, 0.0)`. Three houses were typed in with variant codes
(`H003` = `res-b`, `H006` = `RES-B ` with a trailing space, `H009` = `RES_B`), so they miss the lookup and are billed
**0** for ~15% of the customer base. The existing tests (`tests/test_basic.py`) only use clean codes (H001/H002), so
nothing caught it. Spec: "Every house that uses electricity must be billed; ... never billed zero silently."
Fix: normalise the code (strip, upper, `_`->`-`) and fail loudly when it still does not match.
