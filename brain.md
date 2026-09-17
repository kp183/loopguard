# LOOPGUARD: AGENT MASTER CONTEXT & MEMORY (brain.md)

## 1. Project Identity & Hackathon Metadata
- **Project Name:** LoopGuard
- **Repository Prefix:** `LoopGuard-` / `Guard`
- **Hackathon:** Bharat Builds Tour (WeMakeDevs × AWS Builder Center)
- **Track:** Ship It (Deployed, Live AWS Architecture)
- **Team:** Team Kroid
- **Evaluation Mechanics:** Scored strictly on public GitHub repository, written documentation, and a maximum 3-minute demo video. No live Q&A. Evaluators look for production-grade systems engineering, operational resilience, and AWS architecture.
- **Separation Boundary:** Structurally and conceptually independent from prior projects (Clarity, AgentLens). LoopGuard is an infrastructure-level, closed-loop circuit breaker modifying runtime concurrency and DynamoDB session states.

---

## 2. Strict Operational Directives ("Never Do" Rules)
1. **DO NOT** use the words "Sentinel", "Analyst", "CoPilot", or "Triage" in any file name, function name, variable, or log message. Use **Guard** exclusively (`GuardTargetFunction`, `GuardOrchestratorFunction`, `GuardRemediationFunction`).
2. **DO NOT** use Titan Text Embeddings or cosine vector distance in the hot execution path. Stagnation detection must remain sub-millisecond using Python standard library `difflib.SequenceMatcher` over raw query strings extracted from log tails.
3. **DO NOT** build complex Slack Block Kit OAuth authentication or signature verification. Incident dispatches must use webhook embeds with HMAC-tokenized callback URLs targeting Amazon API Gateway (`/remediate?token=...&action=...`).
4. **DO NOT** implement account-wide IAM credential revocations. Remediation must operate strictly through:
   - **Surgical Session Isolation:** 10-minute DynamoDB TTL lock (`SESSION#<session_id>`).
   - **Emergency Global Throttle:** Target function concurrency set to 0 (`PutFunctionConcurrency(0)`).
5. **DO NOT** let Tier 2 (team-based routing) block Tier 1. Tier 1 must be completely demoable on its own with base webhook alerts dispatched directly by the orchestrator.

---

## 3. Core System Architecture & Service Responsibilities

| Component | AWS Resource | File Path | Core Responsibility |
|---|---|---|---|
| **State Store** | `AWS::DynamoDB::Table` (`LoopGuardState`) | `template.yaml` | Single-table store with TTL tracking incident audit records and active session quarantine locks. |
| **Target Function** | `AWS::Serverless::Function` (`LoopGuard-TargetFunction`) | `src/target/app.py` | Monitored workload. Checks DynamoDB session lock inline (`ConsistentRead=True`). Simulates runaway retry loops when triggered. Capped at 50 concurrent executions. |
| **Metric Alarm** | `AWS::CloudWatch::Alarm` (`LoopGuard-TargetInvocationsSpike`) | `template.yaml` | Tracks Invocations $\ge 20$ in a 60-second window. Fires state-change event on breach. |
| **Routing Bus** | `AWS::Events::Rule` | `template.yaml` | Pattern matches CloudWatch Alarm State Change where `state.value = ALARM`, invoking orchestrator. |
| **Orchestrator** | `AWS::Serverless::Function` (`LoopGuard-OrchestratorFunction`) | `src/orchestrator/app.py` | Unpacks nested JSON logs, computes difflib similarity ($\ge 0.70$ threshold), prompts Bedrock Claude 3.5 Sonnet for RCA, and posts webhook alert cards. |
| **Control API** | `AWS::Serverless::HttpApi` (`LoopGuard-ControlApi`) | `template.yaml` | Exposes authenticated `/remediate` endpoint. |
| **Remediation** | `AWS::Serverless::Function` (`LoopGuard-RemediationFunction`) | `src/remediation/app.py` | Validates auth token. Executes surgical quarantine (writes DynamoDB TTL lock) or global shutdown (`ReservedConcurrentExecutions: 0`). |
| **Reset Tooling** | CLI Script (Python / Boto3) | `scripts/reset_demo.py` | Clears Lambda concurrency overrides, forces alarm to OK, and purges session locks for demo retakes. |

