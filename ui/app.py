import customtkinter as ctk
from pathlib import Path
import sys

try:
    from PIL import Image
except ImportError:
    Image = None

sys.path.append(str(Path(__file__).parent))

from views.run_view import RunView
from views.results_view import ResultsView

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

UI_DIR = Path(__file__).resolve().parent
ASSETS_DIR = UI_DIR / "assets"

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MINeBUGS - Advanced Taxonomy Mapper")
        self.geometry("1200x800") 

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_image = None
        logo_path = ASSETS_DIR / "logo.png"
        
        if Image and logo_path.exists():
            try:
                pil_image = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(48, 48))
            except Exception as e:
                print(f"Warning: Could not load logo image: {e}")
        elif not Image:
            print("Warning: Pillow library not installed. Logo disabled.")

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="  MINeBUGS", image=self.logo_image,
            compound="left", font=ctk.CTkFont(size=28, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=30, pady=(50, 5), sticky="w")

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar_frame, text="Advanced Taxonomy Mapper", text_color="gray70", font=ctk.CTkFont(size=14)
        )
        self.subtitle_label.grid(row=1, column=0, padx=30, pady=(0, 40), sticky="w")

        self.btn_run = ctk.CTkButton(
            self.sidebar_frame, text="Run Analysis", command=self.show_run_view,
            height=50, font=ctk.CTkFont(size=16, weight="bold"), anchor="w" 
        )
        self.btn_run.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.btn_results = ctk.CTkButton(
            self.sidebar_frame, text="Results Viewer", command=self.show_results_view,
            height=50, font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
        )
        self.btn_results.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        self.label_ver = ctk.CTkLabel(self.sidebar_frame, text="v2.0 Local Release", text_color="gray50")
        self.label_ver.grid(row=6, column=0, padx=20, pady=20)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        self.views = {}
        for V in (RunView, ResultsView):
            view_name = V.__name__
            view = V(parent=self.container, controller=self)
            self.views[view_name] = view
            view.grid(row=0, column=0, sticky="nsew")

        self.show_run_view()

    def show_view(self, name):
        view = self.views.get(name)
        if view: view.tkraise()
        return view

    def show_run_view(self):
        self.show_view("RunView")
        self.btn_run.configure(fg_color=("gray75", "gray25")) 
        self.btn_results.configure(fg_color="transparent")

    def show_results_view(self):
        view = self.show_view("ResultsView")
        if view:
            view.refresh()
            
        self.btn_results.configure(fg_color=("gray75", "gray25"))
        self.btn_run.configure(fg_color="transparent")

if __name__ == "__main__":
    app = App()
    app.mainloop()
