# Accuracy report

Every golden-set ticket sent once per run through `POST /tickets`, one at a time, outside any load run. Cells: mean ± SD (min–max) across runs. Per-category accuracy = share of that category's golden tickets answered correctly (recall). A ticket with no category (502 / no answer) counts as incorrect. p50 latency = client-side time per ticket with nothing else running.

95% CI: percentile bootstrap over golden tickets (2000 resamples, seed 2113); each ticket's score is its share of correct runs. Per-category intervals resample within that category, so they are wide where the category has few golden tickets. The interval reflects which tickets happen to be in the golden set, not run-to-run variation (that is the ± SD).

| Model | Runs | Overall | Overall 95% CI | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | No answer | p50 latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **gemma4:e4b** | 1 | 84.0% (1 run) | 77.7–89.1% | 86% (1 run) | 58% (1 run) | 96% (1 run) | 100% (1 run) | 77% (1 run) | 71% (1 run) | 100% (1 run) | 0.0 (1 run) | 34.9 (1 run) |
| **llama3.2:1b** | 1 | 34.9% (1 run) | 28.0–41.7% | 71% (1 run) | 0% (1 run) | 9% (1 run) | 27% (1 run) | 82% (1 run) | 0% (1 run) | 43% (1 run) | 0.0 (1 run) | 2.8 (1 run) |
| **mistral:7b** | 1 | 73.1% (1 run) | 66.9–79.4% | 83% (1 run) | 75% (1 run) | 65% (1 run) | 69% (1 run) | 86% (1 run) | 33% (1 run) | 100% (1 run) | 0.0 (1 run) | 12.4 (1 run) |
| **phi3:3.8b** | 1 | 73.1% (1 run) | 66.9–80.0% | 86% (1 run) | 58% (1 run) | 74% (1 run) | 88% (1 run) | 50% (1 run) | 50% (1 run) | 100% (1 run) | 0.0 (1 run) | 6.5 (1 run) |

## Pairwise comparison (exact McNemar)

Each pair is compared on the golden tickets both answered. A ticket counts as correct for a model when it was right in more than half of that model's runs. Only the discordant tickets (one model right, the other wrong) carry information; p is the two-sided exact binomial test of those against 50/50. Holm-adjusted p corrects for testing every pair.

| A | B | Tickets | A acc | B acc | Only A right | Only B right | p (exact) | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| gemma4-e4b_accuracy_golden175 | llama3.2-1b_accuracy_golden175 | 175 | 84.0% | 34.9% | 90 | 4 | <0.0001 | <0.0001 |
| gemma4-e4b_accuracy_golden175 | mistral-7b_accuracy_golden175 | 175 | 84.0% | 73.1% | 28 | 9 | 0.0026 | 0.0077 |
| gemma4-e4b_accuracy_golden175 | phi3-3.8b_accuracy_golden175 | 175 | 84.0% | 73.1% | 28 | 9 | 0.0026 | 0.0077 |
| llama3.2-1b_accuracy_golden175 | mistral-7b_accuracy_golden175 | 175 | 34.9% | 73.1% | 4 | 71 | <0.0001 | <0.0001 |
| llama3.2-1b_accuracy_golden175 | phi3-3.8b_accuracy_golden175 | 175 | 34.9% | 73.1% | 9 | 76 | <0.0001 | <0.0001 |
| mistral-7b_accuracy_golden175 | phi3-3.8b_accuracy_golden175 | 175 | 73.1% | 73.1% | 22 | 22 | 1.0000 | 1.0000 |

## gemma4-e4b_accuracy_golden175

Runs: run1. 

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 85.7% (1 run) | 74.3–97.1% | 78.9% (1 run) |
| Credit card | 24 | 58.3% (1 run) | 37.5–79.2% | 93.3% (1 run) |
| Consumer loan | 23 | 95.7% (1 run) | 87.0–100.0% | 91.7% (1 run) |
| Bank account or service | 26 | 100.0% (1 run) | 100.0–100.0% | 68.4% (1 run) |
| Debt collection | 22 | 77.3% (1 run) | 59.1–95.5% | 94.4% (1 run) |
| Money transfer or service | 24 | 70.8% (1 run) | 54.1–87.5% | 100.0% (1 run) |
| Mortgage | 21 | 100.0% (1 run) | 100.0–100.0% | 84.0% (1 run) |
| **Overall** | 175 | 84.0% (1 run) | 77.7–89.1% |  |

Confusion matrix (single run); rows = golden label, columns = model's answer:

