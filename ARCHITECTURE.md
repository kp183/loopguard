# LoopGuard System Architecture

This document outlines the system topology, component interactions, data schemas, and security boundaries for LoopGuard.

---

## 1. System Topology & Data Flow

LoopGuard separates application execution from the monitoring, diagnostic, and remediation control plane across four phases:

```
[Upstream Client / Test]
         │
         ▼
[GuardTargetFunction] ──(ConsistentRead=True)──> [DynamoDB: LoopGuardState (SESSION#<id>)]
         │                                                      │
    (Runaway Loop)                                         (HTTP 499 if Quarantined)
         ▼
[CloudWatch Metrics (Invocations >= 20 / 60s)]
         │
         ▼
[CloudWatch Alarm: LoopGuard-TargetInvocationsSpike]
         │
         ▼
[Amazon EventBridge Rule]
         │
         ▼
[GuardOrchestratorFunction]
   ├── 1. Defensive Dimension Parsing (dict or list format)
   ├── 2. CloudWatch Log Tail Fetch & Recursive JSON Log Unwrapping
   ├── 3. difflib.SequenceMatcher Stagnation Scoring (>= 0.70)
   ├── 4. Bedrock (Claude 3.5 Sonnet) RCA Synthesis
   ├── 5. Persist Incident Audit Record (INCIDENT#<id>)
   └── 6. Base Webhook Dispatch (Discord/Slack Embed with HMAC Links)
                                    │
                                    ▼
                          [Webhook Notification]
                           ├── Surgical Isolation: action=session
                           └── Global Kill Switch: action=global
                                    │
                                    ▼
                         [GuardHttpApi (/remediate)]
                                    │
                                    ▼
                        [GuardRemediationFunction]
                           ├── action=session ──> Write SESSION#<id> LOCK (TTL 600s) to DynamoDB
                           └── action=global  ──> Set Target Concurrency = 0 via Lambda API
```

### Phase A: Execution & In-Flight Circuit Evaluation
1. An upstream consumer or test harness invokes `LoopGuard-TargetFunction` passing `session_id`.
2. The target function performs a strongly consistent read against DynamoDB (`PK = SESSION#<session_id>`, `SK = LOCK`).
3. If an active quarantine lock is detected, execution halts immediately with HTTP 499 (`SURGICAL_QUARANTINE_ENFORCED`).
4. If healthy, execution proceeds. When configured in runaway mode, the function triggers asynchronous self-invocations, mutating query parameters to simulate an agent reformulating failing queries.

### Phase B: Anomaly Ingestion & Event Routing
1. Asynchronous execution cascades generate rapid metric spikes in Amazon CloudWatch.
2. When invocations reach or exceed 20 within a 60-second window, `LoopGuard-TargetInvocationsSpike` transitions from `OK` to `ALARM`.
3. CloudWatch emits an alarm state-change notification into Amazon EventBridge.
4. An EventBridge rule filters for this alarm event and invokes `LoopGuard-OrchestratorFunction`.

### Phase C: Diagnostic Synthesis & Stagnation Analysis
1. The orchestrator extracts the target function name, handling both dict and list metric dimension schemas.
2. The orchestrator retrieves recent log streams from CloudWatch Logs, recursively unpacking outer structured JSON envelopes to access inner application payloads.
3. The orchestrator executes `difflib.SequenceMatcher` over consecutive tool inputs. An average similarity score $\ge 0.70$ flags semantic stagnation.
4. The log tail and stagnation metrics are submitted to Amazon Bedrock (Anthropic Claude 3.5 Sonnet).
5. Bedrock outputs a validated JSON schema containing root cause, detected pattern, estimated burn rate, and operational recommendations.
6. The diagnostic record is persisted in DynamoDB (`PK = INCIDENT#<id>`, `SK = METADATA`).
7. The orchestrator dispatches a structured incident card containing remediation links directly to a configured Discord or Slack webhook.

### Phase D: Dual-Path Remediation Plane
The incident card exposes two distinct remediation paths via Amazon API Gateway (`/remediate`):
- **Surgical Remediation (`action=session`):** Writes an ephemeral 10-minute TTL lock record to DynamoDB (`PK = SESSION#<session_id>`, `SK = LOCK`). The runaway session is immediately blocked on subsequent attempts, while concurrent user traffic continues operating normally.
- **Global Override (`action=global`):** Invokes `lambda:PutFunctionConcurrency` setting reserved concurrency to 0. All subsequent function invocations return HTTP 429 (`TooManyRequestsException`).
- **Environment Reset:** `scripts/reset_demo.py` restores standard operational settings, removes concurrency overrides, and clears test locks.

