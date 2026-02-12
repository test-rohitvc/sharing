from pydantic import BaseModel, Field
from typing import Optional

class EvaluationResult(BaseModel):
    """
    Structured output for evaluation results.
    """
    score: float = Field(
        ..., 
        description="A score between 0.0 and 1.0 representing the quality of the generation based on the criteria."
    )
    reasoning: str = Field(
        ..., 
        description="A detailed explanation of why this score was assigned."
    )
    evaluator_name: str = Field(
        ...,
        description="The name of the evaluator (e.g., 'Consistency', 'Correctness')."
    )
