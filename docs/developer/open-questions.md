# Open Questions (Resolved)

* **Will the temporal UI accept the same workflow ID over and over again?**
  * **Answer:** Yes. Temporal enforces unique IDs for *running* workflows, but once a workflow completes/fails/terminates, the same ID can be reused. The UI shows each execution as a separate run under the same workflow ID. No timestamp needed — deterministic IDs are correct.

* **How do we support different activities written in different languages?**
  * **Answer:** Deploy a separate worker per language, both listening on the same task queue. Temporal routes activity tasks to whichever worker registered that activity. Existing Python activity code is unaffected. Not needed for MVP.

* **Lets move cronjob out of MVP?**
  * **Answer:** Yes, agreed. Deferred to upgrade-ideas.md. The WhatsApp listener already handles workflow lifecycle (start on first message, signal on subsequent, restart after expiry). **Plan updated.**

* **Why is `_get_tools()` in `_route_message` in the WhatsApp listener? This should be configured on the Temporal side not the whatsapp listener?**
  * **Answer:** Correct — tools are a workflow concern, not a listener concern. Removed `_get_tools()` from the listener. The workflow loads its own tools from the `tools/` directory at startup. **Plan updated.**

* **What happens to the whatsapp listener if I am using my own number? If someone else texts me, what happens?**
  * **Answer:** Added `MY_PHONE_NUMBER` env var and sender filtering to the listener. Only messages from your own number (and self-chat via `IsFromMe`) are processed. All other messages are ignored. **Plan updated.**

* **Does `async def bash_executor_activity` using asyncio inside Temporal cause issues?**
  * **Answer:** No. Activities are normal Python functions — they can freely use asyncio, subprocess, network calls, etc. Only *workflows* must be deterministic. The current async implementation is correct. No side effects. **No action needed.**

* **Can we use docker compose watch to hot reload workers for dev?**
  * **Answer:** Yes, `docker compose watch` (Compose v2.22+) works for syncing file changes into containers. However, the current `watchdog`/bind mount approach in the plan already works fine. Either approach is valid. **No action needed for MVP.**
