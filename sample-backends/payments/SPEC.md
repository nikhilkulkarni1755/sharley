Payments API for people and for AI agents that spend on their behalf. Anyone can sign up as a user with a name; the
signup response gives an id, an account id and a secret, and the secret plus the id is exchanged for a signed bearer
token. A user can create agents; each agent has its own account and a per-payment limit that its owner sets, and an
agent can never pay more than that limit in one payment. Agents cannot create other agents. Money is in integer cents.
Users (and the admin) can deposit into their own accounts and the accounts of their agents, and nobody can touch
another person's account. A payment moves money from the caller's account to another account, needs an idempotency
key so retrying the same request never charges twice, fails if the balance is too low, and cannot be zero, negative
or to yourself. People can look at payments they sent or received, nobody else. The person who was paid can refund a
payment, which returns the money to the payer. A payment can be refunded only once and never for more than it was
worth. Agents cannot issue refunds. Every request except signup, token and health needs a valid signed token; unsigned
or tampered tokens must be rejected. Errors must not leak internals. GET /health returns 200.
