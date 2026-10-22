#!/usr/bin/env node
// Offline row-resolution check for a DSH agent preset (0.2.0-rc.2+ declaration rows).
//
// Usage:
//   node check-preset-plugins.mjs --base <install-root> <file.yml> [...]
//
//   <install-root> = the directory whose node_modules holds @deepseek-ai/* for the
//   RUNNING dsh (find it from the live host's command line; see SKILL.md step 1).
//   <file.yml>     = a bundle cordis.patch.yml (rows under config.plugins of a
//                    @deepseek-ai/dsh-agent-preset declaration), a profile
//                    cordis.yml / cordis.patch.yml, or a legacy plugins list.
//
// It resolves each plugin row's `name` specifier against <install-root>'s
// node_modules, so a row naming a package that is not installed in the CURRENT
// installation is reported FAIL. Exit code 1 if any row fails.
//
// Resolution uses createRequire(<install-root>/package.json).resolve(): it honors
// package `exports` subpaths (`<pkg>/<sub>`) and needs no installed entry point in
// the script's own location. Do NOT use `import.meta.resolve(spec, parent)` here --
// this Node ignores the `parent` argument, so every specifier resolves against the
// script's own directory and a correct install reports a false all-FAIL.
//
// It does NOT activate plugins and does NOT validate `config` values: a PASS here
// means "the specifier resolves", not "the row mounts". See SKILL.md.

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";

const argv = process.argv.slice(2);
let base = process.cwd();
const files = [];
for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === "--base") {
    base = argv[i + 1];
    i += 1;
  } else files.push(argv[i]);
}
base = path.resolve(base);
if (files.length === 0) {
  console.error("usage: node check-preset-plugins.mjs --base <install-root> <file.yml> [...]");
  process.exit(2);
}

const baseRequire = createRequire(path.join(base, "package.json"));
const yaml = await import(pathToFileURL(baseRequire.resolve("js-yaml")).href);

// `!!js` is a Loader expression tag; keep it as an opaque marker, never evaluate it.
const jsTag = new yaml.default.Type("tag:yaml.org,2002:js", {
  kind: "scalar",
  construct: (data) => ({ __jsExpr: data }),
});
const SCHEMA = yaml.default.DEFAULT_SCHEMA.extend([jsTag]);

// Loader builtins are not packages.
const LOADER_BUILTINS = new Set(["cordis:group", "cordis:include"]);

/** Rows declared inside a `group: true` row's config, recursively. */
function nestedRows(row, out) {
  if (row && row.group === true && Array.isArray(row.config)) {
    for (const child of row.config) collectRow(child, out);
  }
}

/** Decide whether a YAML element is a target plugin row, a patch, or a declaration. */
function collectRow(node, out) {
  if (!node || typeof node !== "object" || Array.isArray(node)) return;
  if (Array.isArray(node.insert)) {
    for (const row of node.insert) collectRow(row, out);
    // An override patch (id + name, no insert) is also a row.
    if (typeof node.name === "string") out.push(node);
    return;
  }
  if (node.config && typeof node.config === "object" && Array.isArray(node.config.plugins)) {
    // A `@deepseek-ai/dsh-agent-preset` declaration: its plugins ARE the rows.
    (out.declarations ??= []).push({
      id: node.config.id,
      rowId: node.id,
      count: node.config.plugins.length,
    });
    out.push(node); // the declaration's own package must resolve too
    for (const row of node.config.plugins) collectRow(row, out);
    return;
  }
  if (typeof node.name === "string") out.push(node);
  nestedRows(node, out);
}

function walk(doc, out) {
  const nodes = Array.isArray(doc) ? doc : [doc];
  for (const node of nodes) collectRow(node, out);
}

let failures = 0;
let checked = 0;
for (const file of files) {
  const abs = path.resolve(file);
  let doc;
  try {
    doc = yaml.default.load(readFileSync(abs, "utf8"), { schema: SCHEMA });
  } catch (error) {
    console.log(`FILE ${abs}\n  PARSE FAIL: ${error.message}`);
    failures += 1;
    continue;
  }
  const rows = [];
  walk(doc, rows);
  console.log(`FILE ${abs}`);
  for (const d of rows.declarations ?? []) {
    console.log(
      `  declaration: loader row id=${d.rowId ?? "(none)"} preset id=${d.id ?? "(none)"} plugins=${d.count}`,
    );
  }
  // Deduplicate identical row ids (override patches restate the same row).
  const seen = new Set();
  for (const row of rows) {
    const spec = row.name;
    const id = row.id ?? "(no id)";
    if (seen.has(`${id}|${spec}`)) continue;
    seen.add(`${id}|${spec}`);
    if (LOADER_BUILTINS.has(spec)) {
      console.log(`  LOADER ${id} (${spec})`);
      continue;
    }
    checked += 1;
    try {
      const url = baseRequire.resolve(spec);
      console.log(`  PASS   ${id} (${spec}) -> ${url.replace(base + path.sep, "")}`);
    } catch (error) {
      failures += 1;
      console.log(`  FAIL   ${id} (${spec}) -> ${error.code ?? "ERR"}: ${error.message.split("\n")[0]}`);
    }
  }
}
console.log(`\nbase=${base}\nrows checked=${checked} failed=${failures}`);
process.exit(failures === 0 ? 0 : 1);
