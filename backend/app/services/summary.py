from discovery_utils.utils.llm.llm_utils import get_llm
from langchain_core.prompts import ChatPromptTemplate


class SummaryService:
    def __init__(self, model_name: str, temperature: float, max_tokens: int):
        self.llm = get_llm(model_name, temperature)
        self.model_name = model_name
        self.max_tokens = max_tokens

    def summarize(
        self,
        papers_list: list[dict],
        extraction_fields: list[str] = None,
        prompt: str = None,
    ) -> str:
        # Format input for the LLM
        def format_paper(p, idx):
            fields = [
                f"{k}: {v}" for k, v in p.items() if k.startswith("extra_field_") and v
            ]
            # Always include id and title for reference linking
            return (
                f"[{idx+1}] Title: {p.get('title', '')}\nOpenAlex: {p.get('id', '')}\n"
                + "\n".join(fields)
            )

        input_text = "\n\n".join(
            format_paper(p, idx) for idx, p in enumerate(papers_list)
        )
        # Prompt
        system_message = "You are an expert research summariser."
        user_message = (
            "Given the following papers and their extracted fields, write a concise summary "
            "focusing on main themes and key information, using British English.\n\n"
            # Use numbered in-text citations, e.g., [1], [2], etc.
            "Use numbered in-text references (e.g., [1], [2]) to refer to the papers within the summary.\n"
            # All in-text citations must be HTML <a> links with class="ai-summary-link"
            'Each in-text reference should be an HTML <a> tag with class="ai-summary-link" linking to the paper\'s OpenAlex URL.\n'
            'For example <a href="openalex-id" class="ai-summary-link">[1]</a>\n'
            # Provide a reference list at the end of the summary
            "At the end of the summary, add double line break and then include a Reference List: numbered HTML <ol> list with the correct numbering.\n"
            "It is important that the reference list is numbered from 1 to the number of papers, and that the numbering is consistent with the in-text references.\n"
            'For example <ol><li><a href="openalex-id" class="ai-summary-link">[number] Paper title</a></li></ol>\n'
            # Each reference in the list should be the paper title as a hyperlink to its OpenAlex page
            'Each list item should be the paper\'s title as an <a> tag (with class="ai-summary-link") '
            "that links to the corresponding OpenAlex URL.\n"
            'All links should have target="_blank"'
            # Numbering must match between in-text references and list
            "Ensure that reference numbering is strictly sequential and consistent between in-text citations and the list "
            "(i.e., the first paper mentioned is [1], the second is [2], and so on).\n"
            # Reiterate styling requirement for consistency
            'All hyperlinks—both in-text and in the reference list—must include class="ai-summary-link".\n\n'
            # Placeholder for the actual input (e.g., list of papers and their metadata)
            "{input}"
        )
        if prompt:
            user_message += f"\n\nInstructions: {prompt}"
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_message), ("user", user_message)]
        )
        formatted_prompt = prompt.format(input=input_text)
        # Call LLM
        response = self.llm.invoke(formatted_prompt)
        return response.content
