#!/usr/bin/env python3
"""
Risk Tier Router — a runnable example of tiered gating for AI output.

Put the model where the task is generative, not decisive.
Let it move fast where a mistake is cheap and reversible.
Put a human in front of anything that touches money, a customer,
compliance, or something hard to undo.

    LOW RISK  -> model drafts + model self-checks against rules -> release, logged
    HIGH RISK -> model drafts -> human reviews in a queue -> approve / edit / send back, logged
    ANY RISK  -> self-check fails -> escalate to a human anyway

This is the pattern discussed for e-commerce and finance:
  * E-commerce: a model can draft a product description, but publishing
    it to customers is high risk.
  * Finance: a model can draft a summary or flag a transaction, but
    approving the transaction is high risk.

The routing decision here is deterministic code, not a model call.
That is deliberate: detection and scoring stay rule-based and auditable,
generation stays behind a gate, and judgment stays with a person.

Run it:
    python3 risk-tier-router-example.py
    python3 risk-tier-router-example.py --interactive   # you play the reviewer
    python3 risk-tier-router-example.py --json          # audit log as JSON

No dependencies. No API key. The "model" is a small stub function —
swap `fake_model_draft()` for a real model call and keep the router.

To use it in your own project:
  1. Describe each task with the five signals in `Signals`.
  2. Call `Router().route(task)`.
  3. Replace `demo_reviewer()` / the interactive prompt with your real
     review queue (an in-tool queue, not an email inbox).
  4. Persist `router.audit_log` — that log is the point, not a by-product.

License: MIT. Copy it, change the signals, ship your version.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


# ---------------------------------------------------------------------------
# 1. The five questions that decide the tier
# ---------------------------------------------------------------------------
# Answer these honestly for the *action the output will cause*, not for
# the draft itself. Drafting a refund email is harmless. Sending it is not.

@dataclass
class Signals:
    touches_money: bool = False       # payments, refunds, pricing, approvals
    touches_customer: bool = False    # a customer will see / be affected by it
    compliance_related: bool = False  # regulated, legal, or policy-bound
    hard_to_undo: bool = False        # publish, send, delete, commit, transact
    sensitive_data: bool = False      # personal, financial, or health data

    def triggered(self) -> list[str]:
        """Names of the high-risk signals that fired, in a stable order."""
        checks = [
            ("touches_money", self.touches_money),
            ("touches_customer", self.touches_customer),
            ("compliance_related", self.compliance_related),
            ("hard_to_undo", self.hard_to_undo),
            ("sensitive_data", self.sensitive_data),
        ]
        return [name for name, fired in checks if fired]


class Tier(Enum):
    LOW = "LOW"
    HIGH = "HIGH"


def classify(signals: Signals) -> Tier:
    """One rule, no exceptions: any high-risk signal means HIGH.

    Do not average the signals away. A task that is 'mostly internal'
    but moves money is a money task.
    """
    return Tier.HIGH if signals.triggered() else Tier.LOW


# ---------------------------------------------------------------------------
# 2. A task and its draft
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    title: str
    domain: str                 # e.g. "internal", "e-commerce", "finance"
    prompt: str                 # what you would ask the model to do
    signals: Signals
    sources: list[str] = field(default_factory=list)  # grounding for the draft


def fake_model_draft(task: Task) -> str:
    """Stand-in for a model call. Replace this one function with a real one.

    Note what it cannot do: it returns text only. It has no send, publish,
    pay, or approve method. The router decides what happens to the text.
    """
    drafts = {
        "brainstorm": "Draft names: North Loop, Field Kit, Basecamp Supply.",
        "research-summary": "Summary: three vendors compared on price and "
                            "lead time, from the sources listed.",
        "product-description": "Draft copy: 'Trail shoe with a grippy sole, "
                               "built for wet rock.'",
        "support-reply": "Draft reply: 'Sorry for the delay. We can refund "
                         "the $84.00 charge to your original payment method.'",
        "transaction-flag": "Draft flag: 'Transaction looks unusual for this "
                            "account. Recommend: approve.'",
        "internal-note-no-sources": "Draft note: 'Everyone agrees the launch "
                                    "date should move.' (no source given)",
    }
    return drafts.get(task.id, f"Draft for: {task.prompt}")



# ---------------------------------------------------------------------------
# 3. The low-risk gate: a model self-check that is really just rules
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    passed: bool
    reasons: list[str]


def self_check(task: Task, draft: str) -> CheckResult:
    """Checks a low-risk draft can pass on its own. Cheap, fast, logged.

    A self-check is not the model grading its own homework in prose.
    It is explicit rules: grounded, non-empty, and containing no claim
    that clearly needs a source it does not have.
    """
    reasons: list[str] = []
    if not draft.strip():
        reasons.append("draft is empty")
    if task.id != "internal-note-no-sources" and not task.sources:
        # Brainstorms need no sources. Factual summaries do.
        if task.id not in ("brainstorm",):
            reasons.append("no sources listed for a factual draft")
    if task.id == "internal-note-no-sources":
        reasons.append("asserts agreement ('everyone agrees') with no source")
    return CheckResult(passed=not reasons, reasons=reasons or ["rules passed"])


# ---------------------------------------------------------------------------
# 4. The high-risk gate: a human, in a queue, with three buttons
# ---------------------------------------------------------------------------
# In production this is a review queue inside the tool: draft, sources,
# signals that fired, and Approve / Edit / Send back. Not an email inbox —
# email is where review goes to stall.

@dataclass
class Review:
    decision: str   # "approve" | "edit" | "send_back"
    reviewer: str
    note: str = ""
    edited_draft: str | None = None


def demo_reviewer(task: Task, draft: str) -> Review:
    """Simulated reviewer decisions, so the demo runs without input."""
    decisions = {
        "product-description": Review(
            "edit", "demo-reviewer",
            "Approved after softening an unverified claim.",
            edited_draft="Trail shoe with a grippy sole, made for mixed terrain.",
        ),
        "support-reply": Review(
            "approve", "demo-reviewer",
            "Refund amount matches the order. OK to send.",
        ),
        "transaction-flag": Review(
            "send_back", "demo-reviewer",
            "Do not approve on a draft flag alone. Pull account history first.",
        ),
    }
    return decisions.get(
        task.id, Review("approve", "demo-reviewer", "Reviewed."))


def interactive_reviewer(task: Task, draft: str) -> Review:
    print(f"\n  REVIEW QUEUE — {task.title}")
    print(f"  Draft:   {draft}")
    print(f"  Sources: {', '.join(task.sources) or '(none)'}")
    choice = input("  [a]pprove / [e]dit / [s]end back: ").strip().lower()
    if choice.startswith("e"):
        edited = input("  Edited draft: ").strip()
        return Review("edit", "you", "Edited in review.", edited or draft)
    if choice.startswith("s"):
        return Review("send_back", "you", input("  Reason: ").strip())
    return Review("approve", "you", "Approved in review.")



# ---------------------------------------------------------------------------
# 5. The router — and the audit log it always writes
# ---------------------------------------------------------------------------

@dataclass
class Result:
    task: Task
    tier: Tier
    outcome: str        # "released" | "released_after_edit" | "sent_back" | "escalated"
    final_text: str | None
    actor: str          # who/what made the final call


class Router:
    def __init__(self, interactive: bool = False) -> None:
        self.interactive = interactive
        self.audit_log: list[dict] = []

    def _log(self, task: Task, tier: Tier, outcome: str, actor: str,
             detail: str) -> None:
        self.audit_log.append({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task_id": task.id,
            "title": task.title,
            "tier": tier.value,
            "signals_triggered": task.signals.triggered(),
            "outcome": outcome,
            "actor": actor,
            "detail": detail,
        })

    def route(self, task: Task) -> Result:
        tier = classify(task.signals)
        draft = fake_model_draft(task)

        if tier is Tier.LOW:
            check = self_check(task, draft)
            if check.passed:
                self._log(task, tier, "released", "model-self-check",
                          "; ".join(check.reasons))
                return Result(task, tier, "released", draft, "model-self-check")
            # Low risk is not no risk. A failed check escalates.
            self._log(task, tier, "escalated", "model-self-check",
                      "; ".join(check.reasons))
            review = self._review(task, draft)
            return self._apply_review(task, tier, draft, review, escalated=True)

        # HIGH: the model never releases its own draft. Ever.
        review = self._review(task, draft)
        return self._apply_review(task, tier, draft, review)

    def _review(self, task: Task, draft: str) -> Review:
        if self.interactive:
            return interactive_reviewer(task, draft)
        return demo_reviewer(task, draft)

    def _apply_review(self, task: Task, tier: Tier, draft: str,
                      review: Review, escalated: bool = False) -> Result:
        actor = f"human:{review.reviewer}"
        if review.decision == "approve":
            outcome = "escalated_then_released" if escalated else "released"
            self._log(task, tier, outcome, actor, review.note)
            return Result(task, tier, outcome, draft, actor)
        if review.decision == "edit":
            outcome = "released_after_edit"
            self._log(task, tier, outcome, actor, review.note)
            return Result(task, tier, outcome, review.edited_draft or draft, actor)
        self._log(task, tier, "sent_back", actor, review.note)
        return Result(task, tier, "sent_back", None, actor)



# ---------------------------------------------------------------------------
# 6. Six worked examples — run through them in order
# ---------------------------------------------------------------------------

def demo_tasks() -> list[Task]:
    return [
        # 1 — LOW: internal, reversible, nobody outside the team sees it.
        Task("brainstorm", "Brainstorm names for an internal project",
             "internal", "Suggest project names.",
             Signals(), sources=[]),
        # 2 — LOW: internal summary, grounded in listed sources.
        Task("research-summary", "Summarise vendor research for the team",
             "internal", "Summarise these three vendor pages.",
             Signals(), sources=["vendor-a.pdf", "vendor-b.pdf", "vendor-c.pdf"]),
        # 3 — HIGH (e-commerce): customers will read it, publishing is hard to undo.
        Task("product-description", "Publish a product description",
             "e-commerce", "Write copy for a new trail shoe.",
             Signals(touches_customer=True, hard_to_undo=True),
             sources=["product-spec-sheet.pdf"]),
        # 4 — HIGH (finance / support): money moves, a customer is affected.
        Task("support-reply", "Reply to a customer asking for a refund",
             "finance", "Draft a refund reply for an $84.00 charge.",
             Signals(touches_money=True, touches_customer=True,
                     sensitive_data=True),
             sources=["order-1842", "refund-policy-v3"]),
        # 5 — HIGH (finance): the model recommends, a human must decide.
        Task("transaction-flag", "Flag — and recommend action on — a transaction",
             "finance", "Assess this transaction and recommend next steps.",
             Signals(touches_money=True, compliance_related=True,
                     hard_to_undo=True, sensitive_data=True),
             sources=["transaction-9921"]),
        # 6 — LOW on paper, escalated in practice: self-check fails.
        Task("internal-note-no-sources", "Circulate a note claiming team agreement",
             "internal", "Write a note saying the launch date should move.",
             Signals(), sources=[]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--interactive", action="store_true",
                        help="you act as the human reviewer for high-risk tasks")
    parser.add_argument("--json", action="store_true",
                        help="print the audit log as JSON at the end")
    args = parser.parse_args(argv)

    router = Router(interactive=args.interactive)
    print("Risk Tier Router — low risk self-checks, high risk gets a human\n")

    results: list[Result] = []
    for i, task in enumerate(demo_tasks(), start=1):
        result = router.route(task)
        results.append(result)
        fired = task.signals.triggered()
        why = ", ".join(fired) if fired else "no high-risk signals"
        print(f"{i}. [{result.tier.value}] {task.title}")
        print(f"   Why this tier: {why}")
        print(f"   Outcome: {result.outcome}  (decided by: {result.actor})")
        if result.final_text:
            print(f"   Released: {result.final_text}")
        else:
            print("   Released: nothing — sent back, draft does not ship")
        print()

    released = sum(1 for r in results if r.final_text is not None)
    print(f"Tasks: {len(results)} routed, {released} released, "
          f"{len(results) - released} sent back.")
    print(f"Audit log: {len(router.audit_log)} entries recorded "
          f"(an escalation writes two: the failed check, then the review).")
    print("Every release and every block is in the log. That is the feature.")

    if args.json:
        print("\n" + json.dumps(router.audit_log, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

