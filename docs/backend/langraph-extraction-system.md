# LangGraph Document Extraction System

## Overview

This document describes the implementation of a LangGraph-based research paper extraction system designed to extract structured information from academic papers with high accuracy and grounding. The system implements a minimal 4-stage workflow following the MECE (Mutually Exclusive, Collectively Exhaustive) principle.

## Architecture

### Core Components

1. **Data Models** (`schemas_langchain.py`) - Pydantic models for structured extraction
2. **Prompts** (`prompts_langchain.py`) - LangChain prompt templates with strong grounding requirements
3. **Workflow** (`workflow_langchain.py`) - LangGraph state machine orchestrating the extraction pipeline
4. **Service** (`extractor_langchain.py`) - High-level service interface for document processing

### Workflow Design Principles

- **Minimal Orchestration**: 4 sequential stages + validation (5 total steps)
- **Index-based References**: Uses simple integer indices instead of complex IDs
- **Verbatim Grounding**: Every extracted item must include exact quotes from source text
- **MECE Enforcement**: Prompts ensure mutually exclusive and collectively exhaustive extractions
- **Post-hoc Validation**: Fuzzy matching validates quote authenticity after extraction

## 4-Stage Workflow

### Stage A: Issues Extraction
**Purpose**: Extract 1-3 key problem statements that motivated the research

**Input**: Full paper text
**Output**: List of `IssueItem` objects

```python
class IssueItem(BaseModel):
    idx: int                    # Sequential index
    label: str                  # Concise problem statement
    explanation: str            # 1-2 sentence LLM interpretation
    supporting_quote: str       # Verbatim quote from paper
    quote_location: str        # Page/section reference
```

**Key Rules**:
- Focus on broader problems, not study-specific findings
- Avoid generic research gaps ("need for more research")
- Merge overlapping issues to maintain MECE

### Stage B: Interventions Extraction
**Purpose**: Extract 2-6 active interventions/programs evaluated or proposed

**Input**: Full paper text
**Output**: List of `InterventionItem` objects

```python
class InterventionItem(BaseModel):
    idx: int                          # Sequential index
    name: str                         # Intervention name
    type: str                         # Intervention type/category
    description: str                  # Description based on quote
    study_type: str                   # Maryland Scientific Methods Scale (a-h)
    country: Optional[str]            # Where intervention was conducted
    population_intervened: Optional[str]  # Who received intervention
    population_measured: Optional[str]    # Who was measured
    population_demographics: Optional[str] # Demographics details
    supporting_quote: str             # Verbatim quote
    quote_location: str              # Page/section reference
```

**Key Rules**:
- Focus on active interventions only (exclude control groups)
- Use Maryland Scientific Methods Scale for study classification
- Include detailed population characteristics

### Stage C: Mapping Extraction
**Purpose**: Link issues to interventions with grounded rationale

**Input**: Full paper text + extracted issues + extracted interventions
**Output**: List of `MappingItem` objects

```python
class MappingItem(BaseModel):
    issue_idx: int              # Reference to issue
    intervention_idx: int       # Reference to intervention
    rationale: str             # Why intervention addresses issue
    supporting_quote: str      # Verbatim quote supporting connection
    quote_location: str       # Page/section reference
```

### Stage D: Results Extraction (Per-Intervention Loop)
**Purpose**: Extract 1-5 results for each intervention separately

**Input**: Full paper text + one intervention at a time
**Output**: List of `ResultItem` objects

```python
class ResultItem(BaseModel):
    intervention_idx: int                           # Reference to intervention
    outcome_variable: str                          # What was measured
    effect_direction: Literal["increase", "decrease", "null"]  # Direction of effect
    effect_size_type: Optional[str]               # Type of effect size
    effect_size: Optional[str]                    # Numerical effect size
    uncertainty: Optional[str]                    # Confidence intervals, etc.
    p_value: Optional[str]                        # Statistical significance
    sample_size: Optional[str]                    # Sample size for result
    subgroup_or_dose: Optional[str]              # Subgroup or dose details
    result_text: str                              # Human-readable summary
    supporting_quote: str                         # Verbatim quote
    quote_location: str                          # Page/section reference
```

**Key Rules**:
- Process each intervention separately to maintain focus
- Focus on primary results vs. control/baseline
- Exclude control group results unless they are the main finding
- Prefer explicit statistics when available

### Stage E: Validation and Filtering
**Purpose**: Post-hoc validation to ensure data quality

**Process**:
1. **Quote Validation**: Use fuzzy matching to verify quotes exist in source text
2. **Reference Validation**: Ensure all index references are valid
3. **Cascade Filtering**: Remove downstream items if upstream items are filtered

**Fuzzy Matching Algorithm**:
```python
def _fuzzy_quote_match(self, quote: str, full_text: str, threshold: float = 0.7) -> bool:
    # 1. Try exact substring match (fastest)
    # 2. Normalize whitespace and try again
    # 3. For long quotes (>50 chars): word overlap analysis
    # 4. For short quotes: key phrase matching
```

## LangGraph Implementation

### State Management
```python
class WorkflowState(TypedDict):
    paper_id: str                    # Document identifier
    full_text: str                   # Complete paper text
    issues: List[IssueItem]          # Accumulated issues
    interventions: List[InterventionItem]  # Accumulated interventions
    mappings: List[MappingItem]      # Accumulated mappings
    results: List[ResultItem]       # Accumulated results
    error: str | None               # Error tracking
```

