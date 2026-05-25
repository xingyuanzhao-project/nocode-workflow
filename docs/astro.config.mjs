import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://xingyuanzhao-project.github.io",
  base: "/academic-pipeline",
  integrations: [
    starlight({
      title: "Academic Pipeline",
      description:
        "Visual flow editor for LLM-powered text processing on structured data.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/xingyuanzhao-project/academic-pipeline",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      sidebar: [
        { label: "Overview", slug: "" },
        {
          label: "Getting Started",
          items: [
            { label: "Installation", slug: "getting-started/installation" },
            { label: "Quick Start", slug: "getting-started/quick-start" },
          ],
        },
        {
          label: "Architecture",
          items: [
            { label: "System Design", slug: "architecture/system-design" },
            { label: "Flow Engine", slug: "architecture/flow-engine" },
            { label: "Node Types", slug: "architecture/node-types" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "Configuration", slug: "reference/configuration" },
            { label: "Citation", slug: "reference/citation" },
          ],
        },
      ],
    }),
  ],
});