| Golden \ Predicted | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | (no answer) | Total | Accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| **Credit reporting** | **30** | · | · | 1 | 1 | · | 3 | · | 35 | 86% |
| **Credit card** | 3 | **14** | 2 | 5 | · | · | · | · | 24 | 58% |
| **Consumer loan** | 1 | · | **22** | · | · | · | · | · | 23 | 96% |
| **Bank account or service** | · | · | · | **26** | · | · | · | · | 26 | 100% |
| **Debt collection** | 4 | · | · | · | **17** | · | 1 | · | 22 | 77% |
| **Money transfer or service** | · | 1 | · | 6 | · | **17** | · | · | 24 | 71% |
| **Mortgage** | · | · | · | · | · | · | **21** | · | 21 | 100% |

## llama3.2-1b_accuracy_golden175

Runs: run1. 

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 71.4% (1 run) | 54.3–85.7% | 33.3% (1 run) |
| Credit card | 24 | 0.0% (1 run) | 0.0–0.0% | 0.0% (1 run) |
| Consumer loan | 23 | 8.7% (1 run) | 0.0–21.7% | 66.7% (1 run) |
| Bank account or service | 26 | 26.9% (1 run) | 11.5–46.2% | 70.0% (1 run) |
| Debt collection | 22 | 81.8% (1 run) | 63.6–95.5% | 24.7% (1 run) |
| Money transfer or service | 24 | 0.0% (1 run) | 0.0–0.0% | - |
| Mortgage | 21 | 42.9% (1 run) | 19.0–66.7% | 69.2% (1 run) |
| **Overall** | 175 | 34.9% (1 run) | 28.0–41.7% |  |

Confusion matrix (single run); rows = golden label, columns = model's answer:

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

Runs: run1. 

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 82.9% (1 run) | 68.6–94.3% | 85.3% (1 run) |
| Credit card | 24 | 75.0% (1 run) | 58.3–91.7% | 50.0% (1 run) |
| Consumer loan | 23 | 65.2% (1 run) | 43.5–82.6% | 83.3% (1 run) |
| Bank account or service | 26 | 69.2% (1 run) | 50.0–84.6% | 64.3% (1 run) |
| Debt collection | 22 | 86.4% (1 run) | 72.7–100.0% | 82.6% (1 run) |
| Money transfer or service | 24 | 33.3% (1 run) | 16.7–54.2% | 100.0% (1 run) |
| Mortgage | 21 | 100.0% (1 run) | 100.0–100.0% | 75.0% (1 run) |
| **Overall** | 175 | 73.1% (1 run) | 66.9–79.4% |  |

Confusion matrix (single run); rows = golden label, columns = model's answer:

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

Runs: run4. 

| Category | Golden n | Accuracy (recall) | 95% CI | Precision |
|---|---|---|---|---|
| Credit reporting | 35 | 85.7% (1 run) | 74.3–97.1% | 75.0% (1 run) |
| Credit card | 24 | 58.3% (1 run) | 37.5–79.2% | 77.8% (1 run) |
| Consumer loan | 23 | 73.9% (1 run) | 56.5–91.3% | 89.5% (1 run) |
| Bank account or service | 26 | 88.5% (1 run) | 76.9–100.0% | 53.5% (1 run) |
| Debt collection | 22 | 50.0% (1 run) | 27.3–72.7% | 100.0% (1 run) |
| Money transfer or service | 24 | 50.0% (1 run) | 29.2–70.8% | 100.0% (1 run) |
| Mortgage | 21 | 100.0% (1 run) | 100.0–100.0% | 65.6% (1 run) |
| **Overall** | 175 | 73.1% (1 run) | 66.9–80.0% |  |

Confusion matrix (single run); rows = golden label, columns = model's answer:

| Golden \ Predicted | Credit reporting | Credit card | Consumer loan | Bank account or service | Debt collection | Money transfer or service | Mortgage | (no answer) | Total | Accuracy |
|---|---|---|---|---|---|---|---|---|---|---|
| **Credit reporting** | **30** | · | 1 | · | · | · | 4 | · | 35 | 86% |
| **Credit card** | 4 | **14** | · | 6 | · | · | · | · | 24 | 58% |
| **Consumer loan** | · | · | **17** | 1 | · | · | 5 | · | 23 | 74% |
| **Bank account or service** | · | 3 | · | **23** | · | · | · | · | 26 | 88% |
| **Debt collection** | 5 | · | 1 | 3 | **11** | · | 2 | · | 22 | 50% |
| **Money transfer or service** | 1 | 1 | · | 10 | · | **12** | · | · | 24 | 50% |
| **Mortgage** | · | · | · | · | · | · | **21** | · | 21 | 100% |
