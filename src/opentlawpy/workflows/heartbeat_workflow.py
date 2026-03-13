import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from opentlawpy.config import HEARTBEAT_INTERVAL_MINUTES, HEARTBEAT_MESSAGE
    from opentlawpy.models.heartbeat import PokeAgentInput, PokeAgentOutput


@workflow.defn
class HeartbeatWorkflow:
    def __init__(self) -> None:
        self._stopped = False
        self._poke_count = 0

    @workflow.run
    async def run(self, chat_id: str) -> None:
        while not self._stopped:
            # either we receive a stop signal in which case the workflow ends
            # or if we hit timeout, the workflow errors and we proceed
            # with the rest of the logic. This is just a temporal native way
            # to handle "cron" like stuff.
            try:
                await workflow.wait_condition(
                    lambda: self._stopped,
                    timeout=timedelta(minutes=HEARTBEAT_INTERVAL_MINUTES),
                )
            except asyncio.TimeoutError:
                # Timeout means it's time to poke the agent
                pass

            if self._stopped:
                workflow.logger.info(f"Heartbeat stopped for {chat_id}")
                return

            workflow.logger.info(f"Heartbeat poke #{self._poke_count + 1} for {chat_id}")

            await workflow.execute_activity(
                "poke_agent",
                arg=PokeAgentInput(
                    chat_id=chat_id,
                    message=HEARTBEAT_MESSAGE,
                ),
                result_type=PokeAgentOutput,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            self._poke_count += 1

            # Continue-as-new every 100 pokes to bound event history
            if self._poke_count >= 100:
                workflow.logger.info(
                    f"Continuing-as-new after {self._poke_count} pokes for {chat_id}"
                )
                workflow.continue_as_new(chat_id)

    @workflow.signal
    def stop(self) -> None:
        self._stopped = True
