# Labelling Protocol — Ticket Triage Golden Test Set (v3, final)

**Team rows used:** 2000–2999
**Golden set:** 175 tickets, stratified — 25 drawn from each of the 7 `source_label` categories (seed = 2113, reproducible). The original `source_label` was hidden from both annotators during labelling and revealed only at the resolution meeting, as a reference point; it decided no resolution.
**Annotators:** Phoebe and Nicholas — labelled independently, without conferring, then reconciled by discussion.
**Status:** Frozen. Final labels committed before any model-calling code was written.

> **Version history in brief.** v1 was written and frozen before labelling began. v2 recorded the measured agreement statistic and the disagreement list, and *proposed* new rules for the gaps that surfaced. v3 is the post-resolution protocol: it records what the team actually decided, and two of v2's proposed rules (A7, A8) were **overturned** by those decisions and have been rewritten to match. The v1 → v2 → v3 trail is the evidence that the protocol was revised because of what labelling exposed.

---

## 1. Category Definitions

1. **Credit reporting** — The complaint is about what's *on the credit file itself*: accuracy, an investigation, or a dispute with a credit reporting agency (Equifax, Experian, TransUnion) or a furnisher's reporting behaviour. Signals: FCRA citations, "block this from my report," wrong account status/dates, a dispute that was allegedly not investigated.
2. **Debt collection** — The complaint is about *being pursued for a debt*: calls, letters, threats, demands, validation requests, "this debt isn't mine," harassment. The debt can originate from any product — what matters is that the complaint targets the pursuit, not the original account.
3. **Mortgage** — A home loan: origination, servicing, escrow, modification, foreclosure, refinancing, payment processing, and release of a satisfied lien.
4. **Credit card** — The cardholder relationship itself: billing disputes, unauthorized charges, APR/interest, rewards, account closure, fraud on the card — where the card issuer is the subject.
5. **Bank account or service** — Checking/savings accounts and general bank services: deposits, holds, overdraft, account closure, fraud on the account, teller/customer service issues, ATM problems.
6. **Consumer loan** — Non-mortgage installment credit: personal loans, auto loans, student loans (private or servicing), payday loans.
7. **Money transfer or service** — Moving money between parties: P2P apps (Zelle, Venmo, Cash App), wire transfers, remittances, prepaid cards, money orders — where the complaint is about the transfer/service itself.

---

## 2. Decision Order

The resolution meeting established that the v1 rules were not merely ambiguous but **unordered** — A1 and A2 could each be read as governing the same ticket. All twelve disagreements are consistent with the following priority, which v3 states explicitly. Apply the tests in order and stop at the first that fires.

> **Step 1 — Is the accuracy of information on the credit file contested?** → **Credit reporting** (Rule A2/A5)
> **Step 2 — Otherwise, is the complaint about being pursued for a debt?** → **Debt collection** (Rule A1/A6/A7)
> **Step 3 — Otherwise, label by the product the complaint concerns** (Rules A3, A4, definitions 3–7)

This ordering is what the team's twelve resolutions actually encode: every ticket in which a credit-file accuracy claim was live resolved to Credit reporting (rows 2469, 2608, 2670, 2679, 2690, 2990), and the two tickets that resolved to Debt collection (2225, 2348) are precisely those in which no credit-file claim appears.

---

## 3. Edge-Case Rules

### Rule A — Tickets that fit two categories

- **A1. Collection activity beats the origin product.** If the core complaint is about being contacted, pursued, or sued for a debt, label **Debt collection** even when the debt arises from a credit card, medical bill, or loan.
  *Example: [row 2110]* — framed around PNC credit card services, but the complaint is disputed collection calls and conflicting balances → **Debt collection**.

- **A2. Contested credit-file accuracy beats the underlying product.** If the accuracy of information on the consumer's credit file is disputed, label **Credit reporting** even where the tradeline is a mortgage, auto loan, or card.
  *Example: [row 2043]* — "Equifax is not reporting my mortgage information" → **Credit reporting**.
  *Contrast: [row 2042]* — mentions a mortgage company and an insurance claim, but the dispute is the underlying property/insurance matter with reporting only a consequence → label by the underlying issue.

