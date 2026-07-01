# SetFit 508 Compliance Model

## What is SetFit?

SetFit (Sentence Transformer Fine-Tuning) is a framework for few-shot text classification developed by Hugging Face and Intel Labs, published in 2022. It was designed to solve a specific problem: how do you train an accurate text classifier when you only have a small number of labeled examples?

Traditional fine-tuning of language models (like BERT) requires thousands of labeled examples. SetFit can achieve comparable accuracy with as few as 8 examples per class. It does this through a two-stage training process:

### Stage 1: Contrastive Learning

SetFit takes a pre-trained sentence transformer (a model that converts text into numerical vectors) and fine-tunes it using contrastive pairs. For each training example, it generates pairs:

- **Positive pairs**: Two texts with the same label (e.g., two compliant solicitations)
- **Negative pairs**: Two texts with different labels (e.g., one compliant, one non-compliant)

The model learns to push similar texts closer together in vector space and dissimilar texts further apart. This is where the `num_iterations` parameter matters — more iterations means more contrastive pairs are generated, which is critical when you have very few examples of the minority class.

### Stage 2: Classification Head

After the sentence transformer is fine-tuned, SetFit trains a simple logistic regression classifier on top of the embeddings. This classifier takes the vector representation of a text and outputs a class label (compliant / non-compliant).

The result is a model that:
- Runs entirely locally (no API calls)
- Is fast (~300ms per prediction)
- Is small (~80MB)
- Works well with limited training data

### Why SetFit over GPT/Gemini for compliance?

| Aspect | SetFit | LLM (GPT/Gemini) |
|--------|--------|-------------------|
| Consistency | Same input always produces same output | Can vary between calls |
| Speed | ~300ms | ~10-20 seconds |
| Cost | Free (runs locally) | Per-token API cost |
| Offline | Yes | No |
| Explainability | Trained on labeled data with known accuracy | Black box reasoning |
| Accuracy | Measured via cross-validation | Unmeasured, prompt-dependent |

For a compliance decision that needs to be consistent, auditable, and reproducible, a trained classifier is the right tool. The LLM is better suited for generating explanations and context.

---

## How David Built the 508 Compliance Model

### The Dataset

David assembled a labeled dataset of 301 federal solicitations from SAM.gov:

- **58 compliant** — solicitations that include Section 508 accessibility requirements
- **243 non-compliant** — solicitations that do not include 508 requirements

Each solicitation was manually reviewed by the QA team. The labels come from human expert judgment, not AI predictions. The CSV includes the solicitation number, the specific PDF/DOCX files that were reviewed, and detailed reviewer notes explaining why each solicitation was classified the way it was.

### The Challenge: Class Imbalance

