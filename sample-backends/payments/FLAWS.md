# Planted flaws (ground truth for evaluating Sharley; never shown to the test writer)

1. **FLAW-LOGIC (business logic):** `POST /payments/{id}/refund` never records that a payment was refunded, so the payee's
   money can be returned to the payer any number of times (money creation). Spec: "A payment can be refunded only once."
2. **FLAW-CVE (CVE class: JWT `alg: none` acceptance, cf. CVE-2015-9235 / CVE-2018-1000531):** the hand-rolled token
   verifier skips the signature check when the header says `alg: none`, so anyone can forge a token for any principal,
   including `role: admin`. Spec: "unsigned or tampered tokens must be rejected."

`flaws.json` lists the exact line edits that produce the fixed twin used to measure false failures.
Note: this is a CVE *class* reproduced in code, not a vulnerable third-party package.