- **A3. Transfer mechanism beats the accounts at either end.** Where money was moved and the failure or fraud is in the movement itself, label **Money transfer or service**, even though a deposit account was debited and even where the account is later closed as a result. Fraud on the account or card itself, with no transfer mechanism at the centre, remains **Bank account or service** / **Credit card**.
  *Confirmed by rows 2303 and 2642; unchanged from v1.*

- **A4. Two genuinely unrelated complaints in one narrative.** Label by whichever is more developed (more sentences, more specific detail, appears first). Flag as `"multi-topic — picked X over Y"`.

- **A5. Credit reporting takes priority over Debt collection where file accuracy is contested.** *(added v2; materially narrowed in v3 after rows 2679 and 2690)*
  When a narrative contains both collection activity and credit-file complaints, **Credit reporting** governs whenever the consumer contests what the file says — a wrong balance, a false late status, a re-aged delinquency date, a tradeline they say isn't theirs.
  - **The consumer need not ask for removal in so many words.** Contesting accuracy is sufficient; an explicit "delete this" sentence is not required (row 2679).
  - **A deletion request arising from a validation failure does not convert the ticket to Debt collection.** *v2 proposed the opposite; the team overturned it at row 2690.* Where the contested facts are what the file says, the label is Credit reporting even though the FDCPA validation complaint is what prompted it.
  - **No credit bureau need be named as respondent.** A furnisher or collector reporting inaccurately engages A2 on its own (row 2608).
  - Debt collection remains correct where the pursuit is the whole grievance and no file-accuracy claim is made (rows 2225, 2348).
  *v1 gap:* v1 said to "use A2's report-language test first, then fall back to A1" without defining report-language, so one annotator read a credit-report mention as sufficient and the other required an explicit removal request. Six of twelve disagreements sat on this single boundary.

- **A6. An original creditor collecting its own debt is still collection.** *(added v2; confirmed v3 at row 2225)*
  A1 applies whether the caller is a third-party agency or the lender pursuing its own account. What matters is that the complaint targets collection conduct — harassment, abusive representatives, call frequency — rather than the loan's terms or servicing.
  *v1 gap:* v1's A1 examples all used third-party collectors, leaving the in-house case undefined.

