# No-Code Workflow

No-Code Workflow is a **visual workflow editor for LLM-powered structured text processing**.

**[Open App](https://nocode-workflow-gui.onrender.com)** · **[How it works](https://xingyuanzhao-project.github.io/nocode-workflow/quick-start/)** · **[GitHub](https://github.com/xingyuanzhao-project/nocode-workflow-public)** · **[HuggingFace](https://huggingface.co/spaces/xingyuanzhao/nocode-workflow)** · **[Cite this work](#citation)**

---

## What it does

A no-code application for processing structured text data with large language models. Upload a file, build a flow on a canvas by drag and drop, and run against any OpenAI-compatible model. Output supports CSV and JSON.

---

## Who it is for

Built for social science researchers who need systematic, reproducible LLM coding on large text corpora without writing code. It works for any practitioner with structured text data who wants model-agnostic processing without engineering overhead.

---

## Quick start

1. Open the app at [nocode-workflow-gui.onrender.com](https://nocode-workflow-gui.onrender.com)
2. Click **Input Node** — upload a file with a text column
3. Drag a **Processor** node — write an instruction and define an output schema
4. Drag an **LLM Call** node — select a provider and model (any OpenRouter-compatible endpoint)
5. Optionally attach a **Codebook** node to provide context and guide the LLM
6. Connect an **Output Node** and click **Run**

See the [documentation](https://xingyuanzhao-project.github.io/nocode-workflow/quick-start/) for detailed usage.

---

## Citation

If you use No-Code Workflow in your research, please cite:

```bibtex
@software{zhao2026nocodeworkflow,
  author       = {Xingyuan Zhao},
  title        = {No-Code Workflow: A No-Code Application for LLM-Powered Structured Text Processing},
  year         = {2026},
  url          = {https://huggingface.co/spaces/xingyuanzhao/nocode-workflow}
}
```