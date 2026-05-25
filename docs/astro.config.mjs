import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://xingyuanzhao-project.github.io",
  base: "/academic-pipeline",
  integrations: [
    starlight({
      title: "Academic Pipeline",
      description:
        "LLM-powered text processing for structured research data.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/xingyuanzhao-project/academic-pipeline-public",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      sidebar: [
        { label: "Overview", slug: "" },
        { label: "How it works", slug: "quick-start" },
        { label: "Citation", slug: "citation" },
      ],
    }),
  ],
});
