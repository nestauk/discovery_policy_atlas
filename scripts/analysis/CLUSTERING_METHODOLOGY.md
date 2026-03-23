# Clustering Methodology: Agency & Resilience Theme Analysis

## What this pipeline does

We take intervention and outcome themes extracted by Policy Atlas from academic and grey literature, and group them into meaningful clusters. The goal is to answer: **what types of interventions and outcomes keep appearing across different searches, and where does the strongest evidence sit?**

The pipeline runs in four stages:

1. **Embed** -- turn text descriptions into numerical vectors that capture meaning
2. **Cluster** -- group similar vectors together automatically
3. **Label & organise** -- use an LLM to give clusters human-readable names and assign them to higher-level themes
4. **Deduplicate & visualise** -- detect cross-search overlaps and produce charts

---

## Stage 1: Text Embedding

### What we do

Each intervention or outcome has a text description (e.g. "Community-based digital literacy programmes targeting older adults"). We convert these into 384-dimensional numerical vectors using a **sentence embedding model**.

### Model: `all-MiniLM-L6-v2`

This is a lightweight, well-established model from the [Sentence Transformers](https://www.sbert.net/) library. It was trained to produce vectors where semantically similar sentences end up close together in vector space. For example, "digital skills training for elderly residents" and "technology literacy programmes for older adults" would have vectors pointing in nearly the same direction.

### Why this model?

- **Fast and lightweight** -- runs locally on a laptop in seconds, no API calls needed
- **Good quality for short texts** -- performs well on sentence-level similarity tasks, which is exactly what our intervention/outcome descriptions are
- **Well-benchmarked** -- consistently ranks well on semantic textual similarity benchmarks
- **Deterministic** -- same input always produces the same vector, so results are reproducible

### What the vectors look like

Each description becomes a list of 384 numbers. You can think of each number as capturing one aspect of meaning. Two descriptions about similar topics will have vectors that point in roughly the same direction (high cosine similarity), while unrelated descriptions will point in different directions (low cosine similarity).

---

## Stage 2: Clustering with BERTopic

### What we do

We use **BERTopic** to automatically discover groups of similar interventions (or outcomes). BERTopic is a modular topic modelling framework that chains together three steps: dimensionality reduction, clustering, and topic representation.

### Step 2a: Dimensionality Reduction (UMAP)

**Problem:** Our vectors have 384 dimensions. Clustering algorithms struggle with high-dimensional data because distances become less meaningful (the "curse of dimensionality"). Points that are genuinely similar can appear far apart.

**Solution:** We use **UMAP** (Uniform Manifold Approximation and Projection) to compress the 384 dimensions down to a much smaller number (2-5, depending on corpus size) while preserving the neighbourhood structure -- i.e. points that were close together in 384D stay close in 5D.

**Parameters:**
| Parameter | Value | Why |
|---|---|---|
| `n_neighbors` | `min(10, max(3, corpus_size - 1))` | Controls the balance between local and global structure. Lower values preserve fine-grained local clusters. We adapt to corpus size so small datasets don't break. |
| `n_components` | `min(5, max(2, corpus_size // 10))` | How many dimensions to keep. More components = more information preserved but harder for HDBSCAN to cluster. Adapts to corpus size. |
| `min_dist` | `0.0` | How tightly UMAP packs points together. Zero allows tight clusters, which is what we want for subsequent clustering. |
| `metric` | `cosine` | Matches how the embeddings were trained -- cosine similarity is the natural distance measure for sentence embeddings. |
| `random_state` | `42` | Makes results reproducible across runs. |

### Step 2b: Clustering (HDBSCAN)

**What it does:** HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise) finds groups of points that are densely packed together, and labels sparse/isolated points as outliers (cluster ID = -1).

**Why HDBSCAN over alternatives?**
- **Doesn't require specifying the number of clusters** -- unlike K-means, you don't need to guess how many groups exist. HDBSCAN discovers this from the data.
- **Handles noise** -- points that don't clearly belong to any cluster get labelled as outliers rather than being forced into a bad fit. This is important because not every intervention description will have close neighbours.
- **Finds clusters of varying sizes** -- unlike K-means which tends to produce equal-sized clusters.

