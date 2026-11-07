Electricity management system for a small utility. Operators load monthly meter readings for each house, and the system
turns the difference between two months into kWh used and bills it at the house's tariff rate: residential A is 12 cents
per kWh, residential B is 18 cents and commercial A is 25 cents. Every house that uses electricity must be billed; a house
with a tariff the system does not understand must never be billed zero silently, it should be billed correctly or the
request should fail loudly. Readings are cumulative so a new reading can never be lower than the previous one, only one
reading per house per month is allowed, and months look like 2026-02. Operators can list houses, add readings, run
billing for a month, and get a summary that includes the total and any house that used power but was not charged. A
customer uses their own house key and can only see their own house and bill, never another house. Operators use the
operator key; everything except the health check needs a key. Bad input must give a clear error, not a crash.
GET /health returns 200.
