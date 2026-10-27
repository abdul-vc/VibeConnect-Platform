import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import esbuild from "esbuild";

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (err) {
    const code = err && err.code;
    if (code === "ERR_UNSUPPORTED_DIR_IMPORT" || code === "ERR_MODULE_NOT_FOUND") {
      let resolvedPath;
      if (specifier.startsWith("file://")) {
        resolvedPath = fileURLToPath(specifier);
      } else if (context.parentURL) {
        resolvedPath = path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier);
      } else {
        resolvedPath = path.resolve(specifier);
      }

      if (fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory()) {
        const files = fs.readdirSync(resolvedPath);
        const testFile = files.find((f) => f.endsWith(".test.ts"));
        if (testFile) {
          return {
            shortCircuit: true,
            url: pathToFileURL(path.join(resolvedPath, testFile)).href,
          };
        }
      }
    }
    throw err;
  }
}

export async function load(url, context, nextLoad) {
  if (/\.(png|jpe?g|svg|webp|ico|gif|css)$/i.test(url)) {
    return {
      format: "module",
      shortCircuit: true,
      source: "export default '/mock-asset.png';",
    };
  }
  if (url.endsWith(".tsx") || url.endsWith(".ts")) {
    const filePath = fileURLToPath(url);
    const source = fs.readFileSync(filePath, "utf8");
    const isTsx = url.endsWith(".tsx") || source.includes("<");
    const result = esbuild.transformSync(source, {
      loader: isTsx ? "tsx" : "ts",
      format: "esm",
      jsx: "automatic",
      target: "esnext",
    });
    return {
      format: "module",
      shortCircuit: true,
      source: result.code,
    };
  }
  return nextLoad(url, context);
}
