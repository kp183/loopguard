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

### Segment 2: Detection, Stagnation Analysis & Bedrock RCA (0:35 – 1:20)
- **Screen View:** Left: CloudWatch Logs stream refreshing live. Right: CloudWatch Metrics graph climbing.
- **Action:** Highlight invocations crossing the threshold ($\ge 20$). Show the alarm state transition to `ALARM`. Show orchestrator logs displaying SequenceMatcher stagnation ratio ($\ge 0.70$) and the incoming Bedrock JSON response.
- **Spoken Narrative:**
  > "Within seconds, our CloudWatch alarm breaches threshold, and EventBridge invokes our orchestrator. Instead of relying solely on invocation counts, LoopGuard performs inline fuzzy sequence matching across consecutive arguments. We detect an 84% parameter similarity—signaling semantic stagnation. The orchestrator calls Amazon Bedrock using Claude 3.5 Sonnet, producing a schema-validated root-cause diagnostic detailing the deadlock pattern and projected burn rate."

---

### Segment 3: Surgical Session Isolation (1:20 – 2:05)
- **Screen View:** Left: Browser hitting surgical remediation URL. Right: DynamoDB Management Console.
- **Action:** Execute the surgical quarantine action:
  ```bash
  curl -s "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<TOKEN>&action=session&session_id=session-live-01&incident_id=INC-LIVE"
  ```
  Refresh DynamoDB to show `SESSION#session-live-01` with an active TTL lock. Invoke the target function using `session-live-01` (returns HTTP 499), then invoke with `good-user-session` (returns HTTP 200).
- **Spoken Narrative:**
  > "Rather than taking down the entire service, we execute LoopGuard's surgical remediation. This writes an ephemeral 10-minute TTL lock into DynamoDB. When our runaway session attempts to continue, it is halted instantly with HTTP 499. Meanwhile, concurrent requests from healthy users continue processing with HTTP 200. Our blast radius is restricted to exactly one broken session."

---

### Segment 4: Emergency Global Override & Conclusion (2:05 – 2:45)
- **Screen View:** Left: Browser hitting global remediation URL. Right: Lambda Concurrency Management Console.
- **Action:** Trigger the emergency global kill switch. Refresh the AWS Console to show Reserved Concurrency set to 0.
  ```bash
  curl -s "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-LIVE"
  ```
- **Spoken Narrative:**
  > "If engineering determines an incident represents a systemic deployment bug, LoopGuard provides an emergency global override. We execute the global action—and in the AWS console, reserved concurrency is set to 0 instantly. All subsequent executions are throttled at the infrastructure layer before incurring further compute costs."

---

### Segment 5: Architecture Summary (2:45 – 3:00)
- **Screen View:** Full screen: VS Code displaying clean AWS SAM template and public GitHub repository structure.
- **Spoken Narrative:**
  > "Built natively on AWS using Lambda, EventBridge, CloudWatch, DynamoDB, Bedrock, and API Gateway. LoopGuard delivers real-time, closed-loop resilience for the serverless and AI agent era."
