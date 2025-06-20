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
            # Prioritize doi for original source, then overton_url, then id
            url = p.get("doi") or p.get("overton_url") or p.get("id", "")
            return (
                f"[{idx+1}] Title: {p.get('title', '')}\nURL: {url}\n"
                + "\n".join(fields)
            )

        input_text = "\n\n".join(
            format_paper(p, idx) for idx, p in enumerate(papers_list)
        )
        # Prompt
        system_message = "You are an expert policy and research summariser."
        user_message = (
            "Given the following documents and their extracted fields, write a concise summary "
            "focusing on main themes and key information, using British English.\n\n"
            "Use numbered in-text references (e.g., [1], [2]) to refer to the documents within the summary.\n"
            'Each in-text reference should be an HTML <a> tag with class="ai-summary-link" linking to the document\'s URL.\n'
            'For example, in-text: <a href="document-url" class="ai-summary-link">[1]</a>\n'
            "\n"
            "At the end of the summary, after a double line break, include a Reference List as a numbered HTML <ol> list. "
            'Each item must be an <a> tag (with class="ai-summary-link" and target="_blank") that starts with the same number as the in-text citation, followed by the document title, and links to the document\'s URL.\n'
            "For example:\n"
            '<ol>\n  <li><a href="document-url" class="ai-summary-link" target="_blank">[1] Document title</a></li>\n  <li><a href="document-url" class="ai-summary-link" target="_blank">[2] Document title</a></li>\n</ol>\n'
            "\nThe numbering in the reference list must exactly match the in-text citations.\n"
            "Each reference in the list must begin with the same number as the in-text citation, e.g., [1], [2], etc., inside the <a> tag.\n"
            'All links should have target="_blank".\n'
            "Ensure that reference numbering is strictly sequential and consistent between in-text citations and the list "
            "(i.e., the first document mentioned is [1], the second is [2], and so on).\n"
            'All hyperlinks—both in-text and in the reference list—must include class="ai-summary-link".\n\n'
            "Do not omit the numbers in the reference list. Each reference must start with its number in square brackets, matching the in-text citation.\n\n"
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
