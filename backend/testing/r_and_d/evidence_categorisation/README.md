# Evidence Categorisation

Automated classification of research and policy documents into 8 hierarchical evidence categories using LLM-based analysis.

## Evidence Categories (Highest → Lowest)

1. **Systematic Review and Meta-Analysis** - Cochrane reviews, PRISMA systematic reviews
2. **RCTs and Quasi-Experimental Studies** - Randomized controlled trials, quasi-experimental designs
3. **Observational Research Studies** - Cohort, case-control, cross-sectional studies
4. **Modelling & Simulation** - Economic models, forecasting, scenario analysis
5. **Policy Syntheses & Guidance Documents** - White papers, policy briefs, guidance reports
6. **Qualitative & Contextual Evidence** - Interviews, focus groups, case studies, lived experience
7. **Expert Opinion and Commentary** - Editorials, commentaries, thought leadership
8. **Other (Non-evidence documents)** - Statistical bulletins, bills, administrative documents

## Quick Start

### 1. Prepare Input Data

Place your `references.csv` file in the `inputs/` directory. The CSV should contain:
- `title` - Document title
- `abstract_or_summary` - Document abstract or summary
- `source` - Source (e.g., "overton", "openalex")
- `document_type` - Document type
- `year` - Publication year (optional)

### 2. Run Classification

From the backend directory:

```bash
cd /Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/backend

# Basic usage
uv run python testing/r_and_d/evidence_categorisation/categorise_evidence.py \
  --input testing/r_and_d/evidence_categorisation/inputs/references.csv \
  --output testing/r_and_d/evidence_categorisation/outputs/categorised_evidence.csv

# With custom parameters
uv run python testing/r_and_d/evidence_categorisation/categorise_evidence.py \
  --input testing/r_and_d/evidence_categorisation/inputs/references.csv \
  --output testing/r_and_d/evidence_categorisation/outputs/categorised_evidence.csv \
  --model gpt-5-mini \
  --temperature 0.0 \
  --batch-size 10 \
  --max-concurrent 5
```

### 3. Review Results

The output CSV will contain all original columns plus:
- `evidence_category` - Assigned evidence category
- `evidence_confidence` - Confidence score (0.0-1.0)
- `category_reasoning` - Brief explanation for classification

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | (required) | Path to input references.csv file |
| `--output` | (required) | Path to output categorized CSV file |
| `--model` | `gpt-4o-mini` | LLM model to use |
| `--temperature` | `0.0` | Temperature for LLM (0.0 = deterministic) |
| `--batch-size` | `10` | Number of documents per batch |
| `--max-concurrent` | `5` | Maximum concurrent API calls |

## Output Summary

The script prints a summary after completion:

```
CLASSIFICATION SUMMARY
==============================================================

Total documents classified: 150

Category distribution:
Policy Syntheses & Guidance Documents    45
Observational Research Studies           38
Expert Opinion and Commentary            25
RCTs and Quasi-Experimental Studies      18
Systematic Review and Meta-Analysis      12
Qualitative & Contextual Evidence        8
Modelling & Simulation                   4

Average confidence: 0.824
Low confidence (<0.6) count: 12

==============================================================
```

## Analysis Tips

### Reviewing Low Confidence Classifications

Filter for documents with `evidence_confidence < 0.6` to identify ambiguous cases:

```python
import pandas as pd

df = pd.read_csv('outputs/categorised_evidence.csv')
low_confidence = df[df['evidence_confidence'] < 0.6]
print(low_confidence[['title', 'evidence_category', 'evidence_confidence', 'category_reasoning']])
```

### Category Distribution Analysis

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('outputs/categorised_evidence.csv')

# Distribution by category
df['evidence_category'].value_counts().plot(kind='barh')
plt.title('Evidence Category Distribution')
plt.xlabel('Count')
plt.tight_layout()
plt.savefig('outputs/category_distribution.png')
```

## Validation Workflow (with Argilla)

To validate and improve the classifier, you can create a labeled validation set using Argilla.

### Step 1: Start Argilla

```bash
# Using Docker
docker run -d --name argilla -p 6900:6900 argilla/argilla-quickstart:latest

# Or install locally
pip install argilla
```

Access Argilla UI at http://localhost:6900 (default credentials: `admin` / `12345678`)

### Step 2: Load Documents to Argilla

```bash
cd /Users/aidan.kelly/nesta/discovery/discovery_policy_atlas/backend

# Load all documents into Argilla for labeling
uv run python testing/r_and_d/evidence_categorisation/setup_argilla_v2.py \
  --csv testing/r_and_d/evidence_categorisation/inputs/references.csv \
  --dataset-name evidence-categorization \
  --api-key admin.apikey
```

### Step 3: Label in Argilla UI

1. Open http://localhost:6900
2. Navigate to the `evidence-categorization` dataset
3. Review each document:
   - Read title and abstract
   - Select evidence category
   - Rate your confidence (1-5)
   - Mark difficulty (Easy/Medium/Hard)
   - Add notes for edge cases
4. Submit each annotation

**Tips:**
- Focus on what the document **does**, not what it references
- Flag ambiguous cases in notes
- Use the evidence definitions in the guidelines panel

### Step 4: Export Labeled Data

```bash
# Export all submitted labels
uv run python testing/r_and_d/evidence_categorisation/export_from_argilla_v2.py \
  --dataset-name evidence-categorization \
  --output testing/r_and_d/evidence_categorisation/inputs/validation_set.csv \
  --api-key admin.apikey
```

### Step 5: Validate Classifier Performance

```bash
# Run classifier on validation set
uv run python testing/r_and_d/evidence_categorisation/categorise_evidence.py \
  --input testing/r_and_d/evidence_categorisation/inputs/validation_set.csv \
  --output testing/r_and_d/evidence_categorisation/outputs/validation_results.csv

# Then compare predictions vs ground_truth_category in Python
```

**Validation analysis example:**

```python
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

df = pd.read_csv('outputs/validation_results.csv')

# Compare predictions vs ground truth
y_true = df['ground_truth_category']
y_pred = df['evidence_category']

print(classification_report(y_true, y_pred))
print("\nConfusion Matrix:")
print(confusion_matrix(y_true, y_pred))

# Analyze disagreements
disagreements = df[y_true != y_pred]
print(f"\nDisagreement rate: {len(disagreements)/len(df):.2%}")
```

## Files

- `categorise_evidence.py` - Main classification script
- `prompts.py` - Classification prompts and category definitions (8 categories)
- `setup_argilla_v2.py` - Load documents into Argilla for labeling
- `export_from_argilla_v2.py` - Export labeled data from Argilla
- `test_categorisation.py` - Test examples
- `DESIGN.md` - Design documentation
- `inputs/` - Input data directory
- `outputs/` - Classification results directory

## Requirements

- Python 3.11+
- OpenAI API key (in `.env` file)
- Dependencies installed via `uv sync`
- Argilla (optional, for validation workflow)

## Troubleshooting

**Import errors**: Make sure you're running from the backend directory so the script can find `app` modules.

**API errors**: Check your OpenAI API key is set in `.env` file.

**Out of memory**: Reduce `--max-concurrent` parameter to limit parallel API calls.

**Argilla connection errors**: Check Argilla is running and API URL/key are correct.
