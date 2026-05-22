/**
 * Playwright global setup.
 *
 * Brings up the docker compose stack (redis, celery worker, web)
 * before any spec runs. If the stack is already up the existing
 * containers are reused thanks to ``docker compose up``'s idempotent
 * behaviour. The ``--wait`` flag blocks until every service reports
 * healthy, which is what prevents the specs from hitting the editor
 * before the backend is ready to serve ``/api/flow/templates``.
 *
 * The spawn is done through :mod:`child_process` rather than via
 * Playwright's ``webServer`` array because compose output interleaves
 * poorly with Playwright's ``webServer`` log prefixing and makes
 * failures hard to read.
 */

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const DOCKER_COMPOSE_TIMEOUT_MS = 180_000;

function resolveProjectRoot(): string {
  const here = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(here, "..", "..", "..");
}

export default async function globalSetup(): Promise<void> {
  const projectRoot = resolveProjectRoot();
  const result = spawnSync(
    "docker",
    ["compose", "up", "-d", "--wait"],
    {
      cwd: projectRoot,
      stdio: "inherit",
      timeout: DOCKER_COMPOSE_TIMEOUT_MS,
      shell: true,
    },
  );
  if (result.status !== 0) {
    throw new Error(
      `docker compose up failed with exit code ${String(result.status)}`,
    );
  }
}
