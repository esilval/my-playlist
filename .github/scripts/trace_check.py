"""Trazabilidad en el CI (constitución, principio 2).

Ejecuta `sdd trace` en cada feature de specs/ y falla si alguna tiene un error. Una
feature en curso, con alguna tarea sin cerrar, puede tener todavía requisitos MUST sin
prueba (E-REQ-NO-TEST): se escriben al implementar sus tareas. Todos los demás errores
bloquean siempre, incluida una tarea cerrada sin su prueba (E-DONE-NO-TEST). Cuando la
feature tiene todas sus tareas cerradas, cualquier error bloquea.

Uso: python3 .github/scripts/trace_check.py <ruta a sdd.py>
"""

import json
import subprocess
import sys
from pathlib import Path

# Lo que puede faltar mientras una feature se está implementando.
ALLOWED_WHILE_OPEN = {"E-REQ-NO-TEST"}


def check(sdd: str, slug: str) -> bool:
    Path(".sdd").mkdir(exist_ok=True)
    Path(".sdd/current").write_text(slug + "\n", encoding="utf-8")
    subprocess.run([sys.executable, sdd, "trace"], check=False)
    report = json.loads(
        subprocess.run(
            [sys.executable, sdd, "trace", "--json"], capture_output=True, text=True, check=False
        ).stdout
    )
    open_tasks = [task["id"] for task in report["tasks"] if task["state"] != "done"]
    errors = [finding for finding in report["findings"] if finding["severity"] == "error"]
    if open_tasks:
        errors = [finding for finding in errors if finding["code"] not in ALLOWED_WHILE_OPEN]
        print(f"{slug}: en curso ({len(open_tasks)} tareas abiertas); un MUST sin prueba no bloquea aún.")
    for finding in errors:
        print(f"::error title={slug} {finding['code']}::{finding['message']}")
    return not errors


def main() -> int:
    sdd = sys.argv[1]
    features = sorted(path.name for path in Path("specs").glob("[0-9]*") if path.is_dir())
    results = []
    for slug in features:
        print(f"::group::{slug}")
        results.append(check(sdd, slug))
        print("::endgroup::")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