---

## 4. Known Architectural Traps & Mandatory Fixes

### Trap 1: CloudWatch Structured Logging JSON Encapsulation
- **Problem:** In `template.yaml`, `LoggingConfig: LogFormat: JSON` causes AWS Lambda to wrap stdout into an outer JSON object (`{"timestamp": "...", "level": "INFO", "message": "..."}`).
- **Rule:** In `src/orchestrator/app.py`, `fetch_recent_log_events` must parse the outer JSON and check if `data["message"]` contains a nested JSON string. If so, it must parse `data["message"]` to extract `query_payload` and `session_id`. Never assume top-level keys.

### Trap 2: CloudWatch Alarm Metric Dimension Format Variability
- **Problem:** EventBridge alarm state change details can format metric dimensions either as a dictionary (`{"FunctionName": "..."}`) or as an array of objects (`[{"name": "FunctionName", "value": "..."}]`).
- **Rule:** In `src/orchestrator/app.py`, `extract_target_function_name` must handle both dictionary lookups and list iterations defensively.

### Trap 3: Bedrock Cross-Region Inference Profiles
- **Problem:** In many AWS regions, Anthropic Claude 3.5 Sonnet invocations must use inference profiles (e.g., `us.anthropic.claude-3-5-sonnet-20240620-v1:0`), which fail against standard foundation model IAM ARNs.
- **Rule:** In `template.yaml`, the orchestrator IAM policy must allow both:
  - `arn:aws:bedrock:*::foundation-model/*`
  - `arn:aws:bedrock:*:*:inference-profile/*`

### Trap 4: CloudWatch Logs Stream Wildcard Scope
- **Problem:** Boto3's `describe_log_streams` API call fails with `AccessDenied` if the IAM policy only authorizes the log group without the trailing stream wildcard.
- **Rule:** `template.yaml` must authorize both `arn:aws:logs:*:*:log-group:/aws/lambda/LoopGuard-*` and `arn:aws:logs:*:*:log-group:/aws/lambda/LoopGuard-*:*`.

### Trap 5: DynamoDB Session Check Consistency
- **Problem:** High-frequency Lambda retry loops can beat DynamoDB eventual consistency, causing a quarantined session to execute 1–2 extra times after the lock is written.
- **Rule:** `src/target/app.py` must always use `ConsistentRead=True` on `table.get_item()`.

---

## 5. DynamoDB State Schema Reference (`LoopGuardState`)

### Incident Record
- **Partition Key (PK):** `INCIDENT#<incident_id>` (e.g., `INCIDENT#INC-1726589000`)
- **Sort Key (SK):** `METADATA`
- **Attributes:**
  - `target_function`: String (e.g., `LoopGuard-TargetFunction`)
  - `session_id`: String (e.g., `session-live-01`)
  - `alarm_name`: String (e.g., `LoopGuard-TargetInvocationsSpike`)
  - `stagnation_ratio`: String (e.g., `0.842`)
  - `is_stagnant`: Boolean (`true` / `false`)
  - `root_cause_summary`: String (Generated by Bedrock)
  - `detected_pattern`: String (e.g., `SEMANTIC_RETRY_STAGNATION`)
  - `estimated_burn_rate`: String (e.g., `~40 invocations/min`)
  - `status`: String (`ANALYZED`, `REMEDIATED_SURGICAL_LOCK`, `REMEDIATED_GLOBAL_CONCURRENCY_ZERO`)
  - `ttl`: Number (Epoch timestamp + 86400s)

### Surgical Quarantine Lock Record
- **Partition Key (PK):** `SESSION#<session_id>` (e.g., `SESSION#session-live-01`)
- **Sort Key (SK):** `LOCK`
- **Attributes:**
  - `incident_id`: String (Reference to parent incident)
  - `quarantine_type`: String (`SURGICAL_SESSION_ISOLATION`)
  - `ttl`: Number (Epoch timestamp + 600s)

