#!/bin/bash
# Run all 30 evidence categorisation experiments
# 5 models × 2 prompts × 3 datasets = 30 experiments

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODELS=("gpt-5-mini" "gpt-5" "gpt-5.2")
PROMPTS=("variant_a" "variant_b")
DATASETS=("run_child_obesity" "run_home_heating" "run_intervention_home_learning")

total=$((${#MODELS[@]} * ${#PROMPTS[@]} * ${#DATASETS[@]}))
current=0

echo "========================================"
echo "Evidence Categorisation Experiments"
echo "========================================"
echo "Models:   ${MODELS[*]}"
echo "Prompts:  ${PROMPTS[*]}"
echo "Datasets: ${DATASETS[*]}"
echo "Total experiments: $total"
echo "========================================"
echo ""

# Run from backend directory for proper imports
cd ../../../../

for dataset in "${DATASETS[@]}"; do
    for prompt in "${PROMPTS[@]}"; do
        for model in "${MODELS[@]}"; do
            current=$((current + 1))
            echo ""
            echo "========================================"
            echo "[$current/$total] $model / $prompt / $dataset"
            echo "========================================"

            uv run python testing/r_and_d/evidence_categorisation/experiments/run_experiment.py \
                --model "$model" \
                --prompt "$prompt" \
                --dataset "$dataset"

            echo "✓ Completed [$current/$total]"
        done
    done
done

echo ""
echo "========================================"
echo "ALL $total EXPERIMENTS COMPLETE!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Collect results: python experiments/collect_results.py"
echo "  2. Generate plots:  python experiments/visualize_results.py"
