from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from typing import Optional, Dict
import tempfile
import logging
from pathlib import Path
import uuid

from app.core.auth import get_current_user, CurrentUser
from app.services.analysis.parse import ParsingService
from app.services.analysis.normalize import normalize_text
from app.services.analysis.workflow_langchain import ExtractionWorkflow
from app.services.analysis.prompts import (
    ISSUES_PROMPT,
    INTERVENTIONS_PROMPT,
    MAPPING_PROMPT,
    RESULTS_PROMPT,
    CONCLUSIONS_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)
from app.core.config import settings
from langchain_core.prompts import ChatPromptTemplate

router = APIRouter()
logger = logging.getLogger(__name__)


def create_custom_prompt(
    custom_text: str, template_variables: str = "{full_text}"
) -> ChatPromptTemplate:
    """Create a custom prompt template from user text"""
    return ChatPromptTemplate.from_messages(
        [
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", custom_text + f"\n\nPaper text:\n{template_variables}"),
        ]
    )


async def run_extraction_with_custom_prompts(
    text: str, custom_prompts: Optional[Dict[str, str]] = None
):
    """Run extraction with optional custom prompts - simplified approach"""
    workflow = ExtractionWorkflow(model=settings.LLM_MODEL, temperature=0.0)

    # If no custom prompts, use standard workflow
    if not custom_prompts:
        doc_id = f"test_{uuid.uuid4().hex[:8]}"
        return await workflow.run(doc_id, text)

    # For custom prompts, we'll run each stage manually with custom prompts
    from app.services.analysis.schemas_langchain import (
        IssuesExtraction,
        InterventionsExtraction,
        MappingsExtraction,
        ResultsExtraction,
        ConclusionsExtraction,
        DocumentExtractionBundle,
    )
    import json

    doc_id = f"test_{uuid.uuid4().hex[:8]}"

    # Stage 1: Issues
    issues_prompt = (
        create_custom_prompt(custom_prompts.get("issues"))
        if custom_prompts.get("issues")
        else ISSUES_PROMPT
    )
    chain = issues_prompt | workflow.llm | workflow.json_parser
    issues_result = await chain.ainvoke({"full_text": text})
    issues_extraction = IssuesExtraction(**issues_result)

    # Stage 2: Interventions
    interventions_prompt = (
        create_custom_prompt(custom_prompts.get("interventions"))
        if custom_prompts.get("interventions")
        else INTERVENTIONS_PROMPT
    )
    chain = interventions_prompt | workflow.llm | workflow.json_parser
    interventions_result = await chain.ainvoke({"full_text": text})
    interventions_extraction = InterventionsExtraction(**interventions_result)

    # Stage 3: Mappings
    if issues_extraction.issues and interventions_extraction.interventions:
        issues_json = json.dumps(
            {"issues": [issue.model_dump() for issue in issues_extraction.issues]}
        )
        interventions_json = json.dumps(
            {
                "interventions": [
                    intervention.model_dump()
                    for intervention in interventions_extraction.interventions
                ]
            }
        )

        mappings_prompt = (
            create_custom_prompt(
                custom_prompts.get("mappings"),
                "Issues JSON: {issues_json}\nInterventions JSON: {interventions_json}\n\nPaper text:\n{full_text}",
            )
            if custom_prompts.get("mappings")
            else MAPPING_PROMPT
        )

        chain = mappings_prompt | workflow.llm | workflow.json_parser
        mappings_result = await chain.ainvoke(
            {
                "full_text": text,
                "issues_json": issues_json,
                "interventions_json": interventions_json,
            }
        )
        mappings_extraction = MappingsExtraction(**mappings_result)
    else:
        mappings_extraction = MappingsExtraction(mappings=[])

    # Stage 4: Results
    all_results = []
    if interventions_extraction.interventions:
        results_prompt = (
            create_custom_prompt(
                custom_prompts.get("results"),
                "Intervention:\n{one_intervention_json}\n\nPaper text:\n{full_text}",
            )
            if custom_prompts.get("results")
            else RESULTS_PROMPT
        )

        for intervention in interventions_extraction.interventions:
            intervention_json = json.dumps(intervention.model_dump())
            chain = results_prompt | workflow.llm | workflow.json_parser
            results_result = await chain.ainvoke(
                {
                    "full_text": text,
                    "one_intervention_json": intervention_json,
                }
            )
            results_extraction = ResultsExtraction(**results_result)

            for result_item in results_extraction.results:
                result_item.intervention_idx = intervention.idx
                all_results.append(result_item)

    # Stage 5: Conclusions
    conclusions_prompt = (
        create_custom_prompt(custom_prompts.get("conclusions"))
        if custom_prompts.get("conclusions")
        else CONCLUSIONS_PROMPT
    )
    chain = conclusions_prompt | workflow.llm | workflow.json_parser
    conclusions_result = await chain.ainvoke({"full_text": text})
    conclusions_extraction = ConclusionsExtraction(**conclusions_result)

    return DocumentExtractionBundle(
        paper_id=doc_id,
        issues=issues_extraction.issues,
        interventions=interventions_extraction.interventions,
        mappings=mappings_extraction.mappings,
        results=all_results,
        conclusion=conclusions_extraction.conclusion,
    )


