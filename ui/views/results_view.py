import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
import sys
import shutil
import json
import os
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from ui.components.category_list import CategoryList
from ui.utils.data_loader import ReportLoader
from ui.utils.plotter import SankeyGenerator

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None

ASSETS_DIR = PROJECT_ROOT / "ui" / "assets"

CATEGORY_CONFIG = {
    "unambiguous":       {"label": "GREEN",    "color": "#2CC985", "hover": "#229C68"},
    "high_similarity":   {"label": "Y-GREEN", "color": "#2C95C9", "hover": "#22779F"},
    "near_tier":         {"label": "YELLOW",  "color": "#F9A825", "hover": "#C7861E"},
    "low_similarity":    {"label": "RED",      "color": "#D03B3B", "hover": "#A62F2F"},
    "no_correspondence": {"label": "BLACK",    "color": "gray30",  "hover": "gray20"},
}

class ResultsView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.controller = controller
        self.output_dir = PROJECT_ROOT / "output"
        self.current_run_path = None
        
        self.loaded_groups = {} 
        self.current_category = "unambiguous"
        self.raw_results_data = []
        self.current_html_path = None

        self.category_views = {} 
        self.active_list = None
        self.ignore_search_trace = False 

        self.original_plot_image = None 
        self.resize_timer = None
        self.plot_label = None

        self.folder_icon = None
        if Image:
            try:
                icon_path = ASSETS_DIR / "folder.png"
                if icon_path.exists():
                    pil = Image.open(icon_path)
                    self.folder_icon = ctk.CTkImage(light_image=pil, dark_image=pil, size=(24, 24))
            except Exception: pass

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.view_list = ctk.CTkFrame(self, fg_color="transparent")
        self.view_list.grid_rowconfigure(1, weight=1)
        self.view_list.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.view_list, text="Available Simulations", font=("Roboto Medium", 24)).grid(row=0, padx=30, pady=20, sticky="w")
        self.scroll_runs = ctk.CTkScrollableFrame(self.view_list, fg_color=("gray90", "gray13"))
        self.scroll_runs.grid(row=1, sticky="nsew", padx=30, pady=(0, 30))

        self.view_detail = ctk.CTkFrame(self, fg_color="transparent")
        self.view_detail.grid_rowconfigure(1, weight=1)
        self.view_detail.grid_columnconfigure(0, weight=1)

        self.toolbar = ctk.CTkFrame(self.view_detail, height=60, fg_color=("gray85", "gray20"), corner_radius=0)
        self.toolbar.grid(row=0, sticky="ew")
        self.toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(self.toolbar, text="← Back", width=80, fg_color="transparent", text_color=("gray10", "gray90"), border_width=1, command=self.show_list_view).grid(row=0, column=0, padx=20, pady=10)
        self.lbl_run_name = ctk.CTkLabel(self.toolbar, text="Run Name", font=("Roboto Medium", 18))
        self.lbl_run_name.grid(row=0, column=1, padx=20, sticky="w")
        ctk.CTkButton(self.toolbar, text="Rename", width=100, fg_color="#3B8ED0", command=self.action_rename).grid(row=0, column=2, padx=(0,10))
        ctk.CTkButton(self.toolbar, text="Delete", width=100, fg_color="#D03B3B", hover_color="#9F3636", command=self.action_delete).grid(row=0, column=3, padx=20)

        self.tab_view = ctk.CTkTabview(self.view_detail)
        self.tab_view.grid(row=1, sticky="nsew", padx=20, pady=10)
        
        self.tab_overall = self.tab_view.add("Overall Results")
        self.tab_plots = self.tab_view.add("Plots")

        self.tab_overall.grid_rowconfigure(2, weight=1)
        self.tab_overall.grid_columnconfigure(0, weight=1)

        self.cat_btn_frame = ctk.CTkFrame(self.tab_overall, fg_color="transparent")
        self.cat_btn_frame.grid(row=0, column=0, sticky="ew", pady=(10, 5))
        self.category_buttons = {}

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", self._on_search_change)
        
        self.search_entry = ctk.CTkEntry(
            self.tab_overall, textvariable=self.search_var, 
            placeholder_text="Search bacterium in current category...", height=35
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.overall_content = ctk.CTkFrame(self.tab_overall, fg_color="transparent")
        self.overall_content.grid(row=2, column=0, sticky="nsew")
        
        self.tab_plots.grid_rowconfigure(0, weight=1)
        self.tab_plots.grid_columnconfigure(0, weight=1)
        
        self.plots_frame = ctk.CTkFrame(self.tab_plots, fg_color="transparent")
        self.plots_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.plots_frame.bind("<Configure>", self._on_plot_frame_resize)

        self.show_list_view()

    def refresh(self):
        if not self.current_run_path: self.reload_runs()

    def show_list_view(self):
        self._clear_category_cache()
        self.view_detail.grid_forget()
        self.view_list.grid(row=0, column=0, sticky="nsew")
        self.current_run_path = None
        self.reload_runs()

    def show_detail_view(self, run_path):
        self.view_list.grid_forget()
        self.view_detail.grid(row=0, column=0, sticky="nsew")
        self.current_run_path = run_path
        self.lbl_run_name.configure(text=run_path.name)
        self.tab_view.set("Overall Results")
        self.load_run_data()
        self.load_plot_preview()

    def _clear_category_cache(self):
        for view in self.category_views.values():
            view.destroy()
        self.category_views.clear()
        self.active_list = None
        self.original_plot_image = None
        if self.plot_label:
            self.plot_label.destroy()
            self.plot_label = None

    def reload_runs(self):
        for w in self.scroll_runs.winfo_children(): w.destroy()
        if not self.output_dir.exists(): self.output_dir.mkdir(parents=True)
        runs = sorted([p for p in self.output_dir.iterdir() if p.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not runs:
            ctk.CTkLabel(self.scroll_runs, text="No simulations found.", text_color="gray50").pack(pady=40)
            return
        for run in runs:
            ctk.CTkButton(
                self.scroll_runs, text=f"  {run.name}", image=self.folder_icon, 
                compound="left", font=("Roboto", 16), height=60, fg_color="transparent", 
                border_width=1, border_color=("gray70", "gray30"), text_color=("gray10", "gray90"), anchor="w",
                command=lambda r=run: self.show_detail_view(r)
            ).pack(fill="x", pady=5, padx=5)

    def load_run_data(self):
        for w in self.cat_btn_frame.winfo_children(): w.destroy()
        self._clear_category_cache()
        self.category_buttons = {}
        
        self.ignore_search_trace = True
        self.search_var.set("") 
        self.ignore_search_trace = False

        self.raw_results_data = [] 

        json_path = self.current_run_path / "results" / "mapping_report.json"
        
        for w in self.overall_content.winfo_children(): w.destroy()
        self.lbl_loading = ctk.CTkLabel(self.overall_content, text="Loading data...", text_color="gray50")
        self.lbl_loading.pack(pady=50)

        loader = ReportLoader(json_path, 
                              lambda g, t: self.after(0, self._on_json_loaded, g), 
                              lambda m: self.after(0, self._on_json_error, m))
        loader.start()

    def _on_json_loaded(self, groups):
        if self.lbl_loading: self.lbl_loading.destroy()
        self.loaded_groups = groups
        
        self.raw_results_data = []
        for k, items in groups.items():
            self.raw_results_data.extend(items)

        col_idx = 0
        order = ["unambiguous", "high_similarity", "near_tier", "low_similarity", "no_correspondence"]
        
        for key in order:
            items = groups.get(key, [])
            count = len(items)
            conf = CATEGORY_CONFIG[key]
            
            btn = ctk.CTkButton(
                self.cat_btn_frame,
                text=f"{conf['label']}\n{count}",
                font=("Roboto", 12, "bold"),
                fg_color="transparent",
                border_width=2,
                border_color=conf["color"],
                text_color=("gray10", "gray90"),
                hover_color=conf.get("hover", "gray50"),
                height=50,
                command=lambda k=key: self._switch_category(k)
            )
            btn.grid(row=0, column=col_idx, sticky="ew", padx=2)
            self.cat_btn_frame.grid_columnconfigure(col_idx, weight=1)
            self.category_buttons[key] = btn
            col_idx += 1

        found_start = False
        for key in order:
            if len(groups.get(key, [])) > 0:
                self._switch_category(key)
                found_start = True
                return
        
        if not found_start:
            self._switch_category("unambiguous")

    def _on_json_error(self, msg):
        if self.lbl_loading:
            self.lbl_loading.configure(text=f"Error: {msg}", text_color="red")

    def _switch_category(self, category_key):
        self.current_category = category_key

        for key, btn in self.category_buttons.items():
            conf = CATEGORY_CONFIG[key]
            if key == category_key:
                btn.configure(fg_color=conf["color"], text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=("gray10", "gray90"))

        self.ignore_search_trace = True
        self.search_var.set("") 
        self.ignore_search_trace = False

        if self.active_list:
            self.active_list.pack_forget()

        if category_key in self.category_views:
            view = self.category_views[category_key]
            view.filter_immediate("") 
        else:
            items = self.loaded_groups.get(category_key, [])
            color = CATEGORY_CONFIG[category_key]["color"]
            view = CategoryList(self.overall_content, items, color)
            self.category_views[category_key] = view

        view.pack(fill="both", expand=True)
        self.active_list = view

    def _on_search_change(self, *args):
        if self.ignore_search_trace:
            return
        if self.active_list:
            self.active_list.filter(self.search_var.get())

    def load_plot_preview(self):
        for widget in self.plots_frame.winfo_children(): widget.destroy()
        self.original_plot_image = None
        self.plot_label = None
        
        if not self.current_run_path: return

        png_path = self.current_run_path / "flow_analysis.png"
        html_path = self.current_run_path / "flow_analysis.html"
        self.current_html_path = html_path

        if png_path.exists() and Image:
            try:
                self.original_plot_image = Image.open(png_path)
                
                btn_frame = ctk.CTkFrame(self.plots_frame, fg_color="transparent")
                btn_frame.pack(side="bottom", pady=10) 
                
                ctk.CTkButton(btn_frame, text="Open Interactive (HTML)", font=("Roboto Medium", 14), 
                             height=40, fg_color="#3B8ED0", command=self.open_html_plot).pack(side="left", padx=10)
                ctk.CTkButton(btn_frame, text="Regenerate", fg_color="transparent", border_width=1, 
                             text_color=("gray10", "gray90"), command=self.generate_sankey_plot).pack(side="left", padx=10)

                self.plot_label = ctk.CTkLabel(self.plots_frame, text="")
                self.plot_label.pack(side="top", fill="both", expand=True, padx=0, pady=0) 
                
                self.after(50, lambda: self._update_responsive_image(self.plots_frame.winfo_width(), self.plots_frame.winfo_height()))

            except Exception as e:
                ctk.CTkLabel(self.plots_frame, text=f"Error loading preview: {e}", text_color="red").pack()
        else:
            self._show_generate_button()

    def _on_plot_frame_resize(self, event):
        """Chiamato quando il frame dei plot cambia dimensione (es. resize finestra)."""
        if not self.original_plot_image or not self.plot_label:
            return

        if self.resize_timer:
            self.after_cancel(self.resize_timer)
        
        self.resize_timer = self.after(100, lambda: self._update_responsive_image(event.width, event.height))

    def _update_responsive_image(self, container_w, container_h):
        """Calcola le nuove dimensioni e aggiorna l'immagine."""
        if not self.original_plot_image: return

        target_w = max(1, container_w)
        target_h = max(1, container_h - 60) 

        orig_w, orig_h = self.original_plot_image.size
        
        ratio = min(target_w / orig_w, target_h / orig_h)
        
        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)
        
        try:
            ctk_img = ctk.CTkImage(
                light_image=self.original_plot_image, 
                dark_image=self.original_plot_image, 
                size=(new_w, new_h)
            )
            self.plot_label.configure(image=ctk_img)
        except Exception:
            pass

    def _show_generate_button(self):
        ctk.CTkLabel(self.plots_frame, text="No visualization generated yet.", font=("Roboto", 16), text_color="gray60").pack(pady=(100, 20))
        ctk.CTkButton(self.plots_frame, text="Generate Sankey Diagram", font=("Roboto Medium", 16), height=50, fg_color="#5A5A5A", command=self.generate_sankey_plot).pack(pady=10)

    def generate_sankey_plot(self):
        try:
            stats_path = self.current_run_path / "debug" / "02_filtering_stats.json"
            html_out, png_out = SankeyGenerator.generate(
                json_results=self.raw_results_data,
                filtering_stats_path=stats_path,  
                run_name=self.lbl_run_name.cget("text"),
                output_folder=self.current_run_path
            )
            if html_out is None:
                messagebox.showerror("Error", "Could not generate plot. Check input files.")
                return
            self.load_plot_preview()
            if png_out is None:
                messagebox.showwarning("Warning", "Plot generated (HTML) but preview failed.\nInstall 'kaleido' via pip.")
                self.open_html_plot() 
        except Exception as e:
            messagebox.showerror("Plot Error", f"Failed to generate plot:\n{e}")

    def open_html_plot(self):
        if self.current_html_path and self.current_html_path.exists():
            webbrowser.open(f"file://{self.current_html_path.resolve()}")
        else:
            messagebox.showerror("Error", "HTML file not found.")

    # --- ACTIONS ---
    def action_rename(self):
        if not self.current_run_path: return
        dialog = ctk.CTkInputDialog(text="Enter new name:", title="Rename")
        new = dialog.get_input()
        if new:
            new = "".join(c for c in new if c.isalnum() or c in (' ', '_', '-')).strip()
            if new:
                try:
                    dest = self.current_run_path.parent / new
                    self.current_run_path.rename(dest)
                    self.current_run_path = dest
                    self.lbl_run_name.configure(text=new)
                except Exception as e: print(e)

    def action_delete(self):
        if not self.current_run_path: return
        if messagebox.askyesno("Confirm", "Delete simulation? Cannot be undone."):
            try:
                shutil.rmtree(self.current_run_path)
                self.show_list_view()
            except Exception as e: messagebox.showerror("Error", str(e))