### Node Structure
```python
workflow = StateGraph(WorkflowState)

# Sequential pipeline
workflow.add_node("extract_issues", self._extract_issues)
workflow.add_node("extract_interventions", self._extract_interventions)
workflow.add_node("extract_mappings", self._extract_mappings)
workflow.add_node("extract_results", self._extract_results)
workflow.add_node("validate_and_filter", self._validate_and_filter)

# Linear flow
workflow.set_entry_point("extract_issues")
workflow.add_edge("extract_issues", "extract_interventions")
workflow.add_edge("extract_interventions", "extract_mappings")
workflow.add_edge("extract_mappings", "extract_results")
workflow.add_edge("extract_results", "validate_and_filter")
workflow.add_edge("validate_and_filter", END)
```

### Error Handling
- **Node-level**: Each node catches exceptions and sets error state
- **Workflow-level**: Final state checked for errors before returning results
- **Graceful Degradation**: Returns empty bundle on total failure
- **Partial Success**: Individual stage failures don't halt entire workflow

## Prompt Engineering Strategy

### Universal System Prompt
Applied to all stages, enforces:
- **Verbatim Quotes**: "CRITICAL: Every supporting_quote MUST be copied EXACTLY..."
- **Strict JSON**: No explanations, only structured output
- **MECE Principle**: Mutually exclusive, collectively exhaustive
- **Grounding Requirement**: Every item must have supporting quote

### Stage-Specific Prompts
Each stage has tailored instructions:
- **Clear Task Definition**: Specific extraction goals
- **Schema Specification**: Exact JSON format required
- **Domain Rules**: Field-specific guidance (e.g., Maryland Scale for study types)
- **Quality Guidelines**: Focus areas and exclusion criteria

### Example Prompt Structure
```python
ISSUES_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),  # Universal grounding rules
    ("human", """Task: Extract 1–3 key PROBLEM STATEMENTS/ISSUES...
    
    Schema:
    {"issues":[{"idx":0,"label":"...","explanation":"...","supporting_quote":"...","quote_location":"..."}], "coverage_note":"string|null"}
    
    Rules:
    - MECE: Merge overlaps; avoid duplicates...
    - Focus on BROADER PROBLEMS...
    - DO NOT include study-specific findings...
    
    Paper text:
    {full_text}""")
])
```

## Quality Assurance Features

### 1. Verbatim Quote Enforcement
- System prompt emphasizes exact copying
- Fuzzy matching validates post-extraction
- Failed quotes trigger item removal

### 2. MECE Principle Application
- Prompts explicitly request MECE compliance
- Guidance on merging overlapping items
- Coverage notes for gaps in exhaustiveness

### 3. Index-based Integrity
- Simple integer indices avoid complex ID management
- Validation ensures all references exist
- Cascade filtering maintains referential integrity

### 4. Multi-level Validation
- **Syntactic**: Pydantic model validation
- **Semantic**: Quote grounding validation
- **Referential**: Index validity checking

## Performance Characteristics

### Latency
- **Sequential Processing**: ~15-30 seconds per paper
- **LLM Calls**: 4 main stages + 1 per intervention for results
- **Validation**: Fast local processing

### Accuracy
- **High Grounding**: Fuzzy matching ensures quote authenticity
- **Domain-Specific**: Prompts tuned for research paper structure
- **Iteratively Refined**: Based on real paper testing

### Scalability
- **Stateless**: Each paper processed independently
- **Async Support**: Built with async/await throughout
- **Error Isolation**: Individual paper failures don't affect batch

## Usage Example

```python
from app.services.analysis.extractor_langchain import LangChainExtractorService

# Initialize service
extractor = LangChainExtractorService()

# Process documents
documents = [
    {"doc_id": "paper1", "full_text": "...", "source": "journal", "year": 2023}
]

# Extract structured data
results = await extractor.extract_for_documents(documents)

# Export to CSV
await extractor.write_csvs(results, "output_dir", "run_001")
```

## Configuration

### Environment Variables
```bash
OPENAI_API_KEY=sk-...  # Required for LLM access
```

### Model Configuration
```python
ExtractionWorkflow(
    model="gpt-4o-mini",    # Fast, cost-effective model
    temperature=0.0         # Deterministic outputs
)
```

## Testing and Validation

### Test Papers
- Real research papers from multiple domains
- Various document structures (RCTs, meta-analyses, guidelines)
- Different lengths and complexity levels

### Quality Metrics
- **Grounding Rate**: % of extracted items with valid quotes
- **Completeness**: Coverage of key paper elements
- **Accuracy**: Manual validation of extracted content

### Example Results
From `doi.org_10.1016_j.jaac.2012.08.003.txt`:
- 3 issues extracted (early autism detection, intervention effectiveness, parent training)
- 1 intervention (P-ESDM parent training)
- 3 mappings linking issues to intervention
- 5 results covering primary outcomes
- 100% quote grounding validation pass rate

## Future Enhancements

### Potential Improvements
1. **Parallel Results Extraction**: Process multiple interventions simultaneously
2. **Section-Aware Processing**: Route different sections to specialized prompts
3. **Table/Figure Extraction**: Enhanced handling of structured data
4. **Cross-Paper Harmonization**: Vocabulary standardization across papers
5. **Active Learning**: Incorporate user feedback for prompt refinement

### Scaling Considerations
1. **Chunking Strategy**: Handle very long papers (>100k tokens)
2. **Caching Layer**: Cache intermediate results for re-processing
3. **Batch Processing**: Optimize for large document collections
4. **Quality Monitoring**: Automated quality score tracking

## Conclusion

The LangGraph extraction system provides a robust, well-grounded approach to structured information extraction from research papers. Its combination of careful prompt engineering, multi-stage validation, and principled workflow design ensures high-quality, auditable outputs suitable for evidence synthesis and meta-analysis applications.

The system's modular design allows for easy extension and customization while maintaining the core principles of grounding, accuracy, and interpretability that are essential for research applications.