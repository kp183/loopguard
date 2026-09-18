# LoopGuard 3-Minute Video Rehearsal Script

**Target Duration:** 180 seconds maximum  
**Display Configuration:** 1080p, split-screen (Left: Terminal & Chat/Browser, Right: AWS Management Console)  

---

## Rehearsal Timing Breakdown

### Segment 1: The Problem & Live Execution Trigger (0:00 – 0:35)
- **Screen View:** Left: Terminal. Right: CloudWatch Alarm Console showing `LoopGuard-TargetInvocationsSpike` in `OK` state.
- **Action:** Run the trigger command:
  ```bash
  aws lambda invoke \
    --function-name LoopGuard-TargetFunction \
    --invocation-type Event \
    --payload '{"runaway_mode": true, "session_id": "session-live-01"}' \
    out.json
  ```
- **Spoken Narrative:**
  > "Serverless architectures and AI agent pipelines rarely fail by simply crashing—they fail by looping. When an LLM agent encounters a database lock, it retries and reformulates queries, burning compute and API budgets while returning healthy HTTP 200 responses. Standard cost tools update on an 8 to 24-hour delay. We trigger a live recursive retry loop right now on camera."

---

### Segment 2: Detection, Stagnation Analysis & Tag-Based Routing (0:35 – 1:20)
- **Screen View:** Left: CloudWatch Logs stream refreshing live / Webhook channels. Right: CloudWatch Metrics graph climbing.
- **Action:** Highlight invocations crossing the threshold ($\ge 20$). Show the alarm state transition to `ALARM`. Show orchestrator logs displaying SequenceMatcher stagnation ratio ($\ge 0.70$), Bedrock root-cause diagnostic, and `tag:GetResources` ownership lookup.
- **Pacing & Beat 3 Options (Choose Based on Video Runtime):**
  - **Option A (Recommended — Single Pristine Loop, ~180s Strict):** Trigger Payments-Core (`LoopGuard-TargetFunction`). Show the orchestrator resolving `Team: Payments-Core` and dispatching to `#alerts-payments` with HMAC-tokenized action buttons.
  - **Option B (Dual-Team Routing Beat, +15s):** Trigger both `Payments-Core` and `Infra-Core` functions; show alerts automatically routing to their respective channels with zero cross-team spam.
- **Spoken Narrative:**
  > "Within seconds, our CloudWatch alarm breaches threshold, and EventBridge invokes our orchestrator. LoopGuard performs inline fuzzy sequence matching across consecutive arguments, detecting an 87% parameter similarity—signaling semantic stagnation. The orchestrator queries the AWS Resource Groups Tagging API to identify the owning team dynamically, calls Bedrock for root-cause synthesis, and dispatches an actionable alert card directly to the team's dedicated webhook channel."

---

### Segment 3: Surgical Session Isolation & S3 Postmortem (1:20 – 2:10)
- **Screen View:** Left: Browser hitting surgical remediation URL. Right: DynamoDB Management Console.
- **Action:** Click the surgical quarantine link:
  ```bash
  curl -s "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<HMAC_TOKEN>&action=session&session_id=sess-live-payments-88&incident_id=INC-LIVE"
  ```
  1. Show DynamoDB `SESSION#sess-live-payments-88` with an active 10-minute TTL lock.
  2. Invoke target with `sess-live-payments-88` $\to$ returns **HTTP 499** (`SURGICAL_QUARANTINE_ENFORCED`).
  3. Invoke target with clean session $\to$ returns **HTTP 200** (`SUCCESS`). Blast radius = 0%.
  4. Highlight the **'📥 Download SRE Incident Postmortem (.md)'** button on the remediation page, linking to the auto-generated report in Amazon S3.
- **Spoken Narrative:**
  > "Rather than taking down the entire service, we click LoopGuard's surgical quarantine action. This writes an ephemeral 10-minute TTL lock into DynamoDB. When our runaway session attempts to continue, it is halted instantly with HTTP 499. Meanwhile, concurrent requests from healthy users continue processing with HTTP 200. Our blast radius is restricted to exactly one broken session. Simultaneously, LoopGuard automatically compiles an enterprise-grade Markdown incident postmortem directly to Amazon S3, available for one-click download."

---

### Segment 4: Emergency Global Override & Reset (2:10 – 2:45)
- **Screen View:** Left: Browser hitting global remediation URL. Right: Lambda Concurrency Management Console.
- **Action:** Trigger the emergency global kill switch. Refresh the AWS Console to show Reserved Concurrency set to 0.
  ```bash
  curl -s "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<HMAC_TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-LIVE"
  ```
- **Spoken Narrative:**
  > "If engineering determines an incident represents a systemic deployment bug, LoopGuard provides an emergency global override. We execute the global action—and in the AWS console, reserved concurrency is set to 0 instantly. All subsequent executions are throttled at the infrastructure layer (HTTP 429) before incurring further compute costs. Between rehearsal drills or takes, our reset utility restores the entire environment in just five seconds."

---

### Segment 5: Architecture Summary (2:45 – 3:00)
- **Screen View:** Full screen: VS Code displaying clean AWS SAM template and public GitHub repository structure.
- **Spoken Narrative:**
  > "Built natively on AWS using Lambda, EventBridge, CloudWatch, DynamoDB, Bedrock, and API Gateway. LoopGuard delivers real-time, closed-loop resilience for the serverless and AI agent era."