- **A7. Personal enforcement action is collection; administering the loan is not.** *(added v2 as the opposite rule; **REVERSED in v3** by the team's resolution of row 2348)*
  Where a servicer pursues the borrower **personally for money** — a money judgment, a deficiency claim, a demand beyond the secured remedy — the complaint is about being pursued for a debt and is **Debt collection** under A1. Where the complaint is about how the loan is originated, serviced, modified, escrowed, or foreclosed as the ordinary machinery of the loan, it remains **Mortgage** under definition 3.
  - *v2 had proposed that all mortgage-derived legal action stays Mortgage. The team rejected this at row 2348*, on the ground that a judgment sought after Chapter 13 without reaffirmation is pursuit of the person, not administration of the loan.
  - **Untested edge:** no ticket in this set tested a pure foreclosure complaint with no personal-liability claim. Definition 3 names foreclosure explicitly, so such a ticket should be **Mortgage**; flag any future case that tests this.

- **A8. An account discovered only on the credit file is Credit reporting.** *(added v2 as the opposite rule; **REVERSED in v3** by the team's resolution of row 2670)*
  Where a consumer learns of a fraudulently-opened account only through their credit report, knows nothing of it beyond the reported tradeline fields, and contests it there, label **Credit reporting** — whatever product the tradeline claims to be.
  - *v2 had proposed labelling by the product fraudulently opened. The team rejected this at row 2670*, where the narrative reproduces credit-file fields verbatim and the consumer has no independent knowledge of the account.
  - This has the practical benefit of disposing of internally contradictory tradeline data (a card issuer carrying an `Account Type: MORTGAGE` field) without the annotators having to adjudicate which field is right.
  - Identity theft is still labelled **by product** where the consumer has independent knowledge of the fraudulent account — statements received, charges seen, contact from the institution — rather than knowing of it only as a report entry.

### Rule B — Tickets that fit none of the seven

- **B1.** During independent labelling, if a narrative's subject matter falls outside all seven products, mark it **UNCLEAR** rather than forcing a guess. UNCLEAR is a flag for the resolution meeting, never a submitted answer.
- **B2.** Don't use "closest thing mentioned" as a tiebreaker at labelling time — if you are guessing, flag it.
- **B3. UNCLEAR cannot survive into the frozen set.** The deployed classifier returns one of seven categories, so an eighth class would leave an unfillable row in the confusion matrix and corrupt the accuracy measurement. Every UNCLEAR ticket is resolved at the meeting as either:
  - **(a) Forced best-fit** — the team agrees the least-bad of the seven and records why. *Used for all four UNCLEAR tickets in this set (rows 2021, 2052, 2664, 2896).*
  - **(b) Excluded and replaced** — dropped and a replacement drawn from the same original category to preserve the 25-per-category design. *Not used in this set.*
- **B3.1. Thin is not unclassifiable.** A short, redacted, or poorly written narrative that still identifies a product is **not** UNCLEAR. Reserve UNCLEAR for tickets whose *subject matter* lies outside the seven products.
  *Established at rows 2021 and 2052, where UNCLEAR was withdrawn in favour of the identifiable product.*
  *v1 gap:* v1 introduced UNCLEAR without a threshold or a disposal procedure, so one annotator read B1 as "insufficient detail" and the other as "outside the seven products."

### Rule C — Ambiguous / thin narratives

- **C1.** Check whether a product is still identifiable before reaching for UNCLEAR.
  *Example: [row 2574]* — two sentences, but Navient, "lender," and robocalling point to loan-servicing collection calls → **Debt collection**.
- **C2.** Don't infer from narrative length, tone, or how typical a story sounds. Label from stated content only.

---

## 4. Inter-Annotator Agreement

Measured on all 175 tickets, comparing the two independently-submitted label columns **before** any discussion.

| Statistic | Value |
|---|---|
| Tickets double-labelled | 175 |
| Exact matches | 163 |
| **Raw (percent) agreement** | **93.1%** |
| **Cohen's κ** | **0.920** |
| Disagreements | 12 |

**Why Cohen's κ.** Raw agreement overstates reliability under class imbalance, because two annotators labelling independently would match by chance some of the time. Cohen's κ corrects for that expected agreement and is the statistic reported here; raw agreement is given alongside for interpretability. κ = 0.920 is "almost perfect" on the Landis & Koch scale (> 0.81), indicating the §1 definitions were operationally reliable.

**Where the disagreement concentrated.** The twelve disagreements were not spread evenly. Six — half — sat on the **Debt collection / Credit reporting** boundary (rows 2469, 2608, 2679, 2690 directly, plus 2670 and 2990 where Credit reporting competed with another product). That clustering is itself the finding: v1's A1 and A2 overlapped in a region the protocol never resolved. The remainder were the **Money transfer / Bank account** boundary (rows 2303, 2642) and the **UNCLEAR threshold** (rows 2021, 2052).

**Resolution outcomes.** Of the twelve, seven resolved to Nicholas's label and five to Phoebe's — no systematic deference in either direction. All six credit-file tickets resolved to Credit reporting, which is what produced the decision order now stated in §2.

---

## 5. Disagreement Log

All twelve disagreements were resolved by discussion between both annotators. The original `source_label` was visible at this stage as a reference only; where the team's judgment differed from it, the team's judgment stands. Full narratives and both annotators' original reasoning are preserved in `golden_test_set_final_175.csv`.

| Row | Phoebe | Nicholas | **Final** | Basis | Gap → rule |
|---|---|---|---|---|---|
| 2021 | Credit card | UNCLEAR | **Credit card** | Revolving balance and issuer handling identify the product; UNCLEAR withdrawn | B3.1 |
| 2052 | Consumer loan | UNCLEAR | **Consumer loan** | Defect is out of scope, but the auto loan is the only product hook; forced best-fit | B3(a), B3.1 |
| 2225 | Debt collection | Consumer loan | **Debt collection** | Abuse on payment calls is collection conduct, not loan terms — in-house collector still counts | A6 |
| 2303 | Money transfer | Bank account | **Money transfer or service** | Funds debited but never arrived; failure is in the transfer | A3 (confirmed) |
| 2348 | Mortgage | Debt collection | **Debt collection** | Money judgment after Ch.13 is pursuit of the person, not loan administration | **A7 reversed** |
| 2469 | Debt collection | Credit reporting | **Credit reporting** | Removal sought for inaccurate reporting; FCRA §623 cited | A5 |
| 2608 | Debt collection | Credit reporting | **Credit reporting** | False amount contested as a credit-file entry; no bureau needed as respondent | A5 |
| 2642 | Money transfer | Bank account | **Money transfer or service** | Unauthorised transfer is the loss; closure is downstream | A3 (confirmed) |
| 2670 | Credit card | Credit reporting | **Credit reporting** | Account known only as a tradeline; disposes of the conflicting `Account Type` field | **A8 reversed** |
| 2679 | Debt collection | Credit reporting | **Credit reporting** | Accuracy contested; explicit removal wording not required | A5 |
| 2690 | Debt collection | Credit reporting | **Credit reporting** | Re-aged date is the contested fact; validation-failure carve-out removed | A5 |
| 2990 | Mortgage | Credit reporting | **Credit reporting** | Repayment plan reported as delinquency; accuracy is what's disputed | A5 |

### Tickets both annotators independently marked UNCLEAR

Not disagreements, but B3 requires disposal before freezing.

| Row | Both said | Disposal | **Final** | Basis |
|---|---|---|---|---|
| 2664 | UNCLEAR | (a) forced best-fit | **Debt collection** | Denial that any debt is owed, against liens on record — the disputed-debt limb of A1; no file-accuracy claim, no other product identifiable |
| 2896 | UNCLEAR | (a) forced best-fit | **Mortgage** | Trust-accounting claims are out of scope, but the bank's lien and the eventual release of mortgage are a satisfied-lien grievance under definition 3 — the only one of the seven the narrative touches. **Weakest assignment in the set; flagged.** |

---

## 6. Final Golden Set

Frozen at **175 tickets, 0 UNCLEAR**, all seven categories represented.

| Category | Final count |
|---|---|
| Credit reporting | 35 |
| Bank account or service | 26 |
| Credit card | 24 |
| Money transfer or service | 24 |
| Consumer loan | 23 |
| Debt collection | 22 |
| Mortgage | 21 |

Sampling was stratified at 25 per category on the *noisy* `source_label`; the distribution above is the *relabelled* truth, so the drift from 25 is expected and is itself a measure of how noisy the source labels were. Credit reporting gained ten tickets on net, which is consistent with the decision order in §2 pulling file-accuracy complaints out of Debt collection and Mortgage.

**Note for the accuracy analysis:** the set is mildly imbalanced (21–35 per class). Report per-class precision/recall and a macro-averaged F1 alongside overall accuracy, since overall accuracy alone will over-weight Credit reporting.

---

## 7. Revision Log

| Version | Change | Triggered by |
|---|---|---|
| v1 | Initial protocol: 7 definitions, rules A1–A4, B1–B2, C1–C2 | Drafted and frozen before labelling began |
| v2 | Added measured agreement statistic and disagreement list. *Proposed* A5, A6, A7, A8, B3, B3.1 | Post-labelling, pre-resolution |
| v3 | Added explicit decision order (§2). **A7 reversed** — personal money judgment is Debt collection, not Mortgage. **A8 reversed** — accounts known only as tradelines are Credit reporting, not labelled by product. **A5 narrowed** — v2's validation-failure carve-out removed; removal wording not required; no bureau respondent required. A3 and A6 confirmed unchanged. B3(a) applied to all four UNCLEAR tickets. Final set frozen, 0 UNCLEAR | Resolution meeting: rows 2348 (A7), 2670 (A8), 2679 + 2690 (A5), 2225 (A6), 2303 + 2642 (A3), 2021 + 2052 + 2664 + 2896 (B3) |
