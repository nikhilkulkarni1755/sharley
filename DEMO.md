# Demo (60 seconds) and judge playground

## The "aha" in one sentence
Sharley reads a plain-English spec (even a photo of a whiteboard), writes tests the implementer never sees, and catches
bugs a human missed: a payments API that lets one payment be refunded twice and accepts forged `alg: none` tokens, and a
billing system where 3 of 12 houses silently get free electricity.

## Video beats (aim 60s)
1. (0-10s) Camera/Intake tab: snap or drop the whiteboard sketch of the electricity system -> requirements appear with
   observed / inferred badges and coverage 100%.
2. (10-20s) Playground: the code is the real flawed backend. "12 tests you can see, 40 sealed tests you cannot."
3. (20-35s) Run sealed tests -> tiles flip -> **Wrong Answer on sealed test 1 of 40: ... billed cents equals kWh x 12 or 18**.
   Say: "3 houses have been getting free power; the team's own tests never touched them."
4. (35-50s) Edit one line (tariff lookup), Run again -> **Accepted**, 40/40 green. (Fix: normalise the tariff code and fail
   loudly when unknown.)
5. (50-60s) Eval tab: held-out mutation score, the version timeline with a rolled-back skill change. Close on: "independent
   verifier, different model family than the implementer, hidden tests, self-improving."

## Judge playground (what they can do on the link)
- Pick Payments or Electricity, read the spec, edit the code, press **Run sealed tests**; verdict in ~2 s, no model cost.
- Hint to share if they get stuck: Payments -> "look at refunds and at token verification"; Electricity -> "look at how the
  rate is looked up". Reset code restores the original.
- Paid features (spec/bank generation from your own text) are off on the public link; replay mode shows a recorded run.

## Run it yourself
`sharley serve` (local), `deploy/quick-demo.sh` (public link via Cloudflare quick tunnels), or `DEPLOYMENT.md` for production.
