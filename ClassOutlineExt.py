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
        self._func_calls = {}  # qual -> list[(label, lineno)]

        self._find_win = None
        self._find_vars = None  # tuple of tk vars; created when dialog opens
        self._find_last_iid = None

        self._title_base = "Outline — Classes & Functions"
        self._title_focused_prefix = "🟢 "   # pick any symbol you like
        self._title_unfocused_prefix = "❌ "  # pick any symbol you like

    def _apply_title(self, focused: bool):
        """Update window title based on focus state."""
        if not self._win:
            return
        prefix = self._title_focused_prefix if focused else self._title_unfocused_prefix
        try:
            self._win.title(f"{prefix}{self._title_base}")
        except Exception:
            pass

    def _format_callee(self, func_expr):
        """Return a readable label for ast.Call.func."""
        import ast
        # foo(...)
        if isinstance(func_expr, ast.Name):
            return func_expr.id
        # obj.attr(...), possibly chained: pkg.mod.func
        if isinstance(func_expr, ast.Attribute):
            parts = []
            cur = func_expr
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            else:
                parts.append("<expr>")
            parts.reverse()
            return ".".join(parts)
        # something else (callable return, subscript, lambda, etc.)
        return "<call>"

    def _collect_calls(self, func_node, current_class=None):
        """Collect (label, lineno) for calls inside func_node, but
        skip nested defs/classes to avoid double counting."""
        import ast
        calls = []

        class CV(ast.NodeVisitor):
            def visit_Call(self, node):
                try:
                    label = self.outer._format_callee(node.func)
                except Exception:
                    label = "<call>"
                ln = getattr(node, "lineno", 1)
                calls.append((label, ln))
                self.generic_visit(node)

            # stop at nested scopes (but we won't call visit() on the root FunctionDef)
            def visit_FunctionDef(self, node): pass
            def visit_AsyncFunctionDef(self, node): pass
            def visit_ClassDef(self, node): pass

        cv = CV()
        cv.outer = self
        # IMPORTANT: walk only the body of the current function
        for stmt in getattr(func_node, "body", []):
            cv.visit(stmt)

        # de-dup but keep first occurrence order
        seen, out = set(), []
        for lab, ln in calls:
            key = (lab, ln)
            if key in seen:
                continue
            seen.add(key)
            out.append((lab, ln))
        return out




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
                        self._apply_title(True)
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
        #self._win.title("Outline — Classes & Functions")
        self._apply_title(True)
        self._win.bind("<FocusIn>",  lambda e: self._apply_title(True))
        self._win.bind("<FocusOut>", lambda e: self._apply_title(False))
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
        self._win.bind("<Control-f>", self._open_find_dialog)
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
                    self._apply_title(False)
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

        # before parsing/visiting (right after parsing succeeds)
        self._func_calls = {}

        items = []

        def visit(node, parent_qual=None, class_stack=()):
            for n in getattr(node, "body", []):
                if isinstance(n, ast.ClassDef):
                    qual = f"{parent_qual}.{n.name}" if parent_qual else n.name
                    items.append((qual, "class", n.lineno, parent_qual))
                    visit(n, parent_qual=qual, class_stack=class_stack + (n.name,))
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "async def" if isinstance(n, ast.AsyncFunctionDef) else "def"
                    qual = f"{parent_qual}.{n.name}" if parent_qual else n.name
                    items.append((qual, kind, n.lineno, parent_qual))
                    # NEW: collect calls for this function only (not nested defs)
                    current_class = class_stack[-1] if class_stack else None
                    self._func_calls[qual] = self._collect_calls(n, current_class=current_class)
                    # still visit for nested defs (but calls are collected per their own node)
                    visit(n, parent_qual=qual, class_stack=class_stack)
                else:
                    visit(n, parent_qual=parent_qual, class_stack=class_stack)

        visit(parsed, parent_qual=None, class_stack=())
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
            children.sort(key=lambda t: t[2])  # by lineno
            for qual, kind, lineno in children:
                short_name = qual.split(".")[-1]
                text = f"{short_name}  —  {kind}  (L{lineno})"
                iid = qual
                try:
                    self._tree.insert(parent_iid, "end", iid=iid, text=text, values=(lineno,))
                except Exception:
                    iid = self._tree.insert(parent_iid, "end", text=text, values=(lineno,))

                # build normal AST children first
                insert_children(iid, qual)

                # NEW: calls subtree for functions
                if kind in ("def", "async def"):
                    calls = self._func_calls.get(qual, [])
                    if calls:
                        # header
                        header_iid = f"{qual}::calls"
                        try:
                            self._tree.insert(iid, "end", iid=header_iid, text="calls:", values=())
                        except Exception:
                            header_iid = self._tree.insert(iid, "end", text="calls:", values=())
                        # each call row (double-click jumps to call line via stored value)
                        for idx, (label, cln) in enumerate(calls):
                            cid = f"{qual}::call::{idx}:{cln}"
                            ctext = f"→ {label}  (L{cln})"
                            try:
                                self._tree.insert(header_iid, "end", iid=cid, text=ctext, values=(cln,))
                            except Exception:
                                self._tree.insert(header_iid, "end", text=ctext, values=(cln,))


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


    def _open_find_dialog(self, event=None):
        # Reuse if already open
        if self._find_win and tk.Toplevel.winfo_exists(self._find_win):
            self._find_win.deiconify()
            self._find_win.lift()
            try:
                self._find_vars[0].focus_set()  # pattern entry
            except Exception:
                pass
            return

        # Build a small dialog
        self._find_win = tk.Toplevel(self._win)
        self._find_win.title("Find in Outline")
        self._find_win.transient(self._win)
        self._find_win.resizable(False, False)
        self._find_win.protocol("WM_DELETE_WINDOW", self._find_win.withdraw)

        f = ttk.Frame(self._find_win, padding=6); f.pack(fill="both", expand=True)

        # Row 0: pattern
        ttk.Label(f, text="Find:").grid(row=0, column=0, sticky="w")
        pat = tk.StringVar(master=self._find_win, value="")
        ent = ttk.Entry(f, textvariable=pat, width=34)
        ent.grid(row=0, column=1, columnspan=6, sticky="we", padx=(6,0))
        ent.bind("<Return>", lambda e: self._do_find_next())

        # Row 1: regex / ignore case
        rx  = tk.IntVar(master=self._find_win, value=0)   # regex?
        ic  = tk.IntVar(master=self._find_win, value=1)   # ignore case?
        ttk.Checkbutton(f, text="Regex",        variable=rx).grid(row=1, column=1, sticky="w", pady=(6,0))
        ttk.Checkbutton(f, text="Ignore case",  variable=ic).grid(row=1, column=2, sticky="w", pady=(6,0))

        # Row 2: direction + whole + wrap
        ttk.Label(f, text="Direction:").grid(row=2, column=0, sticky="w", pady=(6,0))
        dirv = tk.IntVar(master=self._find_win, value=1)   # 1=Down, -1=Up
        ttk.Radiobutton(f, text="Down", variable=dirv, value=1).grid(row=2, column=1, sticky="w", pady=(6,0))
        ttk.Radiobutton(f, text="Up",   variable=dirv, value=-1).grid(row=2, column=2, sticky="w", pady=(6,0))

        whole = tk.IntVar(master=self._find_win, value=0)
        wrap  = tk.IntVar(master=self._find_win, value=1)
        ttk.Checkbutton(f, text="Whole word",  variable=whole).grid(row=2, column=3, sticky="w", pady=(6,0))
        ttk.Checkbutton(f, text="Wrap around", variable=wrap).grid(row=2, column=4, sticky="w", pady=(6,0))

        # Row 3: area filters
        ttk.Label(f, text="Search in:").grid(row=3, column=0, sticky="w", pady=(6,0))
        in_cls = tk.IntVar(master=self._find_win, value=1)
        in_fun = tk.IntVar(master=self._find_win, value=1)
        in_cal = tk.IntVar(master=self._find_win, value=1)
        ttk.Checkbutton(f, text="Classes",   variable=in_cls).grid(row=3, column=1, sticky="w", pady=(6,0))
        ttk.Checkbutton(f, text="Functions", variable=in_fun).grid(row=3, column=2, sticky="w", pady=(6,0))
        ttk.Checkbutton(f, text="Calls",     variable=in_cal).grid(row=3, column=3, sticky="w", pady=(6,0))

        # Row 4: buttons
        btnf = ttk.Frame(f); btnf.grid(row=4, column=0, columnspan=6, sticky="e", pady=(8,0))
        ttk.Button(btnf, text="Find Next", command=self._do_find_next).pack(side="left")
        ttk.Button(btnf, text="Close", command=self._find_win.withdraw).pack(side="left", padx=(6,0))

        # Save vars (extended tuple: add dirv, whole, wrap at the end)
        self._find_vars = (ent, pat, rx, ic, in_cls, in_fun, in_cal, dirv, whole, wrap)

        # place near parent
        self._find_win.update_idletasks()
        try:
            px = self._win.winfo_rootx(); py = self._win.winfo_rooty()
            self._find_win.geometry(f"+{px+40}+{py+40}")
        except Exception:
            pass

        ent.focus_set()


    def _do_find_next(self):
        if not self._tree or not self._find_vars:
            return
        ent, pat, rx, ic, in_cls, in_fun, in_cal, dirv, whole, wrap = self._find_vars
        pattern = pat.get()
        if not pattern:
            return

        # What to search in
        kinds = set()
        if in_cls.get(): kinds.add("class")
        if in_fun.get(): kinds.update(("def", "async def"))
        if in_cal.get(): kinds.add("call")

        # Flatten items
        items = self._gather_tree_items(kinds=kinds)
        n = len(items)
        if n == 0:
            return

        # Determine start index
        start_idx = -1
        ids = [iid for iid, _, _ in items]
        sel = self._tree.selection()
        if sel and sel[0] in ids:
            start_idx = ids.index(sel[0])
        elif self._find_last_iid and self._find_last_iid in ids:
            start_idx = ids.index(self._find_last_iid)

        # Build matcher
        import re
        flags = re.IGNORECASE if ic.get() else 0

        if rx.get():
            pat_str = pattern
            if whole.get():
                pat_str = rf"\b(?:{pattern})\b"
            try:
                cre = re.compile(pat_str, flags)
                def matches(s): return cre.search(s) is not None
            except re.error:
                return
        else:
            if whole.get():
                # true whole-word match for plain search
                cre = re.compile(rf"\b{re.escape(pattern)}\b", flags)
                def matches(s): return cre.search(s) is not None
            else:
                needle = pattern.lower() if ic.get() else pattern
                def matches(s):
                    s2 = s.lower() if ic.get() else s
                    return needle in s2

        # Direction & wrap
        direction = dirv.get()  # 1=down, -1=up

        def try_match(idx):
            iid, kind, label = items[idx]
            if matches(label):
                self._find_last_iid = iid
                self._expand_to(iid)
                try:
                    self._tree.selection_set(iid)
                    self._tree.see(iid)
                except Exception:
                    pass
                self._navigate_to_iid(iid)
                return True
            return False

        if direction == 1:
            # DOWN
            if start_idx == -1:
                start_idx = -1
            # first pass: start_idx+1 .. n-1
            for idx in range(start_idx + 1, n):
                if try_match(idx): return
            if wrap.get():
                for idx in range(0, start_idx + 1):
                    if try_match(idx): return
        else:
            # UP
            if start_idx == -1:
                start_idx = n
            # first pass: start_idx-1 .. 0
            for idx in range(start_idx - 1, -1, -1):
                if try_match(idx): return
            if wrap.get():
                for idx in range(n - 1, start_idx - 1, -1):
                    if try_match(idx): return

        # no match -> beep
        try:
            (self._find_win or self._win).bell()
        except Exception:
            pass


    def _gather_tree_items(self, kinds):
        """Flatten tree into (iid, kind, label) for the requested kinds."""
        out = []
        def kind_of(iid, text):
            # calls header
            if iid.endswith("::calls"):
                return None
            # call leaf
            if "::call::" in iid:
                return "call"
            # infer from node text: "... —  class/def/async def (L...)"
            try:
                left, right = text.split("—", 1)
                kpart = right.strip().split("(", 1)[0].strip()
                return kpart if kpart in ("class", "def", "async def") else None
            except Exception:
                return None

        def walk(parent=""):
            for iid in self._tree.get_children(parent):
                text = self._tree.item(iid, "text") or ""
                k = kind_of(iid, text)
                if k and k in kinds:
                    # label to search: use displayed text (includes name and kind)
                    out.append((iid, k, text))
                walk(iid)
        walk("")
        return out

    def _expand_to(self, iid):
        # open all ancestors so selection is visible
        p = iid
        parents = []
        while True:
            p = self._tree.parent(p)
            if not p:
                break
            parents.append(p)
        for a in reversed(parents):
            try:
                self._tree.item(a, open=True)
            except Exception:
                pass

    def _navigate_to_iid(self, iid):
        """Jump to the line stored in item values (works for class/def/call rows)."""
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
            pass
            

# end of file
