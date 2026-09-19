# LoopGuard 3-Minute Video Rehearsal Script

**Target Duration:** 180 seconds maximum (Target: 2m 50s)  
**Display Configuration:** 1080p, split-screen (Left: Terminal & Chat/Browser, Right: AWS Management Console)  

---

## Rehearsal Timing Breakdown

### Beat 1: The Hook & Before/After Contrast (0:00 – 0:35)
- **Screen View:** Split screen: Terminal on left, CloudWatch console on right.
- **Action:** Run the chaos trigger command:
  ```bash
  aws lambda invoke \
    --function-name LoopGuard-TargetFunction \
    --invocation-type Event \
    --payload '{"runaway_mode": true, "session_id": "sess-live-payments-88"}' \
    out.json
  ```
- **Spoken Narrative:**
  > "Serverless architectures and AI agents fail by looping, not crashing. When an LLM agent hits a deadlock, it reformulates queries repeatedly, burning compute budgets while returning healthy HTTP 200s. Traditional AWS billing alerts lag 8 to 24 hours behind. Without LoopGuard, an unhandled retry loop can run unchecked, driving hundreds of parallel invocations. With LoopGuard, that loop is intercepted and quarantined in under 60 seconds with zero collateral downtime. Let's trigger our Chaos Harness on live AWS infrastructure right now."

---

### Beat 2: Detection, Fuzzy Stagnation ($S_{\text{stagnant}}$), Groq RCA & Team Tag Routing (0:35 – 1:15)
- **Screen View:** CloudWatch Alarm transitions to `ALARM`. Switch to Webhook.site tab showing Channel A (`Payments-Core`).
- **Action:** Show CloudWatch Alarm firing. Highlight orchestrator log lines showing fuzzy stagnation ratio ($\ge 0.70$), Bedrock primary failover to Groq Llama 3.3 70B live RCA, and `tag:GetResources` dynamic team routing.
- **Spoken Narrative:**
  > "Within 60 seconds, our CloudWatch alarm trips, and EventBridge invokes the orchestrator. LoopGuard does not rely on simple traffic volume. Using fuzzy sequence matching across consecutive query arguments, we detect an 87.6% parameter similarity—proving semantic retry thrashing. Concurrently, our healthy traffic test proves normal queries score under 0.27, eliminating false positives. To guarantee resilience, our diagnostic cascade executed multi-cloud failover to Groq Llama 3.3 70B, synthesizing a structured root-cause analysis in under 400 milliseconds. Using the AWS Resource Groups Tagging API, LoopGuard resolves the function's team tag dynamically—routing this alert directly to Payments-Core."

---

### Beat 3: One-Click Surgical Session Isolation & 0% Blast Radius (1:15 – 1:55)
- **Screen View:** Webhook incident card in browser $\to$ Click signed remediation link. Then Terminal running bad invoke (HTTP 499) and healthy invoke (HTTP 200).
- **Action:** 
  1. Click the HMAC-signed surgical quarantine link in the webhook alert card. Show confirmation page.
  2. In DynamoDB Console, show `SESSION#sess-live-payments-88` lock written with 600s TTL.
  3. Invoke target with rogue session `sess-live-payments-88` $\to$ returns **HTTP 499** (`SURGICAL_QUARANTINE_ENFORCED`).
  4. Invoke target with legitimate session `sess-clean-12` $\to$ returns **HTTP 200** (`SUCCESS`). Blast radius = 0%.
- **Spoken Narrative:**
  > "Rather than shutting down the entire service, the on-call engineer clicks the cryptographically signed surgical isolation link directly in the alert. In milliseconds, a 10-minute TTL lock is written to DynamoDB. When our runaway session attempts to re-invoke, it is halted instantly at the edge with HTTP 499. But watch what happens when a legitimate user checks out at the exact same time: their request returns HTTP 200. Our blast radius is strictly 0%."

---

### Beat 4: S3 Postmortem Artifact & Emergency Global Kill Switch (1:55 – 2:30)
- **Screen View:** Browser clicking 📥 Download SRE Incident Postmortem (.md). Then triggering `action=global` to show Reserved Concurrency set to 0.
- **Action:** Click the S3 download button to show the rendered Markdown postmortem. Then trigger global throttle:
  ```bash
  curl -s "https://<api-id>.execute-api.us-east-1.amazonaws.com/remediate?token=<HMAC_TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-LIVE"
  ```
- **Spoken Narrative:**
  > "Remediation doesn't just stop the bleeding—it autonomously compiles an SRE incident postmortem, uploads it to a private Amazon S3 bucket, and generates an authenticated pre-signed download URL with full diagnostic provenance. For systemic code defects, an engineer can execute the emergency global kill switch, dropping function concurrency to 0 at the infrastructure layer, causing subsequent invocations to throttle with HTTP 429."

---

### Beat 5: Fast Rehearsal Reset Utility & Architecture Summary (2:30 – 2:50)
- **Screen View:** Running `python scripts/reset_demo.py` (finishes in 5s). GitHub repository overview.
- **Action:** Run reset script, show console refreshing back to standard state.
- **Spoken Narrative:**
  > "Between drills or production incidents, our reset tooling restores concurrency throttles, alarms, and state locks in five seconds. Built natively on AWS using Lambda, EventBridge, CloudWatch, DynamoDB, Bedrock, S3, and API Gateway, LoopGuard brings closed-loop operational resilience to the serverless and AI era."
