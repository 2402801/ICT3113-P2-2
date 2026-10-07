# Accuracy report

Every golden-set ticket sent once per run through `POST /tickets`, one at a time, outside any load run. Cells: mean ± SD (min–max) across runs. Per-category accuracy = share of that category's golden tickets answered correctly (recall). A ticket with no category (502 / no answer) counts as incorrect. p50 latency = client-side time per ticket with nothing else running.

95% CI: percentile bootstrap over golden tickets (2000 resamples, seed 2113); each ticket's score is its share of correct runs. Per-category intervals resample within that category, so they are wide where the category has few golden tickets. The interval reflects which tickets happen to be in the golden set, not run-to-run variation (that is the ± SD).

| Model | Runs | Overall | Overall 95% CI | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | No answer | p50 latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **llama3.2:1b** | 3 | 34.9% ± 0.0 (34.9–34.9) | 28.0–41.7% | 71% ± 0 (71–71) | 0% ± 0 (0–0) | 9% ± 0 (9–9) | 27% ± 0 (27–27) | 82% ± 0 (82–82) | 0% ± 0 (0–0) | 43% ± 0 (43–43) | 0.0 ± 0.0 (0.0–0.0) | 2.7 ± 0.3 (2.5–3.0) |
| **mistral:7b** | 3 | 73.1% ± 0.0 (73.1–73.1) | 66.9–79.4% | 83% ± 0 (83–83) | 75% ± 0 (75–75) | 65% ± 0 (65–65) | 69% ± 0 (69–69) | 86% ± 0 (86–86) | 33% ± 0 (33–33) | 100% ± 0 (100–100) | 0.0 ± 0.0 (0.0–0.0) | 11.6 ± 0.7 (11.1–12.4) |
| **phi3:3.8b** | 3 | 72.6% ± 0.6 (72.0–73.1) | 66.1–79.2% | 85% ± 2 (83–86) | 58% ± 0 (58–58) | 74% ± 0 (74–74) | 88% ± 0 (88–88) | 48% ± 3 (45–50) | 49% ± 2 (46–50) | 100% ± 0 (100–100) | 1.3 ± 0.6 (1.0–2.0) | 7.4 ± 0.2 (7.2–7.5) |

## Pairwise comparison (exact McNemar)

Each pair is compared on the golden tickets both answered. A ticket counts as correct for a model when it was right in more than half of that model's runs. Only the discordant tickets (one model right, the other wrong) carry information; p is the two-sided exact binomial test of those against 50/50. Holm-adjusted p corrects for testing every pair.

| A | B | Tickets | A acc | B acc | Only A right | Only B right | p (exact) | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| llama3.2-1b_accuracy_golden175 | mistral-7b_accuracy_golden175 | 175 | 34.9% | 73.1% | 4 | 71 | <0.0001 | <0.0001 |
| llama3.2-1b_accuracy_golden175 | phi3-3.8b_accuracy_golden175 | 175 | 34.9% | 73.1% | 9 | 76 | <0.0001 | <0.0001 |
| mistral-7b_accuracy_golden175 | phi3-3.8b_accuracy_golden175 | 175 | 73.1% | 73.1% | 22 | 22 | 1.0000 | 1.0000 |

## llama3.2-1b_accuracy_golden175

Runs: run1, run2, run3. Run-to-run agreement: 175/175 tickets got the same answer in every run.

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 71.4% ± 0.0 (71.4–71.4) | 54.3–85.7% | 33.3% ± 0.0 (33.3–33.3) |
| Credit card | 24 | 0.0% ± 0.0 (0.0–0.0) | 0.0–0.0% | 0.0% ± 0.0 (0.0–0.0) |
| Consumer loan | 23 | 8.7% ± 0.0 (8.7–8.7) | 0.0–21.7% | 66.7% ± 0.0 (66.7–66.7) |
| Bank account or service | 26 | 26.9% ± 0.0 (26.9–26.9) | 11.5–46.2% | 70.0% ± 0.0 (70.0–70.0) |
| Debt collection | 22 | 81.8% ± 0.0 (81.8–81.8) | 63.6–95.5% | 24.7% ± 0.0 (24.7–24.7) |
| Money transfer or service | 24 | 0.0% ± 0.0 (0.0–0.0) | 0.0–0.0% | - |
| Mortgage | 21 | 42.9% ± 0.0 (42.9–42.9) | 19.0–66.7% | 69.2% ± 0.0 (69.2–69.2) |
| **Overall** | 175 | 34.9% ± 0.0 (34.9–34.9) | 28.0–41.7% |  |

Confusion matrix (identical in all 3 runs); rows = golden label, columns = model's answer:

