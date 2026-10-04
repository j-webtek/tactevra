# Tactevra AI documentation

For a user introduction, start with [getting started](../../../docs/GETTING_STARTED.md)
and [current capabilities](../../../PROJECT_STATUS.md). This directory contains
developer contracts, research records, and implementation plans.

Contributors should start with the
[shared AI-to-arm workplan](SHARED_AI_ARM_WORKPLAN.md). It is the common stage
board for the AI/model and arm/runtime workstreams. Detailed results are kept in
the separate, append-only [AI/arm evidence ledger](EVIDENCE_LEDGER.md), so the
current plan stays readable while the complete history remains available.

Cross-stack latency and throughput optimization is coordinated by the
[AI-to-arm operational efficiency plan](../../docs/AI_TO_ARM_OPERATIONAL_EFFICIENCY_PLAN.md).
It defines common timing milestones, immutable-versus-dynamic work, allowed
parallelism, optimization stages, and evidence gates without granting hardware
authority.

The maintained operating procedure is the
[AI work, testing, and evidence handbook](AI_WORK_AND_EVIDENCE_HANDBOOK.md).
Its companion [AI work registry](AI_WORK_REGISTRY.json) assigns every tracked
AI test to one workstream and links its source, documentation, evidence,
limitations, and next gate.

Then read [the integration contract](CONTRACT.md), followed by the
[model-to-arm translation assurance process](MODEL_TO_ARM_TRANSLATION_ASSURANCE.md),
then [the roadmap](ROADMAP.md).
The [model research note](MODEL_RESEARCH.md) records the published Llama
methods and what still needs a baseline experiment.

The [AI system baseline and implementation plan](AI_SYSTEM_BASELINE_AND_IMPLEMENTATION_PLAN.md)
records what is implemented, what the evidence establishes, how an Ollama or
llama.cpp multimodal observer fits beside the precision pose model, and the
prioritized path to a physically qualified system.

These documents include both implemented offline components and proposed work.
Read each document's date, result, and limitations. Current Tactevra
capabilities and physical status remain in the repository's
[project status](../../../PROJECT_STATUS.md),
[software architecture](../../docs/ARCHITECTURE.md), and code. The AI documents
must be revised when those contracts change.

Tactevra is the product name. The lowercase `rocell` name remains in package,
command, schema, configuration, and historical identifiers for compatibility;
see the repository [glossary](../../../docs/GLOSSARY.md).
