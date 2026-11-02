<!---Unreviewed AI slop below
## Components

### Human Operator

The Human Operator owns the deployment and operation of the complete system.

Typical responsibilities include:

* provisioning infrastructure;
* configuring credentials;
* starting and stopping services;
* connecting to the Agent Runtime;
* reviewing Backend logs and submissions;
* updating pinned software versions;
* operating the Inference API when it is self-hosted.

### Control Centre

The Control Centre is the operator-facing machine used to deploy, configure, access, and observe the system.

It contains:

* a pinned VS Code version;
* a pinned Remote SSH extension;
* an optional pinned Codex VS Code extension;
* SSH access to the Agent Runtime;
* administrative access to the Backend;
* access to Backend logs and submissions.

The Codex VS Code extension belongs on the Control Centre. It is an operator interface and is not required for unattended execution inside the Agent Runtime.

### Agent Runtime

The Agent Runtime is a clean, isolated Ubuntu environment in which the agent executes.

It contains:

* a pinned Ubuntu image;
* pinned operating-system dependencies;
* a pinned Codex CLI version;
* a pinned Codex configuration;
* a dedicated runtime user;
* a dedicated working directory;
* network access to the Backend API;
* network access to the Inference API;
* SSH access from the Control Centre.

The Agent Runtime is the Backend API client. It pulls tasks and pushes completed results.

The Agent Runtime must not have direct access to:

* Backend source data;
* ground-truth data;
* Backend databases;
* Backend submission directories;
* Backend logs;
* unnecessary host files or directories.

### Inference API

The Inference API provides model inference to the Agent Runtime.

OpenAI is the default provider, but the architecture does not require a specific provider. The Inference API may be externally hosted or operated by the Human Operator.

The Inference API communicates with the Agent Runtime. It does not communicate directly with the Backend.

### Backend

The Backend owns the task data, validation, persistence, logs, and submissions.

The current FastAPI implementation exposes:

* `GET /pull` — streams an NDJSON task to the Agent Runtime;
* `POST /push` — validates and stores the completed submission.

For each accepted submission, the Backend writes:

```text
submissions/<timestamp>/response.jsonl
submissions/<timestamp>/response.md
```

`response.jsonl` contains the submitted result followed by the ground truth.

`response.md` contains a human-readable comparison for review.

## Reproducibility

All relevant versions should be explicitly recorded in source control.

For example:

```dotenv
# Control Centre
VS_CODE_VERSION=
REMOTE_SSH_EXTENSION_VERSION=
CODEX_EXTENSION_VERSION=

# Agent Runtime
UBUNTU_IMAGE_URL=
UBUNTU_IMAGE_SHA256=
CODEX_CLI_VERSION=

# Backend
BACKEND_VERSION=
PYTHON_VERSION=
```

Version ownership is divided as follows:

| Dependency              | Location                               |
| ----------------------- | -------------------------------------- |
| VS Code                 | Control Centre                         |
| Remote SSH extension    | Control Centre                         |
| Codex VS Code extension | Control Centre, optional               |
| VS Code Server          | Agent Runtime, installed by Remote SSH |
| Ubuntu image            | Agent Runtime                          |
| Codex CLI               | Agent Runtime                          |
| Codex configuration     | Agent Runtime                          |
| Backend application     | Backend                                |
| Database schema         | Backend                                |

A full VS Code desktop installation is not required inside the Agent Runtime. Remote SSH installs the matching VS Code Server when the Control Centre connects.

## Provisioning

The provisioning implementation may use Lima, a cloud VM, a container, a dedicated server, or another isolation mechanism.

The architecture depends on the resulting runtime contract rather than a particular provisioning provider.

A provisioned Agent Runtime must provide:

* the expected Ubuntu version;
* the expected architecture;
* the expected Codex CLI version;
* the expected Codex configuration;
* a writable working directory;
* SSH connectivity;
* Backend API connectivity;
* Inference API connectivity;
* isolation from Backend storage.

The current Lima implementation already defines:

* the Ubuntu image;
* CPU, memory, and disk resources;
* the runtime user and home directory;
* the mounted working directory;
* the Codex configuration;
* SSH verification;
* working-directory verification;
* recreation of a clean runtime.

It should additionally:

* install an explicitly pinned Codex CLI version;
* verify the Ubuntu image checksum;
* verify the installed Codex CLI version;
* avoid mounting Backend files into the Agent Runtime;
* load credentials from a secret-management mechanism;
* record the complete version matrix in source control.

## Command Naming

For a reusable command that creates, verifies, starts, and enters the runtime, use:

```text
agent-runtime
```

For a one-shot provisioning script, use:

```text
provision-agent-runtime.sh
```

`deploy.sh` is less precise because the script provisions only the Agent Runtime rather than deploying the complete architecture.

Example layout:

```text
bin/
  agent-runtime

scripts/
  provision-agent-runtime.sh

assets/
  hcr_augment_agent_architecture.svg
```

## API Interaction

Pull a task:

```bash
curl -N http://backend.example/pull
```

Submit a completed task:

```bash
curl -N \
  -H 'Content-Type: application/json' \
  --data @submission.json \
  http://backend.example/push
```

The Agent Runtime should receive the Backend base URL through configuration rather than embedding it in the runtime image.

For example:

```bash
export HCR_BACKEND_URL="https://backend.example"
```

## Security Boundary

The central security boundary is between the Agent Runtime and the Backend.

The Agent Runtime should be treated as an isolated and potentially destructive execution environment. It should receive only:

* the task returned by the Backend API;
* the credentials required for permitted API operations;
* the source repository or working files required for the task;
* access to the configured Inference API.

The Backend retains:

* authoritative source data;
* ground truth;
* submission history;
* application logs;
* database access;
* validation logic;
* operator review artefacts.

Even when the Codex sandbox is configured with unrestricted local access, that access remains confined to the isolated Agent Runtime.

## Design Principles

* Keep the Agent Runtime and Backend separate.
* Make the Agent Runtime an API client, not a data-store peer.
* Keep human operation distinct from software orchestration.
* Pin all software that affects execution.
* Provision clean runtimes reproducibly.
* Give the agent only the access required for its task.
* Keep Backend data and ground truth outside the Agent Runtime.
* Ensure all inference-mediated Backend activity passes through the Agent Runtime.
--->