**Parameters:**
| Parameter | Value | Why |
|---|---|---|
| `min_cluster_size` | 3 (interventions) / 4 (outcomes) | The smallest group we'd consider a real cluster. Set lower for interventions because there are fewer of them. |
| `min_samples` | `1` | Controls how conservative clustering is. Setting to 1 is the least conservative -- a point just needs one close neighbour to potentially be in a cluster. We use this because our corpus is small and we'd rather over-cluster (and merge later) than miss valid groups. |
| `metric` | `euclidean` | Standard distance metric in the reduced UMAP space (UMAP output is designed for Euclidean distance). |
| `cluster_selection_method` | `leaf` | Selects the finest-grained clusters from the hierarchy. We prefer more granular clusters because the LLM merge step (Stage 3) can combine them if needed. |

### Step 2c: TF-IDF Topic Representation

BERTopic extracts TF-IDF keywords for each cluster -- the words that are most distinctive to that cluster compared to others. These serve as a fallback label if LLM labelling is skipped, and are also fed into the LLM prompt as additional context.

---

## Stage 3: LLM-Powered Labelling and Organisation

### Why use an LLM at all?

TF-IDF keywords are useful but limited. A cluster might have keywords like ["digital", "literacy", "elderly", "training", "access"] -- technically accurate but not a natural category name. An LLM can read the actual descriptions and member names and produce something like "Digital Inclusion for Older Adults", which is immediately useful in a policy report.

### Step 3a: Cluster Labelling

**Model:** `gpt-5.4-mini` (temperature 0.3 for consistency)

We send **all clusters in a single prompt** so the LLM can see the full landscape and make labels distinctive. This is important because multiple clusters might touch on similar domains (e.g. two clusters about mental health) -- the LLM is instructed to capture what makes each cluster *different* from the others.

**What goes into the prompt for each cluster:**
- Up to 10 member names (e.g. intervention names)
- Up to 6 description snippets (250 chars each)
- Top 8 TF-IDF keywords

**Fallback chain:** If the batch prompt fails, we fall back to per-cluster single prompts, then to TF-IDF keywords (top 5 words).

### Step 3b: Merge Review

**Problem:** HDBSCAN with `cluster_selection_method="leaf"` deliberately produces fine-grained clusters. Sometimes two clusters are really the same concept split by phrasing differences.

**Solution:** We compute the cosine similarity between every pair of cluster centroids (the average embedding of all members). For pairs above a similarity floor of **0.55**, we ask an LLM to judge whether they should merge.

**Model:** `gpt-5.4-mini` (temperature 0.1 for near-deterministic decisions)

The LLM sees both clusters' labels, members, and sample descriptions, and returns a yes/no merge decision with a reason. When merges are accepted, the pipeline:
1. Reassigns all members of the absorbed cluster to the surviving cluster
2. Generates a new combined label via LLM
3. Recomputes cross-cluster similarities

**Transitive merges** are handled: if cluster A merges into B and B merges into C, all members end up in C.

### Step 3c: Meta-Theme Assignment

**Problem:** Even after merging, we might have 10-20 clusters. For a high-level overview, we want to group these into broader themes (e.g. "Community Resilience & Social Capital").

**Model:** `gpt-5.4` (the full model, not mini -- this is the most important judgement call in the pipeline, so we use the strongest model)

**How it works:** We provide a set of **six reference themes** drawn from the Agency & Resilience brief:

1. **Early years & family foundations** -- Build resilience upstream by improving the conditions in which children grow up
2. **Mental health, behaviour & individual capability** -- Increase people's ability to regulate, learn, decide and persist under pressure
3. **Community resilience & social capital** -- Resilience in relationships, trust and local institutions
4. **Climate & place-based adaptation** -- Help places adapt to climate risk in ways that increase resilience and democratic legitimacy
5. **Digital & information resilience** -- Whether people and institutions can navigate digital systems safely and sovereignly
6. **Institutional & governance reform** -- Whether institutions can think long-term, act preventively and share power

Critically, **these are suggestions, not a closed set**. The LLM is explicitly instructed to create new themes if a cluster doesn't fit any reference theme. Emergent themes are tagged as `[NEW]` in all outputs so they're easy to spot.

---

## Stage 4: Deduplication, Filtering, and Outputs

### Data Filtering

Before any clustering happens, we apply two filters:

**Geography Context Fit:** Each intervention has a geography assessment from the synthesis (e.g. "match", "comparable", "limited applicability"). We keep only interventions where the geography context is "comparable" or "match", since the brief focuses on UK-applicable evidence. Outcomes linked to filtered-out interventions are also dropped.

