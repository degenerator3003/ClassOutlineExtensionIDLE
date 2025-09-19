# class_outline.py — IDLE extension: show tree of classes & functions.
from __future__ import annotations
import ast
import hashlib
import sys
import traceback
import tkinter as tk
from tkinter import ttk


class ClassOutlineExt:
    """
    IDLE extension class.

    IDLE will instantiate this with an EditorWindow instance `editwin`.
    We provide a menudefs entry so IDLE can insert the command into the Edit menu.
    """
    menudefs = [
        ('edit', [
            ('_Outline', '<<toggle-outline-window>>'),
        ])
    ]

    def __init__(self, editwin):
        self.editwin = editwin               # IDLE EditorWindow
        self.text = editwin.text             # underlying Text widget
        self._win = None                     # Toplevel for outline
        self._tree = None                    # ttk.Treeview widget
        self._after_id = None                # id of scheduled after() call

        # used to avoid redundant rebuilds
        self._last_src_hash = None

        self._bound_virtuals = []      # list of virtual event names we bound (<<...>>)
        self._bound_sequences = []     # list of raw key sequences we bound ('<Control-...>')
        # optional mapping of raw sequences to method names you want handled by extension
        # e.g. {'<Control-Shift-KeyRelease-Insert>': 'z_in_event'}
        self._global_key_map = {}


    def _register_global_shortcuts(self):
        """Bind global virtual events and raw key sequences while the window is open."""
        # 1) Bind virtual events defined in menudefs (<<...>>)
        try:
            for menu_name, items in getattr(self, "menudefs", []):
                for label, ve in items:
                    if isinstance(ve, str) and ve.startswith("<<") and ve.endswith(">>"):
                        # bind a lambda that captures the virtual event string
                        try:
                            # add=True keeps other handlers intact
                            self._win.bind_all(ve, lambda ev, ve=ve: self._call_virtual_handler(ve), add=True)
                            self._bound_virtuals.append(ve)
                        except Exception:
                            pass
        except Exception:
            pass

        # 2) Bind any explicit raw key sequences the extension wants
        for seq, handler_name in self._global_key_map.items():
            try:
                # call the method by name; capture handler_name in lambda
                self._win.bind_all(seq, lambda ev, hn=handler_name: self._call_method_by_name(hn, ev), add=True)
                self._bound_sequences.append(seq)
            except Exception:
                pass

    def _unregister_global_shortcuts(self):
        """Unbind previously bound global virtual events and sequences."""
        for ve in getattr(self, "_bound_virtuals", []):
            try:
                self._win.unbind_all(ve)
            except Exception:
                pass
        self._bound_virtuals.clear()

        for seq in getattr(self, "_bound_sequences", []):
            try:
                self._win.unbind_all(seq)
            except Exception:
                pass
        self._bound_sequences.clear()

    def _call_virtual_handler(self, ve):
        """
        Given a virtual event string like '<<z-in>>', call the method
        'z_in_event' on this extension instance if present.
        """
        name = ve.strip("<>").replace("-", "_") + "_event"
        handler = getattr(self, name, None)
        if handler:
            try:
                # call with a synthetic event object or None; many handlers accept event
                handler(None)
            except TypeError:
                try:
                    handler()
                except Exception:
                    pass

    def _call_method_by_name(self, method_name, event=None):
        """Call a method by name safely (pass the event if the signature accepts it)."""
        handler = getattr(self, method_name, None)
        if not handler:
            return
        try:
            handler(event)
        except TypeError:
            try:
                handler()
            except Exception:
                pass

    def toggle_outline_window_event(self, event=None):
        """
        Toggle the outline window. Use visibility (winfo_ismapped) rather than mere existence.
        """
        try:
            win = self._win
            # If it doesn't exist or was destroyed, create & show it
            if win is None or not tk.Toplevel.winfo_exists(win):
                self._show_window()
                return

            # If it exists: toggle depending on whether it's currently mapped (visible)
            try:
                if win.winfo_ismapped():
                    # currently visible -> hide it
                    self._hide_window()
                else:
                    # exists but hidden -> restore it
                    try:
                        win.deiconify()
                        win.lift()
                        try:
                            self._register_global_shortcuts()
                        except Exception:
                            pass
                        # try to give keyboard focus back
                        try:
                            win.focus_force()
                        except Exception:
                            pass
                        # ensure periodic updates resume
                        self._schedule()
                    except Exception:
                        # fallback: fully rebuild/show
                        self._show_window()
            except Exception:
                # if anything goes wrong querying state, attempt to show a fresh one
                self._show_window()
        except Exception:
            # ultimate fallback: attempt to show
            try:
                self._show_window()
            except Exception:
                pass


    def _show_window(self):
        # If already created, just show it
        if self._win is not None and tk.Toplevel.winfo_exists(self._win):
            self._win.deiconify()
            return

        # Prefer the Editor's top-level as parent
        try:
            parent = getattr(self.editwin, "top", None) or self.text.winfo_toplevel()
        except Exception:
            parent = None

        # Create the Toplevel first (so we can use it as master and measure sizes)
        self._win = tk.Toplevel(parent)
        self._win.title("Outline — Classes & Functions")
        self._win.protocol("WM_DELETE_WINDOW", self._hide_window)

        # Try to make it transient to the editor window (gives window manager hints)
        try:
            if parent is not None:
                self._win.transient(parent)
        except Exception:
            pass

        # Build UI (frames, tree, buttons) exactly as you already had.
        # -- begin UI creation (paste your existing UI creation code here) --
        frame = ttk.Frame(self._win, padding=(6, 6, 6, 6))
        frame.pack(fill="both", expand=True)

        self._tree = ttk.Treeview(frame, show="tree")
        self._tree.pack(fill="both", expand=True, side="top")
        self._tree.bind("<Double-1>", self._on_tree_double)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", side="bottom", pady=(6, 0))
        ttk.Button(btn_frame, text="Refresh", command=self._update).pack(side="left")
        ttk.Button(btn_frame, text="Close", command=self._hide_window).pack(side="right")
        # -- end UI creation (if your original code had more widgets, keep them) --

        # Ensure widgets are created and sizes known
        self._win.update_idletasks()

        # Positioning logic: prefer right of editor, then left, else center
        try:
            # parent geometry
            if parent is not None and parent.winfo_ismapped():
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
            else:
                # fallback to text widget geometry
                px = self.text.winfo_rootx()
                py = self.text.winfo_rooty()
                pw = self.text.winfo_width()
                ph = self.text.winfo_height()

            # our window size
            ww = self._win.winfo_width()
            wh = self._win.winfo_height()

            # screen geometry (handles multi-monitor)
            screen_w = self._win.winfo_screenwidth()
            screen_h = self._win.winfo_screenheight()

            margin = 10
            # try right
            x_right = px + pw + margin
            y_align = py  # align top edges; you can adjust to center vertically: py + (ph-wh)//2
            if x_right + ww <= screen_w:
                x = x_right
                y = max(0, min(y_align, screen_h - wh))
            else:
                # try left
                x_left = px - ww - margin
                if x_left >= 0:
                    x = x_left
                    y = max(0, min(y_align, screen_h - wh))
                else:
                    # center over parent
                    x = px + max(0, (pw - ww) // 2)
                    y = py + max(0, (ph - wh) // 2)
                    # ensure inside screen
                    x = max(0, min(x, screen_w - ww))
                    y = max(0, min(y, screen_h - wh))

            # apply geometry
            self._win.geometry(f"+{x}+{y}")
        except Exception:
            # if any geometry calculation fails, let window manager place it
            pass

        # initial population and periodic update
        self._update()
        self._schedule()
        self._register_global_shortcuts()

    def _hide_window(self):
        """
        Hide the outline window (withdraw) and cancel scheduled updates.
        Keep the Toplevel object so it can be restored with .deiconify().
        """
        if self._win is None:
            return
        try:
            self._unregister_global_shortcuts()
            # withdraw (hide) rather than destroy, so we can restore later
            if tk.Toplevel.winfo_exists(self._win):
                try:
                    self._win.withdraw()
                except Exception:
                    # if withdraw fails, attempt to destroy to avoid orphaned widgets
                    try:
                        self._win.destroy()
                    except Exception:
                        pass
        finally:
            # cancel periodic updates either way
            try:
                if self._after_id:
                    self.text.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


    def _schedule(self):
        self._cancel_schedule()
        try:
            self._after_id = self.text.after(1000, self._periodic)
        except Exception:
            self._after_id = None

    def _cancel_schedule(self):
        if self._after_id:
            try:
                self.text.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _periodic(self):
        self._update()
        self._schedule()

    # ------------------ improved update logic ------------------
    def _update(self):
        """Parse editor buffer with ast and rebuild tree view, but skip rebuild if unchanged."""
        if self._tree is None:
            # not visible yet; nothing to update
            return

        src = self.text.get("1.0", "end-1c")
        # fast content fingerprint — skip rebuild if identical
        src_hash = hashlib.sha1(src.encode("utf-8")).hexdigest()
        if src_hash == self._last_src_hash:
            return
        self._last_src_hash = src_hash

        try:
            parsed = ast.parse(src)
        except Exception:
            # Parsing failed: show a single informative node
            self._set_tree_items([("Parse error (invalid syntax)", "err", 1, None)])
            return

        items = []

        def visit(node, parent_qual=None):
            for n in getattr(node, "body", []):
                if isinstance(n, ast.ClassDef):
                    qual = f"{parent_qual}.{n.name}" if parent_qual else n.name
                    items.append((qual, "class", n.lineno, parent_qual))
                    visit(n, parent_qual=qual)
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "async def" if isinstance(n, ast.AsyncFunctionDef) else "def"
                    qual = f"{parent_qual}.{n.name}" if parent_qual else n.name
                    items.append((qual, kind, n.lineno, parent_qual))
                    visit(n, parent_qual=qual)
                else:
                    visit(n, parent_qual=parent_qual)

        visit(parsed, parent_qual=None)
        self._set_tree_items(items)

    def _set_tree_items(self, items):
        """
        Given items list of (qual_name, kind, lineno, parent_qual) build treeview.
        Preserve expanded nodes and selection across rebuilds.
        """
        # preserve expanded iids and selection (iids will be qual strings)
        def all_iids(tree, parent=""):
            for child in tree.get_children(parent):
                yield child
                yield from all_iids(tree, child)

        prev_expanded = set()
        prev_selection = tuple(self._tree.selection()) if self._tree else ()
        if self._tree:
            for iid in all_iids(self._tree, ""):
                try:
                    if self._tree.item(iid, "open"):
                        prev_expanded.add(iid)
                except Exception:
                    pass

        # Clear existing
        for iid in list(self._tree.get_children("")):
            self._tree.delete(iid)

        # Build mapping parent_qual -> list of (qual_name, kind, lineno)
        mapping = {}
        for qual, kind, lineno, parent in items:
            mapping.setdefault(parent, []).append((qual, kind, lineno))

        def insert_children(parent_iid, parent_qual):
            children = mapping.get(parent_qual, [])
            children.sort(key=lambda t: t[2])
            for qual, kind, lineno in children:
                short_name = qual.split(".")[-1]
                text = f"{short_name}  —  {kind}  (L{lineno})"
                # use the qualified name as the iid so we can restore open/selection by qual
                iid = qual
                # insert with explicit iid and store lineno in values
                try:
                    self._tree.insert(parent_iid, "end", iid=iid, text=text, values=(lineno,))
                except Exception:
                    # fallback: let Treeview choose iid
                    iid = self._tree.insert(parent_iid, "end", text=text, values=(lineno,))
                insert_children(iid, qual)

        insert_children("", None)

        # Restore expanded state where possible
        for iid in prev_expanded:
            try:
                if iid and self._tree.exists(iid):
                    self._tree.item(iid, open=True)
            except Exception:
                pass

        # Restore selection (if still present)
        new_selection = [s for s in prev_selection if self._tree.exists(s)]
        if new_selection:
            try:
                self._tree.selection_set(new_selection)
                self._tree.see(new_selection[0])
            except Exception:
                pass

    def _on_tree_double(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self._tree.item(iid, "values")
        if not vals:
            return
        try:
            lineno = int(vals[0])
        except Exception:
            return
        try:
            self.editwin.text.mark_set("insert", f"{lineno}.0")
            self.editwin.text.see(f"{lineno}.0")
            self.editwin.text.focus_set()
        except Exception:
            try:
                self.editwin.text.focus()
            except Exception:
                pass

# end of file
