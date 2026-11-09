"""Regression coverage for lossless model-visible tool results."""
from __future__ import annotations

import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import (
    AssistantContextItem,
    ContextItemId,
    TokenUsage,
    ToolCallRecord,
    ToolResultId,
    ToolResultRecord,
)


class ToolResultPromptBudgetTests(unittest.TestCase):
    """Ensure historical tool output remains cache-stable across rounds."""

    def test_tool_results_are_not_truncated_or_rewritten(self) -> None:
        """Context reconstruction preserves a host-supplied result verbatim."""
        handler = ContextHandlerLinear(object(), max_context_threshold=10_000_000)
        historical = "h" * 50_000
        items: list[AssistantContextItem] = []
        results: dict[str, ToolResultRecord] = {}
        for index in range(1, 6):
            result_id = ToolResultId(value=f"r-{index}")
            results[result_id.value] = ToolResultRecord(
                result_id=result_id,
                call_id=f"old-{index}",
                tool_name="shell",
                output=historical,
                images=(),
                ok=True,
                duration_ms=1,
                created_at=None,
            )
            items.append(AssistantContextItem(
                item_id=ContextItemId(value=f"a-{index}"),
                timeline=index,
                content="",
                reasoning="",
                tool_calls=(ToolCallRecord(
                    call_id=f"old-{index}", name="shell", arguments={}, result_id=result_id,
                ),),
                usage=TokenUsage(),
                model_duration_ms=None,
                round_duration_ms=None,
                created_at=None,
            ))
        latest_id = ToolResultId(value="r-6")
        results[latest_id.value] = ToolResultRecord(
            result_id=latest_id,
            call_id="latest",
            tool_name="plan_read",
            output="Plan item frontend-agent-render saved as in_progress.",
            images=(),
            ok=True,
            duration_ms=1,
            created_at=None,
        )
        items.append(AssistantContextItem(
            item_id=ContextItemId(value="a-6"),
            timeline=6,
            content="",
            reasoning="",
            tool_calls=(ToolCallRecord(
                call_id="latest", name="plan_read", arguments={}, result_id=latest_id,
            ),),
            usage=TokenUsage(),
            model_duration_ms=None,
            round_duration_ms=None,
            created_at=None,
        ))
        handler.messages = items
        handler.tool_results = results

        first_messages = handler.build_messages()
        first_tools = [message for message in first_messages if message.role == "tool"]
        second_messages = handler.build_messages()
        tool_messages = [message for message in second_messages if message.role == "tool"]

        self.assertEqual(
            tool_messages[-1].content,
            "Plan item frontend-agent-render saved as in_progress.",
        )
        self.assertEqual(len(tool_messages), 6)
        self.assertEqual(
            [item.content for item in first_tools],
            [item.content for item in tool_messages],
        )
        self.assertTrue(all(
            "Historical tool result omitted" not in (item.content or "")
            for item in tool_messages[:-1]
        ))
        self.assertEqual(historical, tool_messages[0].content)


if __name__ == "__main__":
    unittest.main()
