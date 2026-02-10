import os
import random
from datetime import datetime, timedelta
from langfuse import Langfuse

# Initialize Client
langfuse = Langfuse()

# --- 1. DEFINE EVALUATOR ---
def local_llm_judge(input_text, output_text):
    # Mock logic: Replace with your real judge
    if not output_text: return 0.0
    return random.uniform(0.7, 1.0)

# --- 2. TIME FILTER ---
six_hours_ago = datetime.now() - timedelta(hours=6)
print(f"Fetching traces after: {six_hours_ago.isoformat()}")

# --- 3. FETCH TRACES ---
# Use api.trace.list to fetch traces
traces_page = langfuse.api.trace.list(
    from_timestamp=six_hours_ago, 
    limit=50,
    order_by="timestamp.desc"
)

print(f"Found {len(traces_page.data)} traces.")

# --- 4. PROCESS ---
for trace in traces_page.data:
    generation_scores = []
    
    # Fetch observations (Use get_many instead of list)
    try:
        observations_page = langfuse.api.observations.get_many(
            trace_id=trace.id,
            type="GENERATION",
            limit=100
        )
    except Exception as e:
        print(f"Error fetching observations for trace {trace.id}: {e}")
        continue

    # Filter for your specific LLM calls
    target_generations = [obs for obs in observations_page.data if obs.name == "test"]

    if not target_generations:
        continue

    print(f" - Processing Trace {trace.id} ({len(target_generations)} generations)...")

    for obs in target_generations:
        score_value = local_llm_judge(obs.input, obs.output)
        
        # FIX: Use create_score() instead of score()
        langfuse.create_score(
            name="accuracy",
            value=score_value,
            observation_id=obs.id,  # Score the specific generation
            comment="Local evaluation"
        )
        generation_scores.append(score_value)

    if generation_scores:
        avg_score = sum(generation_scores) / len(generation_scores)
        
        # FIX: Use create_score() instead of score()
        langfuse.create_score(
            name="avg_accuracy",
            value=avg_score,
            trace_id=trace.id,      # Score the root trace
            comment=f"Average of {len(generation_scores)} generations"
        )
        print(f"   -> Updated Trace Score: {avg_score:.2f}")

# Ensure all events are sent
langfuse.flush()
print("Done!")
