import os
import httpx
import json
from typing import Dict, Any, Optional, List
from agent.logger import EventLogger


class DustClient:
    def __init__(self):
        self.api_key = os.getenv("DUST_API_KEY")
        self.workspace_id = os.getenv("DUST_WORKSPACE_ID")
        self.base_url = "https://dust.tt/api/v1"

        if not self.api_key or not self.workspace_id:
            raise ValueError(
                "DUST_API_KEY and DUST_WORKSPACE_ID must be set in environment."
            )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_conversation(
        self, content: str, agent_id: str = "gemini-pro", title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new conversation and get the agent's response (blocking)."""
        url = f"{self.base_url}/w/{self.workspace_id}/assistant/conversations"

        payload = {
            "message": {
                "content": content,
                "mentions": [{"configurationId": agent_id}],
                "context": {"username": "cli-user", "timezone": "UTC"},
            },
            "blocking": True,
            "title": title or f"CLI Task: {content[:30]}...",
        }

        EventLogger.log(
            "dust_api_call",
            f"Creating conversation with agent {agent_id}",
            {"content": content},
        )

        response = httpx.post(
            url, headers=self._get_headers(), json=payload, timeout=120.0
        )
        if response.status_code != 200:
            error_msg = f"Dust.tt API Error ({response.status_code}): {response.text}"
            EventLogger.log("dust_api_error", error_msg)
            raise RuntimeError(error_msg)

        result = response.json()

        messages = result.get("conversation", {}).get("content", [])
        if not messages:
            raise RuntimeError("Dust.tt returned empty content.")

        agent_message = messages[-1][0]["content"]
        return {
            "conversation_id": result.get("conversation", {}).get("sId"),
            "message": agent_message,
            "raw": result,
        }

    def send_message(
        self,
        conversation_id: str,
        content: str,
        agent_id: str = "gemini-pro",
    ) -> Dict[str, Any]:
        """Send a follow-up message in an existing conversation thread."""
        url = (
            f"{self.base_url}/w/{self.workspace_id}"
            f"/assistant/conversations/{conversation_id}/messages"
        )

        payload = {
            "content": content,
            "mentions": [{"configurationId": agent_id}],
            "context": {"username": "cli-user", "timezone": "UTC"},
        }

        EventLogger.log(
            "dust_api_call",
            f"Sending message in conversation {conversation_id}",
            {"content": content[:100]},
        )

        response = httpx.post(
            url, headers=self._get_headers(), json=payload, timeout=120.0
        )
        if response.status_code != 200:
            error_msg = f"Dust.tt API Error ({response.status_code}): {response.text}"
            EventLogger.log("dust_api_error", error_msg)
            raise RuntimeError(error_msg)

        result = response.json()
        return {"conversation_id": conversation_id, "post_result": result}

    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Fetch the full conversation including the latest agent reply."""
        url = (
            f"{self.base_url}/w/{self.workspace_id}"
            f"/assistant/conversations/{conversation_id}"
        )

        response = httpx.get(url, headers=self._get_headers(), timeout=60.0)
        if response.status_code != 200:
            error_msg = f"Dust.tt API Error ({response.status_code}): {response.text}"
            raise RuntimeError(error_msg)

        result = response.json()
        messages = result.get("conversation", {}).get("content", [])
        if not messages:
            return {"conversation_id": conversation_id, "message": "", "raw": result}

        agent_message = messages[-1][0].get("content", "")
        return {
            "conversation_id": conversation_id,
            "message": agent_message,
            "raw": result,
        }

    def reply_in_thread(
        self,
        conversation_id: str,
        content: str,
        agent_id: str = "gemini-pro",
        poll_interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> Dict[str, Any]:
        """Send a message and poll until the agent replies."""
        if max_wait <= 0:
            raise ValueError("max_wait must be > 0.")
        if poll_interval <= 0:
            poll_interval = 1.0

        self.send_message(conversation_id, content, agent_id)

        import time

        waited = 0.0
        while waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval
            conv = self.get_conversation(conversation_id)
            messages = conv.get("raw", {}).get("conversation", {}).get("content", [])
            if not messages:
                continue
            last_group = messages[-1]
            last_msg = last_group[0] if last_group else {}
            if (
                last_msg.get("type") == "agent_message"
                and last_msg.get("status") == "succeeded"
            ):
                return {
                    "conversation_id": conversation_id,
                    "message": last_msg.get("content", ""),
                }

        raise RuntimeError("Agent did not reply within the timeout.")

    def parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON from an agent's text response."""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > 0:
                return json.loads(text[start:end])
            return json.loads(text)
        except json.JSONDecodeError as e:
            EventLogger.log(
                "json_parse_error",
                f"Failed to parse JSON from agent response: {str(e)}",
                {"text": text},
            )
            raise RuntimeError(f"Agent did not return valid JSON: {text}")

    def route_prompt(self, prompt: str) -> Dict[str, Any]:
        """Route a natural language prompt to a skill and slots."""
        content = f"""
Route this request to a skill and return ONLY a JSON object with 'skill_id' and 'slots'.
Request: {prompt}

Available Skills:
- envoice.sales_invoice.existing: Create a sales invoice for an existing customer.
- envoice.sales_invoice.new_customer: Create a sales invoice and add a new customer inline.
- envoice.purchase_invoice.new: Create a new purchase invoice.
- envoice.extract_sales: Extract/list all sales invoices from the table.
- envoice.bulk_create_drafts: Create multiple draft invoices from a list.

Example Output:
{{
  "skill_id": "envoice.sales_invoice.existing",
  "slots": {{
    "customer": "ACME Corp, LLC",
    "amount": 32000,
    "currency": "USD",
    "period": "monthly",
    "tax_rule": "reverse_charge",
    "vat_id": "IE6388047V"
  }},
  "confidence": 0.9,
  "reasoning": "Sales invoice requested with recurrence and VAT context."
}}
"""
        result = self.create_conversation(content, title=f"Route: {prompt[:20]}")
        parsed = self.parse_json_response(result["message"])
        parsed.setdefault("slots", {})
        parsed.setdefault("confidence", 0.5)
        return parsed

    def evaluate_run(
        self, report: Dict[str, Any], skill_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate a run report and propose a JSON patch."""
        content = f"""
Evaluate this browser automation run and propose a JSON patch (RFC6902) to fix any issues in the SkillSpec.
Return ONLY a JSON object with 'decision' (success/failure), 'failure_class', 'reasons', and 'patch'.

Skill Spec:
{json.dumps(skill_spec, indent=2)}

Run Report:
{json.dumps(report, indent=2)}
"""
        result = self.create_conversation(
            content, title=f"Eval: {report.get('run_id', 'unknown')[:8]}"
        )
        return self.parse_json_response(result["message"])

    def mine_workflow(self, trace_summary: str) -> Dict[str, Any]:
        """Mine a workflow from a trace summary to create a new SkillSpec."""
        content = f"""
Analyze this browser trace summary and generate a SkillSpec JSON object.
The SkillSpec should contain 'id', 'name', 'description', and 'steps' (goto, click, fill, wait, screenshot).

Trace Summary:
{trace_summary}
"""
        result = self.create_conversation(content, title="Mine Workflow")
        return self.parse_json_response(result["message"])

    def _run_json_role(
        self,
        role_name: str,
        task: str,
        context_payload: Dict[str, Any],
        *,
        title: Optional[str] = None,
        agent_id: str = "gemini-pro",
    ) -> Dict[str, Any]:
        content = (
            f"You are the '{role_name}' agent in a multi-agent automation system.\n"
            "Return ONLY valid JSON and no prose.\n\n"
            f"Task:\n{task}\n\n"
            f"Context JSON:\n{json.dumps(context_payload, indent=2)}\n"
        )
        result = self.create_conversation(
            content=content,
            agent_id=agent_id,
            title=title or f"{role_name}: {task[:40]}",
        )
        parsed = self.parse_json_response(result["message"])
        if not isinstance(parsed, dict):
            raise RuntimeError(f"{role_name} agent returned non-object JSON.")
        return parsed

    def multi_agent_mine_workflow(
        self,
        *,
        skill_id: str,
        base_url: str,
        trace_summary: str,
        interaction_events: List[Dict[str, Any]],
        platform_map_digest: Dict[str, Any],
        agent_id: str = "gemini-pro",
    ) -> Dict[str, Any]:
        mapper = self._run_json_role(
            role_name="platform_mapper",
            task=(
                "Extract reusable UI/platform knowledge from mimic events. "
                "Return keys: selectors, urls, actions, ui_patterns, caveats."
            ),
            context_payload={
                "base_url": base_url,
                "trace_summary": trace_summary,
                "interaction_events": interaction_events[-150:],
                "platform_map_digest": platform_map_digest,
            },
            title=f"Map platform: {skill_id}",
            agent_id=agent_id,
        )

        planner = self._run_json_role(
            role_name="workflow_planner",
            task=(
                "Build an intent-level action plan from events. "
                "Return keys: objective, prerequisites, slot_candidates, action_plan."
            ),
            context_payload={
                "skill_id": skill_id,
                "base_url": base_url,
                "trace_summary": trace_summary,
                "interaction_events": interaction_events[-150:],
                "platform_knowledge": mapper,
            },
            title=f"Plan workflow: {skill_id}",
            agent_id=agent_id,
        )

        writer = self._run_json_role(
            role_name="skill_writer",
            task=(
                "Generate a valid SkillSpec object. "
                "Use only actions: goto, click, fill, fill_date, select_option, select2, "
                "select2_tax, wait, wait_for_url, screenshot, evaluate, check_validation."
                " Return keys: skill_spec."
            ),
            context_payload={
                "skill_id": skill_id,
                "base_url": base_url,
                "trace_summary": trace_summary,
                "platform_knowledge": mapper,
                "workflow_plan": planner,
            },
            title=f"Write skill: {skill_id}",
            agent_id=agent_id,
        )

        critic = self._run_json_role(
            role_name="skill_critic",
            task=(
                "Audit the candidate SkillSpec for schema validity and execution robustness. "
                "If needed, repair it. Return keys: skill_spec, issues."
            ),
            context_payload={
                "skill_id": skill_id,
                "candidate_skill_spec": writer.get("skill_spec", writer),
                "platform_knowledge": mapper,
                "workflow_plan": planner,
            },
            title=f"Critique skill: {skill_id}",
            agent_id=agent_id,
        )

        return {
            "platform_mapper": mapper,
            "workflow_planner": planner,
            "skill_writer": writer,
            "skill_critic": critic,
            "skill_spec": critic.get("skill_spec")
            or writer.get("skill_spec")
            or writer,
        }

    def synthesize_skill_from_prompt(
        self,
        *,
        skill_id: str,
        prompt: str,
        platform_map_digest: Dict[str, Any],
        available_skill_ids: List[str],
        agent_id: str = "gemini-pro",
    ) -> Dict[str, Any]:
        planner = self._run_json_role(
            role_name="prompt_planner",
            task=(
                "Map the user prompt to executable workflow intent using platform memory. "
                "Return keys: objective, reuse_existing_skill, candidate_skill_id, "
                "slot_candidates, action_plan."
            ),
            context_payload={
                "prompt": prompt,
                "target_skill_id": skill_id,
                "platform_map_digest": platform_map_digest,
                "available_skill_ids": available_skill_ids,
            },
            title=f"Plan prompt: {prompt[:40]}",
            agent_id=agent_id,
        )

        writer = self._run_json_role(
            role_name="prompt_skill_writer",
            task=(
                "Generate a new SkillSpec for this prompt. "
                "Use only supported actions: goto, click, fill, fill_date, select_option, "
                "select2, select2_tax, wait, wait_for_url, screenshot, evaluate, check_validation. "
                "Return keys: skill_spec."
            ),
            context_payload={
                "prompt": prompt,
                "target_skill_id": skill_id,
                "platform_map_digest": platform_map_digest,
                "planner": planner,
            },
            title=f"Write prompt skill: {skill_id}",
            agent_id=agent_id,
        )

        critic = self._run_json_role(
            role_name="prompt_skill_critic",
            task=(
                "Review and repair the generated SkillSpec. "
                "Return keys: skill_spec, risks, assumptions."
            ),
            context_payload={
                "prompt": prompt,
                "target_skill_id": skill_id,
                "candidate_skill_spec": writer.get("skill_spec", writer),
                "planner": planner,
                "platform_map_digest": platform_map_digest,
            },
            title=f"Critique prompt skill: {skill_id}",
            agent_id=agent_id,
        )

        return {
            "planner": planner,
            "writer": writer,
            "critic": critic,
            "skill_spec": critic.get("skill_spec")
            or writer.get("skill_spec")
            or writer,
        }
