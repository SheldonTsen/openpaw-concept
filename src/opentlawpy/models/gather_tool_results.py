from dataclasses import dataclass


@dataclass
class GatherToolResultsInput:
    tool_calls: list[dict]
    tool_results: list[str]


@dataclass
class GatherToolResultsOutput:
    tool_results_as_messages: list[dict]
