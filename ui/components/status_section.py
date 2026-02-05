import customtkinter as ctk
from .result_row import ResultRow

BATCH_SIZE = 50

class StatusSection(ctk.CTkFrame):
    def __init__(self, parent, title, color, items):
        super().__init__(parent, fg_color="transparent")
        
        self.items = items
        self.loaded_count = 0
        self.title = title
        self.color = color
        self.is_expanded = False

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self.header_frame.pack(fill="x", pady=(10, 0))
        
        self.indicator = ctk.CTkFrame(self.header_frame, width=5, height=25, fg_color=self.color)
        self.indicator.pack(side="left", padx=(0, 10))

        self.btn_toggle = ctk.CTkButton(
            self.header_frame,
            text=f"{self.title} ({len(self.items)}) ►",
            font=("Roboto Medium", 14),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            anchor="w",
            hover=False,
            command=self.toggle
        )
        self.btn_toggle.pack(side="left", fill="x", expand=True)

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")

    def toggle(self):
        self.is_expanded = not self.is_expanded
        
        if self.is_expanded:
            self.content_frame.pack(fill="x", padx=(15, 0), pady=5)
            self.btn_toggle.configure(text=f"{self.title} ({len(self.items)}) ▼")
            
            if self.loaded_count == 0:
                self.load_batch()
        else:
            self.content_frame.pack_forget()
            self.btn_toggle.configure(text=f"{self.title} ({len(self.items)}) ►")
            
            for widget in self.content_frame.winfo_children():
                widget.destroy()
            
            self.loaded_count = 0

    def load_batch(self):
        start = self.loaded_count
        end = min(start + BATCH_SIZE, len(self.items))
        
        children = self.content_frame.winfo_children()
        if children and isinstance(children[-1], ctk.CTkButton):
            children[-1].destroy()

        for i in range(start, end):
            row = ResultRow(self.content_frame, self.items[i], self.color)
            row.pack(fill="x", pady=2)
        
        self.loaded_count = end

        if self.loaded_count < len(self.items):
            remaining = len(self.items) - self.loaded_count
            self.btn_load_more = ctk.CTkButton(
                self.content_frame,
                text=f"Load {min(BATCH_SIZE, remaining)} more... ({remaining} remaining)",
                fg_color="transparent",
                border_width=1,
                border_color=("gray70", "gray30"),
                text_color="gray60",
                command=self.load_batch
            )
            self.btn_load_more.pack(fill="x", pady=10)