---

## 6. Mathematical & Heuristic Formulations

### 1. Semantic Stagnation Ratio ($S_{\text{stagnant}}$)
Fuzzy similarity across $N$ sequential tool-call arguments extracted from logs:
$$S_{\text{stagnant}} = \frac{1}{N-1} \sum_{i=1}^{N-1} \frac{2 \cdot M(q_i, q_{i+1})}{|q_i| + |q_{i+1}|}$$

Where:
- $q_i, q_{i+1}$ are consecutive query strings.
- $M(q_i, q_{i+1})$ is the number of matching characters calculated by Python's `difflib.SequenceMatcher`.
- **Threshold Rule:** If $S_{\text{stagnant}} \ge 0.70$, flag `is_stagnant = True`.

### 2. Invocation Velocity ($V_{\text{inv}}$)
$$V_{\text{inv}} = \frac{\Delta \text{Invocations}}{\Delta t}$$
Evaluated over $\Delta t = 60\text{ seconds}$. Alarm trips when $\sum \text{Invocations} \ge 20$.

---

## 7. Rehearsal & Verification CLI Runbook

### Clean Rebuild & Deploy
```bash
sam build
sam deploy --guided
```

### Trigger Live Runaway Incident
```bash
aws lambda invoke \
  --function-name LoopGuard-TargetFunction \
  --invocation-type Event \
  --payload '{"runaway_mode": true, "session_id": "session-live-01"}' \
  out.json
```

### Verify Alarm & Orchestrator Logs
```bash
aws cloudwatch describe-alarms --alarm-names LoopGuard-TargetInvocationsSpike --query "MetricAlarms[0].StateValue"
sam logs -n LoopGuard-OrchestratorFunction --tail
```

### Execute Surgical Remediation (Primary Action)
```bash
curl -i "https://<api-id>.execute-api.<region>.amazonaws.com/remediate?token=<TOKEN>&action=session&session_id=session-live-01&incident_id=INC-TEST"
```

### Prove Dual Blast Radii Behavior
```bash
# 1. Offending session returns HTTP 499 (Blocked)
aws lambda invoke \
  --function-name LoopGuard-TargetFunction \
  --payload '{"runaway_mode": false, "session_id": "session-live-01"}' \
  out.json && cat out.json

# 2. Healthy session returns HTTP 200 (Success)
aws lambda invoke \
  --function-name LoopGuard-TargetFunction \
  --payload '{"runaway_mode": false, "session_id": "good-session-99"}' \
  out.json && cat out.json
```

### Execute Global Override (Secondary Action)
```bash
curl -i "https://<api-id>.execute-api.<region>.amazonaws.com/remediate?token=<TOKEN>&action=global&function=LoopGuard-TargetFunction&incident_id=INC-TEST"
aws lambda get-function-concurrency --function-name LoopGuard-TargetFunction
```

### Fast Rehearsal Reset (< 5 Seconds)
```bash
python scripts/reset_demo.py
```

---

## 8. Current Implementation Status
- [x] `docs/PRD.md`: Synchronized. Acceptance criteria defined. Tier 1 / Tier 2 cleanly separated.
- [x] `ARCHITECTURE.md`: Synchronized. Single-table DynamoDB schema and mathematical formulations documented.
- [x] `template.yaml`: Configured with safety cap (`ReservedConcurrentExecutions: 50`), Bedrock inference profile IAM scope, CloudWatch stream wildcards, and `WebhookUrl` parameter.
- [x] `src/target/app.py`: Configured with consistent read DynamoDB session checks, query mutation simulation, and self-invocation loop.
- [x] `src/orchestrator/app.py`: Defensive dimension extraction, recursive JSON log unwrapping, difflib similarity calculation, Bedrock Claude 3.5 Sonnet RCA with deterministic fallback, and zero-dependency Discord/Slack webhook dispatch.
- [x] `src/remediation/app.py`: Implements dual blast radii: surgical 10-minute DynamoDB TTL lock (`action=session`) and emergency global throttle (`action=global`).
- [x] `scripts/reset_demo.py`: Automated environment restoration utility.
