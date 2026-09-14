---
name: gemini-notebook
description: >-
  Uses the owner's Gemini Notebook capability as persistent source-grounded
  project research beneath Hermes. Use for project notebooks, source admission,
  research synthesis, decision evidence, or notebook-to-VEKL workflows.
---

# Gemini Notebook

## Role

Gemini Notebook is a grounded research memory surface. It is not Project Truth
and does not replace VEKL/GraphRAG.

## Notebook taxonomy

For each project, prefer bounded notebooks:

- Canon Notebook
- Research Notebook
- Design Intelligence Notebook
- Operations Notebook
- Decision Evidence Notebook

## Workflow

1. Load Project Truth and existing VEKL before external research.
2. Build an admitted source packet with project ID, source hashes and trust labels.
3. Route `knowledge_grounding` or `notebook_research` through the Google job planner.
4. Add only explicit sources; do not silently widen scope.
5. Preserve citations/source identifiers in returned research.
6. Validate contradictions against Project Truth.
7. Admit useful findings to VEKL with provenance.
8. Project Truth changes require the normal owner-authorised authority process.

## Consumer vs Enterprise

- `gemini_notebook` is the owner-account consumer surface and may require an authorised browser/share/artifact bridge.
- `gemini_notebook_enterprise` is an optional programmatic Cloud transport.

Do not scrape private Notebook APIs or browser session cookies.
