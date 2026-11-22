# LAL · OWASP LLM Application Security Lab

English · [한국어](README.ko.md)

LAL maintains the infrastructure, container runtime, installation scripts, and verification tools used in the OWASP Top 10 for LLM Applications labs. The repository supports the AWS GPU-based OWASP practice environment, Bedrock-based guardrails and observability, and the mission services used by the LLM Defense Lab (LDL) Control Center.

The [course repository](https://github.com/gasbugs/owasp-top-10-for-llm) contains the learner-facing notes. The [LDL Terraform repository](https://github.com/gasbugs/llm-defense-lab) deploys the dedicated LDL EC2 instance and installs the runtime from a pinned commit of this repository.

> Some lab applications are intentionally vulnerable. Run them in an authorized, isolated practice environment.

## Choose a setup path

| Environment | Where to start |
| --- | --- |
| AWS GPU lab for OWASP Top 10 practice | [Student quickstart](docs/STUDENT-QUICKSTART.md) |
| Amazon Bedrock API practice | [Bedrock API lab](bedrock-api-lab/) |
| NeMo Guardrails and Presidio on WSL | [Guardrails setup](docs/GUARDRAILS-SETUP.md) |
| LDL mission environment on dedicated AWS EC2 | [LDL deployment](https://github.com/gasbugs/llm-defense-lab) |

For the GPU path, Terraform provisions a single on-demand GPU instance in the learner's AWS account. The quickstart covers AWS account checks, the learner's public IPv4 allowlist, installation, and daily start and stop procedures. The Bedrock and WSL paths use their own setup instructions.

## Repository layout

| Path | Contents |
| --- | --- |
| [infrastructure/terraform/](infrastructure/terraform/) | AWS infrastructure for the GPU lab |
| [infrastructure/scripts/student/](infrastructure/scripts/student/) | Installation, preflight, start, stop, and cleanup commands |
| [infrastructure/compose/compose.yaml](infrastructure/compose/compose.yaml) | Services and runtime configuration for the GPU lab |
| [llm-security-control-plane/](llm-security-control-plane/) | Bedrock gateways, guardrails, and LDL mission services |
| [tools/install-guided-practice.sh](tools/install-guided-practice.sh) | LDL runtime installer |
| [tests/](tests/) | Unit, browser, and end-to-end verification |

For deployment details, see the [architecture guide](docs/ARCHITECTURE.md), [advanced Terraform options](docs/TERRAFORM-ADVANCED-OPTIONS.md), and [troubleshooting guide](docs/TROUBLESHOOTING.md). For release and runtime verification, see [image builds](docs/INSTRUCTOR-IMAGE-BUILD.md) and [live validation](docs/LIVE-VALIDATION.md).

## License

Original portions of this repository are available under the [PolyForm Noncommercial License 1.0.0](LICENSE) for noncommercial use. Commercial use requires a [separate written license](COMMERCIAL-LICENSE.md). Earlier revisions distributed under the MIT License retain their original terms. See the [licensing notice](NOTICE.md) and [third-party licenses](THIRD-PARTY-LICENSES.md) for details.