The dataset is heavily imbalanced — roughly 1 compliant for every 4.2 non-compliant. This is realistic (most solicitations don't include 508 language), but it creates a training problem: a naive model could achieve 81% accuracy by simply predicting "non-compliant" for everything.

### David's Signal Extraction Pipeline

Raw solicitation documents are long (often 50+ pages) and mostly irrelevant to 508 compliance. Feeding the entire document to the model would dilute the signal. David built a two-stage extraction pipeline to pull out only the relevant text:

**Stage 1 — Keyword Pre-Filter**

Extract paragraphs that contain phrases from the 508 standards text (e.g., "Section 508", "Rehabilitation Act", "WCAG", "assistive technology"). This is a fast, high-recall filter that catches obvious references.

**Stage 2 — Semantic Re-Ranking**

Encode the remaining paragraphs using the same sentence transformer (all-MiniLM-L6-v2) and rank them by cosine similarity to the 508 standards text. Keep the top 10 most semantically similar paragraphs. This catches references that use different wording but mean the same thing.

The extracted signal text is capped at ~1,024 characters (256 tokens × 4 chars) to fit within the model's context window.

For non-compliant solicitations where no 508 signal is found, the absence of signal IS the signal — David falls back to the first chunk of raw text so the model learns what "no 508 language" looks like.

### Handling Imbalance

David used three strategies to address the 4:1 class imbalance:

1. **Non-compliant capping**: Non-compliant examples are capped at 3× the compliant count (175 max). This prevents the model from being overwhelmed by the majority class.

2. **Synthetic compliant examples**: The 508 standards text itself is chunked into ~25 synthetic "compliant" training examples. These are added to the training set only (never the test set) to boost the minority class.

3. **Stratified cross-validation**: All splits preserve the class ratio, ensuring every fold has a representative mix of compliant and non-compliant examples.

### Model Architecture

- **Base model**: `sentence-transformers/all-MiniLM-L6-v2`
  - 6-layer BERT with 384-dimensional embeddings
  - 22M parameters (tiny by modern standards)
  - 256 token max input length
  - Trained on 1B+ sentence pairs for general-purpose semantic similarity

- **Classification head**: Logistic regression (sklearn) trained on the fine-tuned embeddings

- **Training config**:
  - `num_iterations=20` (generates 20 contrastive pairs per example — use 40 on GPU)
  - `num_epochs=1`
  - 3-fold stratified cross-validation (use 5 on GPU)

### Validation

David used two validation approaches:

1. **Stratified K-Fold Cross-Validation** (3 folds): The primary validation method. Each fold trains on ~67% of the data and tests on ~33%, with class ratios preserved. Reports per-fold and mean F1 scores. The key metric is Compliant F1 — how well the model identifies the minority class.

2. **Hold-Out Dev Test** (20% stratified split, seed=99): A separate evaluation using a different random seed than training (42 vs 99) to verify the model generalizes. This is the "trust these numbers" evaluation.

### What the Model Outputs

For each solicitation, the model returns:

```json
{
  "prediction": "compliant" or "non_compliant",
  "confidence": 0.0 to 1.0,
  "is_508_applicable": true,
  "includes_508": true/false,
  "prediction_source": "setfit",
  "signal_text": "the extracted text that was used for prediction",
  "duration_ms": 347
}
```

The `signal_text` field is important for explainability — it shows exactly what text the model based its decision on, so reviewers can verify the prediction makes sense.

### Key Design Decisions

1. **MiniLM-L6-v2 over larger models**: David chose the smallest effective sentence transformer. It's fast enough to run on a 1GB cloud.gov container without GPU. The accuracy tradeoff is minimal for this binary classification task.

2. **Signal extraction before classification**: Instead of feeding raw documents to the model, the two-stage extraction ensures the model sees concentrated 508-relevant text. This dramatically improves accuracy on long documents.

3. **Solicitation-level labels**: The model predicts at the solicitation level, not the file level. If ANY file in a solicitation contains 508 language, the solicitation is labeled compliant. This matches how human reviewers assess compliance.

4. **Caching extraction results**: The signal extraction step (which requires reading PDFs and running embeddings) is cached to `extraction_cache.json`. This means retraining the model doesn't require re-extracting text from hundreds of PDFs.

5. **Final model trained on ALL data**: After cross-validation confirms the model performs well, the final production model is trained on 100% of the data (including synthetic examples). This maximizes the information available to the model.


---

## Evaluation Metrics Explained

David's evaluation code produces several metrics. Here's what each one means and why it matters for this specific use case.

### The Dataset After Extraction

Of the 301 labeled solicitations, 284 successfully had signal extracted from their PDFs (17 were skipped due to missing or unreadable files):
- 57 compliant
- 227 non-compliant

### Precision, Recall, and F1 Score

These are the three core metrics for each class. They answer different questions:

**Precision** — "When the model says compliant, how often is it right?"

```
Precision = True Positives / (True Positives + False Positives)
```

High precision means few false alarms. If precision is 0.90, then 90% of the solicitations the model flags as "compliant" actually are compliant.

**Recall** — "Of all the actually compliant solicitations, how many did the model catch?"

```
Recall = True Positives / (True Positives + False Negatives)
```

High recall means few missed catches. If recall is 0.85, the model catches 85% of all compliant solicitations. The other 15% slip through as false negatives.

**F1 Score** — The harmonic mean of precision and recall. It balances both concerns into a single number.

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

F1 ranges from 0 to 1. A score of 1.0 means perfect precision AND perfect recall. A score of 0.5 means the model is struggling with one or both.

### Why Compliant F1 is the Key Metric

In David's code, you'll see this comment: `← your key metric` next to Compliant F1. Here's why:

The model's job is to identify solicitations that include Section 508 requirements. Missing a compliant solicitation (false negative) is more costly than incorrectly flagging a non-compliant one (false positive):

- **False negative** (compliant called non-compliant): A solicitation with 508 language gets missed. The review team doesn't see it. This is a compliance gap.
- **False positive** (non-compliant called compliant): A solicitation without 508 language gets flagged for review. The reviewer spends a few minutes looking at it and moves on. Annoying but not harmful.

Because the compliant class is the minority (57 out of 284), it's the harder class to predict correctly. A model that just guesses "non-compliant" for everything would get 80% accuracy but 0% Compliant F1. That's why Compliant F1 is the metric that matters.

### Macro F1 vs Weighted F1

**Macro F1** — Average of Compliant F1 and Non-Compliant F1, treating both classes equally. This is the fairest measure when classes are imbalanced because it doesn't let the majority class dominate.

```
Macro F1 = (Compliant F1 + Non-Compliant F1) / 2
```

**Weighted F1** — Average of both F1 scores, weighted by the number of samples in each class. This gives more weight to the majority class (non-compliant). It looks better on paper but can mask poor performance on the minority class.

For this use case, Macro F1 is more informative than Weighted F1.

### The Confusion Matrix

The confusion matrix is a 2×2 grid showing exactly where the model gets things right and wrong:

```
                    Predicted
                    Non-Compliant    Compliant
Actual
Non-Compliant       TN               FP
Compliant           FN               TP
```

- **TN (True Negative)**: Non-compliant solicitation correctly identified as non-compliant. Good.
- **FP (False Positive)**: Non-compliant solicitation incorrectly flagged as compliant. Wastes reviewer time but not harmful.
- **FN (False Negative)**: Compliant solicitation missed — called non-compliant. This is the costly error.
- **TP (True Positive)**: Compliant solicitation correctly identified. This is what we want to maximize.

David saved two confusion matrix plots:
- `confusion_matrix.png` — evaluated on the full training data (optimistic, since the model saw this data)
- `confusion_matrix_dev.png` — evaluated on a 20% held-out test set with a different random seed (seed=99 vs training seed=42). This is the more trustworthy evaluation.

### Cross-Validation vs Hold-Out

David used two evaluation strategies:

**3-Fold Stratified Cross-Validation** (in `model.py`)

The data is split into 3 equal parts. The model trains on 2 parts and tests on 1, rotating three times so every sample gets tested exactly once. Synthetic compliant examples are added to training folds only — never test folds. This gives a robust estimate of model performance because every sample is tested.

The output looks like:
```
Fold    Compliant F1    Non-Compliant F1    Macro F1
1       0.XXX           0.XXX               0.XXX
2       0.XXX           0.XXX               0.XXX
3       0.XXX           0.XXX               0.XXX

Mean Compliant F1: 0.XXX +/- 0.XXX
```

The `+/- 0.XXX` is the standard deviation across folds. A low standard deviation means the model performs consistently regardless of which data it trains on. A high standard deviation means performance is unstable.

If Mean Compliant F1 drops below 0.60, David's code prints a warning suggesting parameter adjustments.

**20% Stratified Hold-Out** (in `hold_out_evaluation.py`)

A separate 20% of the data is held out using a different random seed (99) than training (42). The model never sees this data during training. This is the "trust these numbers" evaluation — it simulates how the model will perform on completely new solicitations.

The hold-out test set contains roughly:
- ~11 compliant solicitations
- ~45 non-compliant solicitations

Because the test set is small (especially for the compliant class), individual predictions have a big impact on the metrics. A single missed compliant solicitation can drop Compliant F1 significantly.

### What "Good" Looks Like

For this use case with 57 compliant examples:

| Metric | Poor | Acceptable | Good |
|--------|------|------------|------|
| Compliant F1 | < 0.60 | 0.60 - 0.80 | > 0.80 |
| Macro F1 | < 0.70 | 0.70 - 0.85 | > 0.85 |
| Compliant Recall | < 0.70 | 0.70 - 0.90 | > 0.90 |

Compliant Recall is especially important — it answers "what percentage of compliant solicitations are we catching?" A recall of 0.90 means we catch 9 out of 10. The ones we miss are the compliance gaps.

### The Confidence Score

When the model predicts, it also outputs a confidence score (0 to 1). In the pipeline output you see:

```json
"confidence": 1.0
```

This comes from `model.predict_proba()`, which returns the probability the model assigns to each class. A confidence of 1.0 means the model is very certain. Lower confidence (e.g., 0.55) means the model is borderline — these are the cases where human review is most valuable.

In practice, you could use the confidence score to prioritize reviews: high-confidence predictions can be auto-accepted, while low-confidence predictions get flagged for manual review.


---

## Actual Model Performance

### Full Dataset Evaluation (284 samples)

```
                 precision    recall  f1-score   support

Non-Compliant       1.00      0.97      0.98       227
    Compliant       0.89      0.98      0.93        57

     accuracy                           0.97       284
    macro avg       0.94      0.98      0.96       284
 weighted avg       0.97      0.97      0.97       284
```

| Metric | Score |
|--------|-------|
| Macro F1 | 0.958 |
| Weighted F1 | 0.972 |
| Compliant F1 | 0.933 |

**Confusion Matrix:**

```
                    Predicted
                    Non-Compliant    Compliant
Actual
Non-Compliant       220 (TN)         7 (FP)
Compliant             1 (FN)        56 (TP)
```

What this means:
- Out of 57 compliant solicitations, the model correctly identified 56. It missed exactly 1 (FN=1). That's 98% recall on the compliant class.
- Out of 227 non-compliant solicitations, 7 were incorrectly flagged as compliant (FP=7). Those 7 would go to a reviewer who'd quickly see they're not actually compliant. Minor cost.
- The 1 false negative is the only real concern — one compliant solicitation slipped through. In production, this means roughly 1 in 57 compliant solicitations (~1.8%) could be missed.

### Dev Hold-Out Evaluation (56 unseen samples)

This is the more trustworthy evaluation — the model never saw these samples during training. A different random seed (99 vs 42) was used to select the hold-out set.

```
                 precision    recall  f1-score   support

Non-Compliant       1.00      0.96      0.98        45
    Compliant       0.85      1.00      0.92        11

     accuracy                           0.96        56
    macro avg       0.92      0.98      0.95        56
 weighted avg       0.97      0.96      0.97        56
```

| Metric | Score |
|--------|-------|
| Macro F1 | 0.947 |
| Weighted F1 | 0.965 |
| Compliant F1 | 0.917 |

**Confusion Matrix:**

```
                    Predicted
                    Non-Compliant    Compliant
Actual
Non-Compliant       43 (TN)          2 (FP)
Compliant            0 (FN)         11 (TP)
```

What this means:
- **Zero false negatives on the hold-out set.** Every compliant solicitation was caught. 100% recall.
- 2 false positives — two non-compliant solicitations were flagged as compliant. These would be caught during human review.
- Compliant precision is 85% (11 out of 13 predictions of "compliant" were correct). The other 2 were the false positives.

### Summary

The model performs well on both evaluations. The key numbers:

| | Full Data | Hold-Out (unseen) |
|---|---|---|
| Compliant Recall | 98.2% (56/57) | 100% (11/11) |
| Compliant Precision | 88.9% (56/63) | 84.6% (11/13) |
| Compliant F1 | 0.933 | 0.917 |
| False Negatives | 1 | 0 |
| False Positives | 7 | 2 |

The model's strength is recall — it catches nearly every compliant solicitation. The tradeoff is a small number of false positives (non-compliant solicitations flagged as compliant), which are easily caught during human review. This is the right tradeoff for a compliance screening tool: it's better to over-flag than to miss.
