# ClassOutlineExt — IDLE Class & Function Outline

Lightweight **IDLE** extension that shows a tree of classes and functions for the current editor buffer.  
Double-click any item to jump to its line. The window updates as you edit and opens next to the editor.

## Features
- Class/function tree built from `ast` (no third-party deps).
- Double-click to jump to definition.
- Auto refresh (polling the buffer every second).
- Opens near the editor window; toggle open/close from the Edit menu.
- Optional global shortcut binding so the toggle works even when the outline window is focused.

## Installation
1. **Find your `idlelib` folder** (where IDLE looks for extensions):
   ```bash
   python -c "import idlelib, os; print(os.path.dirname(idlelib.__file__))"


2. **Copy the file** into that folder:
    
    - Windows (PowerShell):
        
        ```powershell
        $dest = (python -c "import idlelib, os; print(os.path.dirname(idlelib.__file__))")
        Copy-Item .\ClassOutlineExt.py "$dest\ClassOutlineExt.py"
        ```
        
    - macOS/Linux:
        
        ```bash
        cp ClassOutlineExt.py "$(python -c 'import idlelib, os; print(os.path.dirname(idlelib.__file__))')"
        ```
        
3. **Enable the extension** in IDLE:
    
    - In IDLE: `Options → Configure IDLE… → Extensions` → enable **ClassOutlineExt** for the Editor, or
        
    - Create/edit `~/.idlerc/config-extensions.cfg` and add:
        

        [ClassOutlineExt]
        enable = True
        enable_shell = False
        enable_editor = True
        
        [ClassOutlineExt_bindings]
        toggle-outline-window = <Control-e>
        
        
4. **Restart IDLE**.
    

## Usage

- Open a Python file in the IDLE Editor.
    
- Use `Edit → Outline` (or **Ctrl+E** if you set the binding) to show/hide the outline.
    
- Double-click a class/function to jump to its definition.
    
- Click **Refresh** if you’ve disabled auto updates.
    

## Notes

- The extension class is `ClassOutlineExt` and installs a menu command `_Outline` under **Edit**.
    
- Example config snippet (section name **must** match the class name) is shown above and in `conf_note.txt`.
    

## Troubleshooting

- **Don’t see “Outline” under Edit?** Confirm the file is in the same `idlelib` folder IDLE is using (step 1) and that the extension is enabled. Fully restart IDLE after changes.
    
- **Shortcut doesn’t work?** Ensure you added the `[ClassOutlineExt_bindings]` section and restart IDLE. Some key combos can be OS-reserved—try a different one if needed.
    

## License

MIT — see `LICENSE`.