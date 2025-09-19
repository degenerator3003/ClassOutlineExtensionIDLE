# ClassOutlineExt — IDLE Outline (Classes • Functions • Calls) + Find

Lightweight **IDLE** extension that shows a live outline of the current editor buffer.  
It nests a **calls:** list under each function and includes a **Find** dialog (Ctrl+F in the outline window) with direction and whole-word/wrap options. Double-click any row to jump to that line in the editor.

## Features
- **Outline tree** of `class`, `def`, `async def` (AST-based, no third-party deps).
- **Calls under each function** — shows syntactic call targets like `foo()`, `self.bar()`, `pkg.mod.func()` with line numbers; double-click to jump.
- **Find dialog** (press **Ctrl+F** while the outline window is focused):
  - **Direction:** Up / Down
  - **Whole word**, **Wrap around**
  - **Regex**, **Ignore case**
  - **Area filters:** search in **Classes**, **Functions**, **Calls**
  - Selects/expands the matching row and moves the editor caret to its line.
- **Opens near the editor**, auto-refreshes while you type, and preserves expanded nodes/selection.
- **Focus indicator** in the window title (e.g., green when focused, grey when not) so you know which window has the keys.

> Note: Call extraction is static (AST only). Dynamic/indirect calls may appear as `<call>`.

---

## Install

1. **Locate your `idlelib`** (the folder where IDLE looks for extensions):

    ```bash
    python -c "import idlelib, os; print(os.path.dirname(idlelib.__file__))"
    ```

2. **Copy `ClassOutlineExt.py`** into that folder.

    - **Windows (PowerShell):**

        ```powershell
        $dest = (python -c "import idlelib, os; print(os.path.dirname(idlelib.__file__))")
        Copy-Item .\ClassOutlineExt.py "$dest\ClassOutlineExt.py"
        ```

    - **macOS / Linux:**

        ```bash
        cp ClassOutlineExt.py "$(python -c 'import idlelib, os; print(os.path.dirname(idlelib.__file__))')"
        ```

3. **Enable the extension** in IDLE:
    - `Options → Configure IDLE… → Extensions` → enable **ClassOutlineExt** for the Editor, or
    - Add to `~/.idlerc/config-extensions.cfg`:

        ```ini
        [ClassOutlineExt]
        enable = True
        enable_shell = False
        enable_editor = True

        [ClassOutlineExt_bindings]
        toggle-outline-window = <Control-e>
        ```

4. **Restart IDLE**.

---

## Use

- Open a `.py` file in the IDLE **Editor**.
- Show/hide via **Edit → Outline** (or your `<Control-e>` binding).
- Expand a function to see its **calls:**; double-click a class/function/call to jump.
- Press **Ctrl+F** in the outline window to open **Find**:
  - Choose **Up/Down**, **Whole word**, **Wrap around**, **Regex/Ignore case**, and restrict to **Classes / Functions / Calls**.
  - Click **Find Next** (or press **Enter**) to select the next match and jump the editor caret.

---

## Troubleshooting

- **No “Outline” menu?** Make sure the file is in the same `idlelib` you printed in step 1, enable the extension, and restart IDLE.
- **Ctrl+F doesn’t open the dialog?** Give focus to the outline window (its title changes to the “focused” icon), then press **Ctrl+F**.
- **Calls look incomplete?** Only syntactic calls are listed; nested function bodies are indexed under their own node; dynamic calls show as `<call>`.

---

## License

MIT
