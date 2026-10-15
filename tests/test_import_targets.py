"""Guard that every first-party import resolves inside this repo.

The generic processing core now lives in the separate `fluxcore` package
(installed into ep_cntl); its old in-repo paths (domain/, services/data/,
services/metadata/core/, top-level orchestration/ and infrastructure/
modules) no longer exist here. Function-level imports of those old paths
would only fail when that code path runs, so this scans every module and
test for imports of a local top-level package whose target file or package
is missing.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_TOPS = {
    "domain",
    "fluxtools",
    "infrastructure",
    "services",
    "orchestration",
    "tasks",
    "tools",
    "ui",
}


def _resolves(module: str) -> bool:
    path = ROOT.joinpath(*module.split("."))
    return path.with_suffix(".py").exists() or path.is_dir()


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, []
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module, [a.name for a in node.names]


class ImportTargetsTestCase(unittest.TestCase):
    def test_local_imports_resolve(self):
        missing = []
        for file in sorted(ROOT.rglob("*.py")):
            if ".git" in file.parts or "__pycache__" in file.parts:
                continue
            for lineno, module, names in _imports(ast.parse(file.read_text())):
                if module.split(".")[0] not in LOCAL_TOPS:
                    continue
                ok = _resolves(module) and all(
                    not ROOT.joinpath(*module.split(".")).is_dir()
                    or _resolves(f"{module}.{n}")
                    or n == "*"
                    for n in names
                )
                if not ok:
                    missing.append(
                        f"{file.relative_to(ROOT)}:{lineno} {module} {names}"
                    )
        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
