import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from langfuse import Langfuse
from langfuse.api.resources.score.types.create_score_request import CreateScoreRequest
from evaluator import BaseEvaluator


class EvaluationPipeline:
    def __init__(self, langfuse_client: Optional[Langfuse] = None):
        self.langfuse = langfuse_client or Langfuse()
        self.evaluators: List[BaseEvaluator] = []

    def add_evaluator(self, evaluator: BaseEvaluator):
        """Register an evaluator to the pipeline."""
        self.evaluators.append(evaluator)

    async def fetch_traces(
        self,
        limit: int = 50,
        minutes_ago: int = 60 * 24,
        tags: Optional[List[str]] = None,
    ):
        """
        Fetch traces with intuitive filtering options.
        """
        from_timestamp = datetime.now() - timedelta(minutes=minutes_ago)
        print(f"Fetching traces since: {from_timestamp}")

        try:
            # Note: tags filtering depends on SDK support, listing here for extensibility
            traces_page = await self.langfuse.async_api.trace.list(
                from_timestamp=from_timestamp, limit=limit, order_by="timestamp.desc"
            )
            return traces_page.data
        except Exception as e:
            print(f"Error fetching traces: {e}")
            return []

    def filter_unevaluated_traces(self, traces):
        """Filter out traces that already have scores."""
        unevaluated = []
        for trace in traces:
            # Check if scores list is empty
            if not trace.scores:
                unevaluated.append(trace)
        return unevaluated

    async def _process_single_trace(self, trace_summary):
        """
        Process a single trace: Fetch detailed view -> Extract Generations -> Evaluate -> Update Score.
        """
        try:
            # 1. Get detailed trace to access observations
            detailed_trace = self.langfuse.api.trace.get(trace_id=trace_summary.id)

            over_all_score = {}
            for evaluator in self.evaluators:
                over_all_score[evaluator.name] = {"score": 0, "reason": ""}

            # 2. Extract GENERATION observations
            generations = [
                obs for obs in detailed_trace.observations if obs.type == "GENERATION"
            ]

            if not generations:
                return

            print(
                f"Processing Trace ID: {trace_summary.id} | Generations found: {len(generations)}"
            )

            for generation in generations:
                input_text = str(generation.input)
                output_text = str(generation.output)

                # 3. Run all registered evaluators
                for evaluator in self.evaluators:
                    print(f"  Running {evaluator.name}...")
                    try:
                        result = await evaluator.evaluate(input_text, output_text)

                        over_all_score[evaluator.name]["score"] += result.score
                        over_all_score[evaluator.name][
                            "reason"
                        ] += f"\n{result.reasoning}"
                        # 4. Push Score to Langfuse
                        self.langfuse.api.score.create(
                            request=CreateScoreRequest(
                                name=result.evaluator_name,
                                traceId=trace_summary.id,
                                observationId=generation.id,
                                comment=result.reasoning,
                                value=result.score,
                            )
                        )

                        print(f"    -> Score published: {result.score}")
                    except Exception as eval_err:
                        print(
                            f"    -> Evaluation failed for {evaluator.name}: {eval_err}"
                        )

            total_generations = len(generations)

            for evaluator_name, matrix in over_all_score.items():
                self.langfuse.api.score.create(
                    request=CreateScoreRequest(
                        name=evaluator_name,
                        traceId=trace_summary.id,
                        comment=over_all_score[evaluator_name]["reason"],
                        value=over_all_score[evaluator_name]["score"]
                        / total_generations,
                    )
                )

        except Exception as e:
            print(f"Error processing trace {trace_summary.id}: {e}")

    async def run_async(self, limit: int = 50, minutes_ago: int = 360):
        """
        Main Async Entry point.
        """
        # 1. Fetch
        all_traces = await self.fetch_traces(limit=limit, minutes_ago=minutes_ago)
        print(f"Total traces fetched: {len(all_traces)}")

        # 2. Filter
        target_traces = self.filter_unevaluated_traces(all_traces)
        print(f"Traces requiring evaluation: {len(target_traces)}")

        # 3. Process concurrently
        tasks = [self._process_single_trace(trace) for trace in target_traces]
        if tasks:
            await asyncio.gather(*tasks)
        print("Pipeline execution finished.")

    def run_sync(self, limit: int = 50, minutes_ago: int = 360):
        """
        Wrapper for synchronous execution.
        """
        asyncio.run(self.run_async(limit=limit, minutes_ago=minutes_ago))

    def run_background_task(self, limit: int = 50, minutes_ago: int = 360):
        """
        Fire and forget background task (useful for FastAPI/servers).
        """
        loop = asyncio.get_event_loop()
        loop.create_task(self.run_async(limit=limit, minutes_ago=minutes_ago))
        print("Evaluation pipeline started in background...")
