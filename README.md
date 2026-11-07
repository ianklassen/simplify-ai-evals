# Simplify AI Evals

A runnable example of tiered gating for AI output.

Put the model where the task is generative, not decisive. Let it move fast where a mistake is cheap and reversible. Put a human in front of anything revenue-affecting, containing customer PII, raising a legal, regulatory, or compliance issue, adversely affecting the customer experience, or affecting company principles.

## The idea

- **Low risk** — the model drafts, the model self-checks against explicit rules, and it releases, with a log.
- **High risk** — the model drafts, and a human reviews it in a queue. Approve, edit, or send back. Logged.
- **Any risk** — if a low-risk self-check fails, it escalates to a human anyway.

The gate lives inside the workflow, in a review queue, not held up in an email inbox.

## The five-question test

A task is high risk if **any** of these fire. No averaging, no exceptions.

1. Does this affect revenue?
2. Does it contain customer PII?
3. Is there a legal, regulatory, or compliance issue?
4. Could the customer experience be adversely affected (retention)?
5. Could the experience or process affect the company principles?

That is the whole classifier. It is deterministic code, not a model call, and that is deliberate: detection and scoring stay rule-based and auditable, generation stays behind a gate, and judgment stays with a person.

## Run it

No dependencies. No API key. Python 3.10+.

```bash
python3 risk-tier-router.py
python3 risk-tier-router.py --interactive   # you play the reviewer
python3 risk-tier-router.py --json          # audit log as JSON
```

The demo routes six worked examples:

1. Brainstorm names for an internal project — **LOW**, released
2. Summarise vendor research for the team — **LOW**, released
3. Publish a product description (e-commerce) — **HIGH**, released after edit
4. Reply to a customer asking for a refund (finance) — **HIGH**, approved
5. Flag, and recommend action on, a transaction (finance) — **HIGH**, sent back
6. Circulate a note claiming team agreement, with no source — **LOW** on paper, **escalated** when the self-check fails

Expected output: 6 tasks routed, 5 released, 1 sent back.

## Use it in your own project

1. Describe each task with the five signals in `Signals`.
2. Call `Router().route(task)`.
3. Replace `demo_reviewer()` / the interactive prompt with your real review queue.
4. Persist `router.audit_log`. That log is the point, not a by-product.

The "model" in this example is a small stub function, `fake_model_draft()`. Swap it for a real model call and keep the router. Note what the stub cannot do: it returns text only. It has no send, publish, pay, or approve method. The router decides what happens to the text.

## License

MIT. Copy it, change the signals, ship your version.