**Positive Verdicts (for certain outputs):** Some charts and the per-meta-theme CSV exports filter to positive-verdict outcomes only (`suggested_positive`, `evidenced_positive`, `well_evidenced_positive`). This surfaces "what works" rather than the full evidence landscape. The unfiltered views are also generated for completeness.

### Cross-Search Duplicate Detection

**Problem:** Multiple search queries often surface the same or very similar interventions/outcomes. For example, a search for "community resilience programmes" and one for "social capital interventions" might both find the same community hub initiative.

**Method:** We compute pairwise cosine similarity between all embeddings, then report pairs from *different* searches that exceed a similarity threshold of **0.70** (configurable). A similarity of 0.70+ between sentence embeddings generally indicates the texts are saying very similar things.

These are surfaced as a table (sorted by similarity) and a network graph visualisation.

### Source Document Deduplication

**Problem:** When the same study appears in multiple search results (because it's relevant to multiple queries), it gets counted once per search. Summing "Source Documents" across searches within a meta-theme double-counts these shared studies.

**How we solve it:** Each study has a stable `doc_id` generated deterministically:
1. If the paper has a DOI, the normalised DOI is the ID (same paper = same ID regardless of which search found it)
2. If no DOI, the source platform ID (e.g. OpenAlex ID) is used
3. Fallback: a hash of title + year

In the meta-theme bar charts, we collect all `doc_id` values per meta-theme and count **unique** ones. The chart reports the dedup impact (e.g. "142 raw docs -> 98 unique docs, 44 duplicates removed").

### Outputs

| Output | What it shows |
|---|---|
| **theme_clusters.xlsx** | Multi-sheet spreadsheet with cluster reports, member detail, similarity matrices, and duplicate pairs |
| **UMAP scatter plots** | 2D projection of all interventions/outcomes coloured by cluster -- shows how themes group spatially |
| **Search x Cluster heatmaps** | Which search queries found items in which clusters (with hierarchical ordering) |
| **Meta-theme heatmaps** | Same but aggregated to meta-theme level, with optional positive-verdict filtering |
| **Meta-theme bar charts** | Total evidence per meta-theme, stacked by evidence category, with deduplicated doc counts |
| **Drilldown bar charts** | One per meta-theme, showing the clusters within it stacked by verdict strength |
| **Duplicate network graphs** | Visual network of near-duplicate items across searches |
| **Per-meta-theme CSVs** | One CSV per meta-theme with positive-verdict outcomes, their cluster label, linked intervention, and source studies with top-line summaries |

---

## Key Design Decisions and Trade-offs

### Why cluster first, then label with LLM (rather than asking the LLM to cluster)?

LLMs are good at understanding text but bad at maintaining consistency across large sets. If you ask an LLM to categorise 80 outcomes one at a time, you'll get inconsistent groupings -- the same concept might get different labels on different calls. By clustering the embeddings first (which is deterministic and considers all items simultaneously), we get stable, consistent groups. The LLM then just needs to name and organise what's already been found.

### Why `leaf` cluster selection + merge review instead of a coarser clustering?

We deliberately over-segment first and then selectively merge. This is more conservative than starting coarse:
- **Over-segmenting** risks splitting genuine groups, but the merge review catches this
- **Under-segmenting** risks lumping different concepts together, and there's no automated step to split them back apart
- The merge review also produces an audit trail (the LLM gives a reason for each merge decision)

### Why two different LLM models?

- **gpt-5.4-mini** for labelling and merge decisions: these are simpler tasks where a smaller, faster, cheaper model performs well
- **gpt-5.4** for meta-theme assignment: this requires the most nuanced judgement (deciding whether a cluster fits an existing theme or needs a new one), so we use the strongest available model

### Why 0.70 for duplicate detection but 0.55 for merge review?

These serve different purposes:
- **Duplicate detection (0.70)**: identifies items that are essentially the same thing described differently. At 0.70+, false positives are rare.
- **Merge review (0.55)**: identifies clusters that *might* be related enough to combine. The threshold is lower because it's just a screening step -- the LLM makes the actual merge/no-merge decision. We'd rather send a borderline pair for review than miss a valid merge. Often in the end, we don't do this.

---

## Reproducibility

- Embedding model is deterministic (same input = same vector)
- UMAP uses `random_state=42`
- HDBSCAN is deterministic given the same input
- LLM calls are not perfectly deterministic
- All intermediate results (embeddings, topics, labels, meta-theme assignments) are cached to `.cluster_cache.pkl`, so outputs can be regenerated from cached results without re-running LLM calls
