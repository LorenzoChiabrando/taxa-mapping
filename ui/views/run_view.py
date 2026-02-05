import customtkinter as ctk
from tkinter import filedialog  
import threading
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

try:
    from main import run_local_pipeline
except ImportError:
    run_local_pipeline = None

class GuiLogHandler(logging.Handler):
    """Redirects logging output to the GUI TextBox in a thread-safe manner."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.after(0, self._append_msg, msg)

    def _append_msg(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

class RunView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, corner_radius=10, fg_color=("gray95", "gray15"))
        self.controller = controller
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.default_out_dir = PROJECT_ROOT / "output"
        self.default_out_dir.mkdir(parents=True, exist_ok=True)
        
        self.default_in_dir = PROJECT_ROOT / "input"
        self.default_in_dir.mkdir(parents=True, exist_ok=True)

        self.label_title = ctk.CTkLabel(self, text="Configuration & Execution", font=("Roboto Medium", 20))
        self.label_title.grid(row=0, column=0, columnspan=3, pady=(20, 15), padx=20, sticky="w")

        self.input_path = ctk.StringVar()
        
        lbl_in = ctk.CTkLabel(self, text="Input File:", font=("Roboto", 13))
        lbl_in.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="e")
        
        self.entry_file = ctk.CTkEntry(self, textvariable=self.input_path, placeholder_text="Select CSV file...")
        self.entry_file.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        
        self.btn_file = ctk.CTkButton(self, text="Browse...", command=self.browse_input, width=100)
        self.btn_file.grid(row=1, column=2, padx=(10, 20), pady=10)

        self.output_path = ctk.StringVar(value=str(self.default_out_dir))
        
        lbl_out = ctk.CTkLabel(self, text="Output Dir:", font=("Roboto", 13))
        lbl_out.grid(row=2, column=0, padx=(20, 10), pady=10, sticky="e")
        
        self.entry_out = ctk.CTkEntry(self, textvariable=self.output_path)
        self.entry_out.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        
        self.btn_out = ctk.CTkButton(self, text="Browse...", command=self.browse_output, width=100, 
                                     fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        self.btn_out.grid(row=2, column=2, padx=(10, 20), pady=10)

        lbl_log = ctk.CTkLabel(self, text="Execution Log:", font=("Roboto", 12, "bold"))
        lbl_log.grid(row=3, column=0, columnspan=3, padx=20, pady=(20, 0), sticky="nw")

        self.console = ctk.CTkTextbox(self, font=("Consolas", 12), fg_color=("white", "black"))
        self.console.grid(row=3, column=0, columnspan=3, padx=20, pady=(25, 10), sticky="nsew")
        self.console.insert("0.0", "--- Ready to start ---\n")
        self.console.configure(state="disabled")

        self.btn_run = ctk.CTkButton(self, text="START PIPELINE", command=self.start_pipeline, height=45, 
                                     font=("Roboto Medium", 14), fg_color="#2CC985", hover_color="#229C68", text_color="white")
        self.btn_run.grid(row=4, column=0, columnspan=3, padx=20, pady=(10, 20), sticky="ew")

        self.post_run_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.post_run_frame.grid_columnconfigure(0, weight=1)
        self.post_run_frame.grid_columnconfigure(1, weight=1)

        self.btn_new_run = ctk.CTkButton(
            self.post_run_frame, 
            text="New Run", 
            command=self.reset_ui, 
            height=45,
            fg_color="gray50", hover_color="gray40"
        )
        self.btn_new_run.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.btn_view_results = ctk.CTkButton(
            self.post_run_frame, 
            text="View Results ->", 
            command=self.go_to_results, 
            height=45,
            fg_color="#3B8ED0", hover_color="#36719F"
        )
        self.btn_view_results.grid(row=0, column=1, padx=(10, 0), sticky="ew")

    def _set_input_state(self, state: str):
        """Enables or Disables input fields and browse buttons only."""
        self.btn_file.configure(state=state)
        self.btn_out.configure(state=state)
        self.entry_file.configure(state=state)
        self.entry_out.configure(state=state)

    def browse_input(self):
        filename = filedialog.askopenfilename(
            initialdir=str(self.default_in_dir),
            title="Select Input CSV",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if filename:
            self.input_path.set(filename)

    def browse_output(self):
        dirname = filedialog.askdirectory(
            initialdir=self.output_path.get(),
            title="Select Output Directory"
        )
        if dirname:
            self.output_path.set(dirname)

    def start_pipeline(self):
        inp = self.input_path.get()
        out = self.output_path.get()

        if not inp:
            self._log_to_console("ERROR: Please select an input file!")
            return

        self._set_input_state("disabled")
        self.btn_run.configure(state="disabled", text="Running...")
        
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        for h in logger.handlers:
            logger.removeHandler(h)
        logger.addHandler(GuiLogHandler(self.console))

        t = threading.Thread(target=self._run_thread, args=(inp, out))
        t.start()

    def _run_thread(self, inp, out):
        try:
            if run_local_pipeline:
                run_local_pipeline(inp, out)
            else:
                logging.error("CRITICAL ERROR: Could not import 'run_local_pipeline'.")
        except Exception as e:
            logging.exception(f"Pipeline Execution Failed: {e}")
        finally:
            self.after(0, self._on_pipeline_finished)

    def _on_pipeline_finished(self):
        """Called when processing is done. Swaps buttons."""
        self.btn_run.grid_forget()
        
        self.post_run_frame.grid(row=4, column=0, columnspan=3, padx=20, pady=(10, 20), sticky="ew")
        

    def reset_ui(self):
        """Resets the UI to the initial state."""
        self.input_path.set("")
        self.output_path.set(str(self.default_out_dir))

        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.insert("0.0", "--- Ready for new run ---\n")
        self.console.configure(state="disabled")

        self._set_input_state("normal")

        self.post_run_frame.grid_forget()
        self.btn_run.configure(state="normal", text="START PIPELINE")
        self.btn_run.grid(row=4, column=0, columnspan=3, padx=20, pady=(10, 20), sticky="ew")

    def go_to_results(self):
        """Resets the UI state silently and switches to the Results view."""
        self.reset_ui()
        self.controller.show_results_view()

    def _log_to_console(self, text):
        self.console.configure(state="normal")
        self.console.insert("end", text + "\n")
        self.console.configure(state="disabled")