| Golden \ Predicted | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | (no answer) | Total | Accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| **Credit reporting** | **25** | · | · | · | 8 | · | 2 | · | 35 | 71% |
| **Credit card** | 20 | **0** | · | · | 4 | · | · | · | 24 | 0% |
| **Consumer loan** | 10 | · | **2** | 1 | 9 | · | 1 | · | 23 | 9% |
| **Bank account or service** | 11 | · | · | **7** | 8 | · | · | · | 26 | 27% |
| **Debt collection** | 3 | · | · | · | **18** | · | 1 | · | 22 | 82% |
| **Money transfer or service** | 1 | 1 | · | 2 | 20 | **0** | · | · | 24 | 0% |
| **Mortgage** | 5 | · | 1 | · | 6 | · | **9** | · | 21 | 43% |

## mistral-7b_accuracy_golden175

Runs: run1, run2, run3. Run-to-run agreement: 175/175 tickets got the same answer in every run.

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 82.9% ± 0.0 (82.9–82.9) | 68.6–94.3% | 85.3% ± 0.0 (85.3–85.3) |
| Credit card | 24 | 75.0% ± 0.0 (75.0–75.0) | 58.3–91.7% | 50.0% ± 0.0 (50.0–50.0) |
| Consumer loan | 23 | 65.2% ± 0.0 (65.2–65.2) | 43.5–82.6% | 83.3% ± 0.0 (83.3–83.3) |
| Bank account or service | 26 | 69.2% ± 0.0 (69.2–69.2) | 50.0–84.6% | 64.3% ± 0.0 (64.3–64.3) |
| Debt collection | 22 | 86.4% ± 0.0 (86.4–86.4) | 72.7–100.0% | 82.6% ± 0.0 (82.6–82.6) |
| Money transfer or service | 24 | 33.3% ± 0.0 (33.3–33.3) | 16.7–54.2% | 100.0% ± 0.0 (100.0–100.0) |
| Mortgage | 21 | 100.0% ± 0.0 (100.0–100.0) | 100.0–100.0% | 75.0% ± 0.0 (75.0–75.0) |
| **Overall** | 175 | 73.1% ± 0.0 (73.1–73.1) | 66.9–79.4% |  |

Confusion matrix (identical in all 3 runs); rows = golden label, columns = model's answer:

| Golden \ Predicted | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | (no answer) | Total | Accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| **Credit reporting** | **29** | 1 | · | · | 1 | · | 4 | · | 35 | 83% |
| **Credit card** | 1 | **18** | 3 | 2 | · | · | · | · | 24 | 75% |
| **Consumer loan** | 3 | 1 | **15** | 1 | 1 | · | 2 | · | 23 | 65% |
| **Bank account or service** | · | 8 | · | **18** | · | · | · | · | 26 | 69% |
| **Debt collection** | 1 | 1 | · | · | **19** | · | 1 | · | 22 | 86% |
| **Money transfer or service** | · | 7 | · | 7 | 2 | **8** | · | · | 24 | 33% |
| **Mortgage** | · | · | · | · | · | · | **21** | · | 21 | 100% |

## phi3-3.8b_accuracy_golden175

Runs: run1, run2, run3. Run-to-run agreement: 171/175 tickets got the same answer in every run.

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 84.8% ± 1.6 (82.9–85.7) | 71.4–94.3% | 75.4% ± 1.3 (74.4–76.9) |
| Credit card | 24 | 58.3% ± 0.0 (58.3–58.3) | 37.5–79.2% | 77.8% ± 0.0 (77.8–77.8) |
| Consumer loan | 23 | 73.9% ± 0.0 (73.9–73.9) | 56.5–91.3% | 89.5% ± 0.0 (89.5–89.5) |
| Bank account or service | 26 | 88.5% ± 0.0 (88.5–88.5) | 76.9–100.0% | 53.5% ± 0.0 (53.5–53.5) |
| Debt collection | 22 | 48.5% ± 2.6 (45.5–50.0) | 27.3–68.2% | 100.0% ± 0.0 (100.0–100.0) |
| Money transfer or service | 24 | 48.6% ± 2.4 (45.8–50.0) | 29.2–66.7% | 100.0% ± 0.0 (100.0–100.0) |
| Mortgage | 21 | 100.0% ± 0.0 (100.0–100.0) | 100.0–100.0% | 65.6% ± 0.0 (65.6–65.6) |
| **Overall** | 175 | 72.6% ± 0.6 (72.0–73.1) | 66.1–79.2% |  |

Confusion matrix (summed over 3 runs); rows = golden label, columns = model's answer:

| Golden \ Predicted | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | (no answer) | Total | Accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| **Credit reporting** | **89** | · | 3 | · | · | · | 12 | 1 | 105 | 85% |
| **Credit card** | 11 | **42** | · | 18 | · | · | · | 1 | 72 | 58% |
| **Consumer loan** | · | · | **51** | 3 | · | · | 15 | · | 69 | 74% |
| **Bank account or service** | · | 9 | · | **69** | · | · | · | · | 78 | 88% |
| **Debt collection** | 15 | · | 3 | 9 | **32** | · | 6 | 1 | 66 | 48% |
| **Money transfer or service** | 3 | 3 | · | 30 | · | **35** | · | 1 | 72 | 49% |
| **Mortgage** | · | · | · | · | · | · | **63** | · | 63 | 100% |
