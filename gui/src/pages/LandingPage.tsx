/**
 * Landing page that shows the project README content.
 * Rendered when the user clicks the "No-Code Workflow" title in the NavBar.
 */

import { useState } from "react";
import { NavLink } from "react-router-dom";

const CITATION_BIBTEX = `@software{zhao2026nocodeworkflow,
  author       = {Xingyuan Zhao},
  title        = {No-Code Workflow: A No-Code Application for LLM-Powered Structured Text Processing},
  year         = {2026},
  url          = {https://huggingface.co/spaces/xingyuanzhao/nocode-workflow}
}`;

export default function LandingPage(): JSX.Element {
  const [copied, setCopied] = useState(false);

  function handleCite() {
    navigator.clipboard.writeText(CITATION_BIBTEX).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="mb-2 text-3xl font-bold tracking-tight">
        No-Code Workflow
      </h1>
      <p className="mb-6 text-lg text-muted-foreground">
        A <strong>visual workflow editor</strong> for LLM-powered structured text
        processing.
      </p>

      <div className="mb-8 flex flex-wrap gap-3">
        <NavLink
          to="/flows"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Open App
        </NavLink>
        <a
          href="https://docs.nocodeworkflow.app/quick-start/"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
        >
          How it works
        </a>
        <a
          href="https://github.com/xingyuanzhao-project/nocode-workflow-public"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
        >
          GitHub
        </a>
        <a
          href="https://huggingface.co/spaces/xingyuanzhao/nocode-workflow"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
        >
          HuggingFace
        </a>
        <button
          onClick={handleCite}
          className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
        >
          {copied ? "Copied!" : "Cite this work"}
        </button>
      </div>

      <hr className="my-6" />

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">What it does</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          A no-code application for processing structured text data with large
          language models. Upload a file, build a flow on a canvas by drag and
          drop, and run against any OpenAI-compatible model. Output supports CSV
          and JSON.
        </p>
      </section>

      <hr className="my-6" />

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">Who it is for</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Built for social science researchers who need systematic, reproducible
          LLM coding on large text corpora without writing code. It works for any
          practitioner with structured text data who wants model-agnostic
          processing without engineering overhead.
        </p>
      </section>

      <hr className="my-6" />

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">Quick start</h2>
        <ol className="list-inside list-decimal space-y-2 text-sm text-muted-foreground">
          <li>
            Click{" "}
            <NavLink to="/flows" className="font-medium text-foreground underline">
              Open Flow Editor
            </NavLink>{" "}
            above or the <strong>Flows</strong> tab
          </li>
          <li>
            Click <strong>Input Node</strong> — upload a file with a text column
          </li>
          <li>
            Drag a <strong>Processor</strong> node — write an instruction and
            define an output schema
          </li>
          <li>
            Drag an <strong>LLM Call</strong> node — select a provider and model
            (any OpenRouter-compatible endpoint)
          </li>
          <li>
            Optionally attach a <strong>Codebook</strong> node to provide context
            and guide the LLM
          </li>
          <li>
            Connect an <strong>Output Node</strong> and click <strong>Run</strong>
          </li>
        </ol>
      </section>

      <hr className="my-6" />

      <section className="mb-8">
        <h2 className="mb-3 text-xl font-semibold">Citation</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          If you use No-Code Workflow in your research, please cite:
        </p>
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs">
{`@software{zhao2026nocodeworkflow,
  author       = {Xingyuan Zhao},
  title        = {No-Code Workflow: A No-Code Application for LLM-Powered Structured Text Processing},
  year         = {2026},
  url          = {https://huggingface.co/spaces/xingyuanzhao/nocode-workflow}
}`}
        </pre>
      </section>

      <hr className="my-6" />

      <footer className="text-xs text-muted-foreground">
        <a
          href="https://github.com/xingyuanzhao-project/nocode-workflow-public"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-foreground"
        >
          GitHub
        </a>
        {" · "}
        <a
          href="https://docs.nocodeworkflow.app/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-foreground"
        >
          Documentation
        </a>
      </footer>
    </div>
  );
}
