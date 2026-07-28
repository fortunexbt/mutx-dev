#!/usr/bin/env -S node --experimental-strip-types

import path from "path";

// @ts-expect-error Node's direct TypeScript runner requires an explicit extension.
import { writeDocsSearchIndex } from "../lib/docs/searchIndex.ts";

const outputPath = path.join(process.cwd(), "public", "docs-search-index.json");
const index = writeDocsSearchIndex(outputPath);

console.log(`Built deterministic docs search index for ${index.documents.length} routes -> ${outputPath}`);
