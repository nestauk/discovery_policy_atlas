# Evaluation System - Updated with High Priority Metrics

## 🎉 What's New

All **high priority metrics** from the evaluation plan have been successfully implemented:

### ✅ Added Metrics

**2.1 Reference Retrieval:**
- ✅ **Precision** - Search efficiency metric
- ✅ **Recall curves** - Visual identification of optimal retrieval depth

**2.2 Relevance Screening:**
- ✅ **Accuracy** - Overall screening correctness  
- ✅ **Sensitivity** - Ability to identify relevant papers
- ✅ **Specificity** - Ability to reject irrelevant papers
- ✅ **Confusion Matrix** - TP, TN, FP, FN values

### ✅ New Tools

1. **`plot_recall_curves.py`** - Generates recall curve visualizations
2. **`run_full_evaluation.py`** - Runs complete evaluation pipeline
3. **`METRICS_GUIDE.md`** - Comprehensive metrics documentation

## 🚀 Quick Start

### Run Complete Evaluation

```bash
cd backend/test/evals

# Option 1: Full pipeline (retrieval → comparison → visualization)
python run_full_evaluation.py

# Option 2: Just comparison and visualization (skip retrieval)
SKIP_RETRIEVAL=true python run_full_evaluation.py

# Option 3: Different baseline
BASELINE_CSV=bibliographies_standardized/"Food Advertising.csv" \
python run_full_evaluation.py
```

### View Results

```bash
# View metrics with all new columns
cat retrieval_eval/compare/top_100/metrics.csv

# View recall curves
open retrieval_eval/recall_curves.png

# Check optimal retrieval depths
python plot_recall_curves.py
```

## 📊 New Metrics Output

### Console Output
```
title_abstract baseline count: 6
title_abstract matched: 5
title_abstract recall: 83.33%
title_abstract precision: 2.50%                    ← NEW
title_abstract screening accuracy: 100.00%          ← NEW
title_abstract screening sensitivity: 100.00%       ← NEW
title_abstract screening specificity: 0.00%         ← NEW
```

### CSV Output
```csv
run_label,subset,baseline_count,matched_count,recall_pct,precision_pct,
screening_accuracy_pct,screening_sensitivity_pct,screening_specificity_pct,
screening_tp,screening_tn,screening_fp,screening_fn

all,title_abstract,6,5,83.33,2.50,100.00,100.00,0.00,5,0,0,0
all,full_text,1,1,100.00,0.50,100.00,100.00,0.00,1,0,0,0
```

## 📁 Files Overview

### Core Scripts
- `retrieval_relevance_only.py` - Search & classify papers
- `compare_retrieval_to_baseline.py` - **Updated with new metrics**
- `plot_recall_curves.py` - **New: Visualization**
- `run_full_evaluation.py` - **New: Full pipeline**

### Standardized Baselines
- `bibliographies_standardized/*.csv` - 26 standardized bibliographies
- All have consistent format: `title`, `title_abstract_screen`, `full_text_screen`

### Documentation
- `HOW_IT_WORKS.md` - System workflow
- `QUICK_REFERENCE.md` - Command cheat sheet
- `METRICS_GUIDE.md` - **New: Detailed metrics guide**
- `EVALUATION_PLAN_COMPARISON.md` - Plan vs implementation
- `IMPLEMENTATION_SUMMARY.md` - **New: What was added**

## 🎯 Metrics Alignment with Evaluation Plan

| Plan Metric | Implementation | Status |
|------------|----------------|--------|
| **Recall (2.1)** | `recall_pct` | ✅ Complete |
| **Precision (2.1)** | `precision_pct` | ✅ Complete |
| **Seminal Coverage (2.1)** | `full_text` recall | ✅ Complete |
| **Recall Curves (2.1)** | `plot_recall_curves.py` | ✅ Complete |
| **Accuracy (2.2)** | `screening_accuracy_pct` | ✅ Complete |
| **Sensitivity (2.2)** | `screening_sensitivity_pct` | ✅ Complete |
| **Specificity (2.2)** | `screening_specificity_pct` | ✅ Complete |

## 📈 Example Workflow

```bash
# 1. Standardize bibliographies (if not done)
python standardize_bibliographies.py

# 2. Run full evaluation
python run_full_evaluation.py

# 3. Review metrics
cat retrieval_eval/compare/top_*/metrics.csv | column -t -s,

# 4. View recall curves
open retrieval_eval/recall_curves.png

# 5. Identify optimal retrieval depth
python plot_recall_curves.py
```

## 💡 Understanding the Metrics

### Recall (Primary Metric)
- **What:** % of gold-standard papers found by retrieval
- **Target:** >85%
- **Example:** Found 8 of 10 papers → 80% recall

### Precision
- **What:** % of retrieved papers in gold-standard
- **Note:** Often low (<10%) - this is normal
- **Example:** 8 matches in 100 retrieved → 8% precision

### Screening Accuracy
- **What:** % of screening decisions that match human review
- **Target:** >80%
- **Example:** 75 correct out of 90 → 83% accuracy

### Screening Sensitivity
- **What:** % of relevant papers correctly identified by LLM
- **Target:** >90%
- **Critical:** Missing relevant papers is serious

### Screening Specificity
- **What:** % of irrelevant papers correctly rejected by LLM
- **Target:** >70%
- **Context:** Lower values may be acceptable if casting wider net

See `METRICS_GUIDE.md` for detailed explanations.

## 🔍 Troubleshooting

### No matplotlib error
```bash
# Install visualization dependencies
pip install matplotlib
```

### Missing references.csv
```bash
# Run retrieval first
python retrieval_relevance_only.py
```

### Low precision values
This is **expected and normal** because:
- Gold standards are small (10-50 papers)
- Retrieval returns 100-1000 papers
- Many retrieved papers may be relevant but not in specific gold standard

Focus on:
- High recall (found the papers)
- High sensitivity (correctly identified them)
- Reasonable specificity (not too many false positives)

## 📚 Documentation

For detailed information, see:

1. **`METRICS_GUIDE.md`** - Complete metrics reference
2. **`HOW_IT_WORKS.md`** - System architecture
3. **`QUICK_REFERENCE.md`** - Command reference
4. **`IMPLEMENTATION_SUMMARY.md`** - What was added

## ✅ Verification

Test the implementation:

```bash
# 1. Run comparison
python compare_retrieval_to_baseline.py

# 2. Check new metrics exist
head -1 retrieval_eval/compare/metrics.csv

# Expected columns:
# recall_pct, precision_pct, screening_accuracy_pct,
# screening_sensitivity_pct, screening_specificity_pct

# 3. Generate visualization
python plot_recall_curves.py

# 4. Verify plot created
ls -lh retrieval_eval/recall_curves.png
```

## 🎯 Next Steps (Optional)

If time permits, consider:

### Medium Priority
- Confidence scores from LLM
- LLM-as-judge for reasoning evaluation
- Batch runner for multiple queries

### Low Priority
- Interactive dashboard
- Excel export
- Qualitative review tool

---

## Summary

✅ **All high priority metrics implemented**
- 2.1: Recall, Precision, Recall Curves
- 2.2: Accuracy, Sensitivity, Specificity

✅ **Complete tooling**
- Automated evaluation pipeline
- Visual recall curves
- Comprehensive metrics

✅ **Full documentation**
- Metrics guide
- Implementation summary
- Quick reference

The evaluation system is now complete and aligned with the evaluation plan! 🎉








