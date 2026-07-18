"""Compact Tk desktop monitor for optimization experiments."""
from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from .config import OptimizationConfig
from .engine import EngineState, OptimizationEngine


class OptimizationApp(tk.Tk):
    def __init__(self, config: OptimizationConfig):
        super().__init__()
        self.config = config
        self.engine = OptimizationEngine(config)
        self.title(f"BOFM Optimization - {config.name}")
        self.geometry("1220x760")
        self.minsize(980, 620)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_style()
        self._build_ui()
        self.after(250, self._refresh)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Treeview", rowheight=25, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text=self.config.name, style="Title.TLabel").pack(side="left")
        ttk.Button(toolbar, text="Start / Resume", command=self.engine.start).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Pause", command=self.engine.pause).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Stop", command=self._stop).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Open run", command=self._open_selected).pack(side="right", padx=(6, 12))

        metrics = ttk.Frame(self, padding=(12, 0, 12, 10))
        metrics.pack(fill="x")
        self.state_var = tk.StringVar(value="IDLE")
        self.progress_var = tk.StringVar(value="0 / 0")
        self.best_var = tk.StringVar(value="--")
        self.current_var = tk.StringVar(value="--")
        for label, variable in (
            ("State", self.state_var),
            ("HF-equivalent cost", self.progress_var),
            ("Best target-fidelity eta", self.best_var),
            ("Current trial", self.current_var),
        ):
            block = ttk.Frame(metrics)
            block.pack(side="left", fill="x", expand=True)
            ttk.Label(block, text=label).pack(anchor="w")
            ttk.Label(block, textvariable=variable, style="Metric.TLabel").pack(anchor="w")

        self.progress = ttk.Progressbar(self, maximum=self.config.budget, mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=(0, 10))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12)
        plot_frame = ttk.Frame(body)
        data_frame = ttk.Frame(body)
        body.add(plot_frame, weight=2)
        body.add(data_frame, weight=3)

        self.figure = Figure(figsize=(5.0, 4.0), dpi=100, layout="constrained")
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        columns = ("id", "status", "fidelity", "objective", "cost", "source")
        self.table = ttk.Treeview(data_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID", "status": "Status", "fidelity": "Fidelity",
            "objective": "eta", "cost": "Cost", "source": "Source",
        }
        widths = {"id": 50, "status": 90, "fidelity": 65, "objective": 90, "cost": 60, "source": 155}
        for column in columns:
            self.table.heading(column, text=headings[column])
            self.table.column(column, width=widths[column], anchor="center" if column != "source" else "w")
        scrollbar = ttk.Scrollbar(data_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<<TreeviewSelect>>", self._show_selected)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=False, padx=12, pady=(10, 12))
        event_frame = ttk.Frame(notebook)
        detail_frame = ttk.Frame(notebook)
        notebook.add(event_frame, text="Events")
        notebook.add(detail_frame, text="Selected trial")
        self.events_text = tk.Text(event_frame, height=7, wrap="none", font=("Consolas", 9), state="disabled")
        self.events_text.pack(fill="both", expand=True)
        self.detail_text = tk.Text(detail_frame, height=7, wrap="none", font=("Consolas", 9), state="disabled")
        self.detail_text.pack(fill="both", expand=True)

    def _refresh(self) -> None:
        snapshot = self.engine.snapshot()
        self.state_var.set(snapshot["state"].upper())
        self.progress_var.set(f'{snapshot["cost_used"]:.2f} / {snapshot["budget"]:.2f}')
        self.progress["value"] = snapshot["cost_used"]
        best = snapshot["best"]
        self.best_var.set("--" if best is None else f'{best["objective"]:.6f}  (#{best["id"]})')
        current = snapshot["current_trial_id"]
        self.current_var.set("--" if current is None else f"#{current}")
        selected = self.table.selection()
        selected_id = selected[0] if selected else None
        current_ids = set(self.table.get_children())
        desired_ids = {str(item["id"]) for item in snapshot["trials"]}
        for stale in current_ids - desired_ids:
            self.table.delete(stale)
        for trial in snapshot["trials"]:
            iid = str(trial["id"])
            objective = "--" if trial["objective"] is None else f'{trial["objective"]:.6f}'
            values = (
                trial["id"], trial["status"], trial["fidelity"], objective,
                f'{trial["relative_cost"]:.2f}', trial["source"],
            )
            if iid in current_ids:
                self.table.item(iid, values=values)
            else:
                self.table.insert("", "end", iid=iid, values=values)
        if selected_id in desired_ids:
            self.table.selection_set(selected_id)
        self._update_plot(snapshot["trials"])
        event_lines = [
            f'{event["created_at"][-14:]}  {event["level"].upper():7}  {event["message"]}'
            for event in snapshot["events"][-80:]
        ]
        self._set_text(self.events_text, "\n".join(event_lines))
        self.after(750, self._refresh)

    def _update_plot(self, trials: list[dict]) -> None:
        completed = [item for item in trials if item["status"] == "completed"]
        self.axis.clear()
        self.axis.set_title("Best target-fidelity objective vs equivalent HF cost", fontsize=10)
        self.axis.set_xlabel("Equivalent high-fidelity cost")
        self.axis.set_ylabel(self.config.objective_label)
        self.axis.grid(True, color="#d9d9d9", linewidth=0.7)
        cost = 0.0
        best = None
        xs, ys = [], []
        target_name = self.config.fidelities[-1].name
        for trial in completed:
            cost += float(trial["relative_cost"])
            feasible = all(
                float(trial["constraints"].get(spec.name, float("inf"))) <= spec.upper
                for spec in self.config.constraints
            )
            if feasible and trial["fidelity"] == target_name:
                value = float(trial["objective"])
                best = value if best is None else (max(best, value) if self.config.maximize else min(best, value))
            if best is not None:
                xs.append(cost)
                ys.append(best)
        if xs:
            self.axis.step(xs, ys, where="post", color="#1769aa", linewidth=2.0)
            self.axis.scatter(xs[-1:], ys[-1:], color="#c43d3d", s=28, zorder=3)
        self.canvas.draw_idle()

    def _selected_trial(self) -> dict | None:
        selected = self.table.selection()
        if not selected:
            return None
        trial_id = int(selected[0])
        return next((item for item in self.engine.store.trials() if item["id"] == trial_id), None)

    def _show_selected(self, _event=None) -> None:
        trial = self._selected_trial()
        self._set_text(self.detail_text, "" if trial is None else json.dumps(trial, indent=2, ensure_ascii=False))

    def _open_selected(self) -> None:
        trial = self._selected_trial()
        if not trial or not trial.get("run_dir"):
            return
        path = Path(trial["run_dir"])
        if path.exists():
            os.startfile(path)

    def _stop(self) -> None:
        if messagebox.askyesno("Stop scheduling", "Stop after the current external trial finishes?"):
            self.engine.stop()

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")
        widget.see("end")

    def _close(self) -> None:
        if self.engine.current_trial_id is not None:
            self.engine.pause()
            messagebox.showwarning(
                "Trial still running",
                "Pause has been requested. Keep this window open until the current "
                "external trial finishes, then close it safely.",
            )
            return
        if self.engine.state == EngineState.RUNNING:
            self.engine.pause()
        self.destroy()
