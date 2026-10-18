"""Run the notebook and save the executed copy under outputs/."""

import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    notebook = nbformat.read(ROOT / "preprocessing.ipynb", as_version=4)
    nbformat.validate(notebook)
    destination = ROOT / "outputs/preprocessing.executed.ipynb"
    destination.parent.mkdir(exist_ok=True)
    namespace = {"__name__": "__main__"}
    count = 0
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        count += 1
        cell.execution_count = count
        cell.outputs = []
        print(f"Ячейка {count}", flush=True)
        captured = io.StringIO()
        try:
            with redirect_stdout(captured), redirect_stderr(captured):
                exec(
                    compile(cell.source, f"preprocessing.ipynb:cell{count}", "exec"),
                    namespace,
                )
        finally:
            cell.outputs = [
                nbformat.v4.new_output(
                    "stream", name="stdout", text=captured.getvalue()
                )
            ]
            print(captured.getvalue(), end="", flush=True)
            nbformat.write(notebook, destination)
    print(f"Сохранено: {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