@router.get("/api/test-extraction/prompts")
async def get_default_prompts(current_user: CurrentUser = Depends(get_current_user)):
    """Get default extraction prompts for customization"""

    # Extract the human message content from each prompt template
    def extract_human_message(prompt_template):
        for message in prompt_template.messages:
            if hasattr(message, "prompt") and hasattr(message.prompt, "template"):
                if "Task:" in message.prompt.template:
                    return message.prompt.template
        return ""

    return {
        "issues": extract_human_message(ISSUES_PROMPT),
        "interventions": extract_human_message(INTERVENTIONS_PROMPT),
        "mappings": extract_human_message(MAPPING_PROMPT),
        "results": extract_human_message(RESULTS_PROMPT),
        "conclusions": extract_human_message(CONCLUSIONS_PROMPT),
    }


@router.post("/api/test-extraction")
async def test_extraction(
    current_user: CurrentUser = Depends(get_current_user),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    custom_prompts: Optional[str] = Form(None),  # JSON string of custom prompts
):
    """
    Test extraction service with either uploaded PDF or pasted text.
    Optionally use custom prompts for extraction stages.
    """
    try:
        # Debug logging
        logger.info(
            f"Test extraction request - file: {file.filename if file else None}, text length: {len(text) if text else 0}, custom_prompts: {bool(custom_prompts)}"
        )

        # Validate input
        if not file and not text:
            logger.error("Validation failed: Neither file nor text provided")
            raise HTTPException(
                status_code=400, detail="Either file or text must be provided"
            )

        if file and text:
            logger.error("Validation failed: Both file and text provided")
            raise HTTPException(
                status_code=400, detail="Provide either file or text, not both"
            )

        # Parse custom prompts if provided
        parsed_custom_prompts = None
        if custom_prompts:
            try:
                import json

                parsed_custom_prompts = json.loads(custom_prompts)
            except Exception as e:
                logger.warning(f"Failed to parse custom prompts: {e}")

        # Extract text from input
        extracted_text = ""

        if file:
            # Handle PDF upload
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=400, detail="Only PDF files are supported"
                )

            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                content = await file.read()
                temp_file.write(content)
                temp_file_path = temp_file.name

            try:
                # Parse PDF using existing service
                temp_dir = Path(tempfile.mkdtemp())
                parser = ParsingService(export_dir=str(temp_dir))

                doc_id = f"test_{uuid.uuid4().hex[:8]}"
                parsed = await parser.parse_saved_file(doc_id, temp_file_path)

                if not parsed or not parsed.text:
                    raise HTTPException(
                        status_code=400, detail="Failed to extract text from PDF"
                    )

                # Normalize text
                extracted_text = normalize_text(parsed.text)

            finally:
                # Cleanup
                Path(temp_file_path).unlink(missing_ok=True)
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

        else:
            # Use provided text
            extracted_text = normalize_text(text)

        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted")

        # Run extraction workflow
        extraction_result = await run_extraction_with_custom_prompts(
            extracted_text, parsed_custom_prompts
        )

        # Format response to match the expected format for DocumentDetailView
        response = {
            "document": {
                "id": extraction_result.paper_id,
                "doc_id": extraction_result.paper_id,
                "title": file.filename if file else "Pasted Text",
                "source": "test_extraction",
                "year": None,
                "abstract_or_summary": extracted_text[:500] + "..."
                if len(extracted_text) > 500
                else extracted_text,
                "is_relevant": True,
                "extraction_status": "completed",
            },
            "extraction": {
                "issues": [issue.model_dump() for issue in extraction_result.issues],
                "interventions": [
                    {
                        **intervention.model_dump(),
                        "results": [
                            result.model_dump()
                            for result in extraction_result.results
                            if result.intervention_idx == intervention.idx
                        ],
                    }
                    for intervention in extraction_result.interventions
                ],
                "mappings": [
                    mapping.model_dump() for mapping in extraction_result.mappings
                ],
                "conclusion": extraction_result.conclusion.model_dump()
                if extraction_result.conclusion
                else None,
                "metadata": {
                    "text_length": len(extracted_text),
                    "extraction_time": "live",
                    "custom_prompts_used": parsed_custom_prompts is not None,
                },
            },
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
