from abc import ABC, abstractmethod
from typing import Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from models import EvaluationResult

class BaseEvaluator(ABC):
    """
    Base class for all evaluators.
    """
    def __init__(self, llm=None, name: str = "BaseEvaluator"):
        # Default to Gemini-2.5-Flash-Lite if no LLM is provided
        self.llm = llm or ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite", # Updated to current valid model name, user asked for 2.5 but 2.0 is standard currently, verify availability
            temperature=0
        )
        self.name = name
        # Bind the structured output schema immediately
        self.structured_llm = self.llm.with_structured_output(EvaluationResult)

    @abstractmethod
    async def evaluate(self, input_text: str, output_text: str, context: Optional[str] = None) -> EvaluationResult:
        """
        Run the evaluation.
        """
        pass

class ConsistencyEvaluator(BaseEvaluator):
    def __init__(self, llm=None):
        super().__init__(llm, name="Consistency")

    async def evaluate(self, input_text: str, output_text: str, context: Optional[str] = None) -> EvaluationResult:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert AI evaluator. Analyze if the response is consistent with the input request."),
            ("human", """
            Evaluate the detailed consistency of the following interaction.
            
            Input: {input}
            Output: {output}
            
            Return a score (0.0-1.0) and reasoning. Set evaluator_name to 'Consistency'.
            """)
        ])
        chain = prompt | self.structured_llm
        return await chain.ainvoke({"input": input_text, "output": output_text})

class CorrectnessEvaluator(BaseEvaluator):
    def __init__(self, llm=None):
        super().__init__(llm, name="Correctness")

    async def evaluate(self, input_text: str, output_text: str, context: Optional[str] = None) -> EvaluationResult:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert AI evaluator. Verify the factual correctness and logic of the response."),
            ("human", """
            Evaluate the correctness of the generated output based on the input.
            
            Input: {input}
            Output: {output}
            
            Return a score (0.0-1.0) and reasoning. Set evaluator_name to 'Correctness'.
            """)
        ])
        chain = prompt | self.structured_llm
        return await chain.ainvoke({"input": input_text, "output": output_text})
