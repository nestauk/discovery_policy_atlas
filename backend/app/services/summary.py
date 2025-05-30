from discovery_utils.utils.llm.llm_utils import get_llm
from langchain_core.prompts import ChatPromptTemplate

class SummaryService:
    def __init__(self, model_name: str, temperature: float, max_tokens: int):
        self.llm = get_llm(model_name, temperature)
        self.model_name = model_name
        self.max_tokens = max_tokens

    def summarize(self, papers_list: list[dict], extraction_fields: list[str] = None) -> str:
        # Format input for the LLM
        def format_paper(p):
            fields = [f"{k}: {v}" for k, v in p.items() if k.startswith("extra_field_") and v]
            return f"Title: {p.get('title', '')}\n" + "\n".join(fields)
        input_text = "\n\n".join(format_paper(p) for p in papers_list)
        # Prompt
        system_message = "You are an expert research summarizer."
        user_message = (
            "Given the following papers and their extracted fields, write a concise summary focusing on main themes and key information:\n\n{input}"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("user", user_message)
        ])
        formatted_prompt = prompt.format(input=input_text)
        # Call LLM
        response = self.llm.invoke(formatted_prompt)
        return response.content