---

## 2. DynamoDB Single-Table Schema (`LoopGuardState`)

The state table utilizes a single-table design with native Time-to-Live (TTL) enabled on the `ttl` attribute.

| Partition Key (PK) | Sort Key (SK) | Attributes | Description |
|---|---|---|---|
| `INCIDENT#<incident_id>` | `METADATA` | `target_function`, `session_id`, `alarm_name`, `stagnation_ratio`, `is_stagnant`, `root_cause_summary`, `detected_pattern`, `estimated_burn_rate`, `status`, `ttl` | Immutable audit record of the detected incident and Bedrock RCA diagnostic. |
| `SESSION#<session_id>` | `LOCK` | `incident_id`, `quarantine_type`, `created_at`, `ttl` | Active surgical quarantine item. Checked inline by target functions with strongly consistent reads. |

---

## 3. Mathematical & Algorithmic Formulations

### Semantic Stagnation Ratio ($S_{\text{stagnant}}$)
Fuzzy similarity across $N$ sequential tool-call arguments is computed using Python's Gestalt pattern matching algorithm:
$$S_{\text{stagnant}} = \frac{1}{N-1} \sum_{i=1}^{N-1} \frac{2 \cdot M(q_i, q_{i+1})}{|q_i| + |q_{i+1}|}$$

Where:
- $q_i, q_{i+1}$ represent consecutive query/argument strings extracted from execution logs.
- $M(q_i, q_{i+1})$ is the count of matching characters in matching subsequences.
- When $S_{\text{stagnant}} \ge 0.70$, the pipeline flags semantic retry stagnation.

### Token & Invocation Burn Velocity ($V_{\text{burn}}$)
Velocity is evaluated over the evaluation window $\Delta t$:
$$V_{\text{burn}} = \frac{\Delta \text{Invocations}}{\Delta t}$$

---

## 4. Security & Least-Privilege IAM Boundaries

LoopGuard enforces strict AWS least-privilege security policies across all execution roles:

### Target Execution Role (`GuardTargetFunctionRole`):
- Read-only permissions on DynamoDB (`dynamodb:GetItem`) scoped strictly to `LoopGuardState`.
- Scoped invocation rights (`lambda:InvokeFunction`) restricted solely to its own ARN for self-redrive testing.

### Orchestrator Role (`GuardOrchestratorFunctionRole`):
- Scoped read access on CloudWatch Logs (`logs:FilterLogEvents`, `logs:GetLogEvents`, `logs:DescribeLogStreams`) restricted to `arn:aws:logs:*:*:log-group:/aws/lambda/LoopGuard-*` and `arn:aws:logs:*:*:log-group:/aws/lambda/LoopGuard-*:*`.
- Read/write access on DynamoDB (`dynamodb:PutItem`, `dynamodb:UpdateItem`) scoped to `LoopGuardState`.
- Model execution rights (`bedrock:InvokeModel`) allowing foundation models and cross-region inference profiles (`arn:aws:bedrock:*::foundation-model/*` and `arn:aws:bedrock:*:*:inference-profile/*`).
- Scoped tag lookup permissions (`tag:GetResources`) for Tier 2 team resolution.

### Remediation Role (`GuardRemediationFunctionRole`):
- Concurrency management rights (`lambda:PutFunctionConcurrency`, `lambda:DeleteFunctionConcurrency`, `lambda:GetFunctionConcurrency`) restricted strictly to target functions matching `arn:aws:lambda:*:*:function:LoopGuard-*`.
- Read/write access on DynamoDB for updating incident metadata and writing session quarantine records.

---

## 5. Tooling & Verification Architecture

### Rehearsal Reset Utility (`scripts/reset_demo.py`)
To enable predictable, reliable recording rehearsals:
1. Calls `lambda:DeleteFunctionConcurrency` on `LoopGuard-TargetFunction`.
2. Calls `cloudwatch:SetAlarmState` to force `LoopGuard-TargetInvocationsSpike` back to `OK`.
3. Executes a batch purge of all items matching PK begins_with `SESSION#` in `LoopGuardState`.
