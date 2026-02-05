import customtkinter as ctk

class ResultRow(ctk.CTkFrame):
    """
    Represents a single bacterium mapping row.
    Now supports data updates (recycling) to avoid lag.
    """
    def __init__(self, parent, item_data, accent_color):
        super().__init__(parent, fg_color="transparent")
        
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=6, border_width=1, border_color=("gray70", "gray30"))
        self.header_frame.pack(fill="x", pady=2)
        
        self.header_frame.bind("<Button-1>", self.toggle)
        
        self.lbl_query = ctk.CTkLabel(
            self.header_frame, 
            text="", 
            font=("Roboto Medium", 15), 
            text_color=("gray10", "gray90")
        )
        self.lbl_query.pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_query.bind("<Button-1>", self.toggle)

        self.lbl_match = ctk.CTkLabel(
            self.header_frame, 
            text="", 
            font=("Roboto", 12)
        )
        self.lbl_match.pack(anchor="w", padx=15, pady=(0, 8))
        self.lbl_match.bind("<Button-1>", self.toggle)

        self.frame_detail = None
        
        self.update_data(item_data, accent_color)

    def update_data(self, item_data, accent_color):
        self.item_data = item_data
        self.accent_color = accent_color
        self.is_expanded = False
        
        if self.frame_detail:
            self.frame_detail.destroy()
            self.frame_detail = None
        self.header_frame.configure(fg_color="transparent")

        query = item_data.get("query_name", "Unknown")
        mapped_id = item_data.get("mapped_id")
        self.candidates_data = item_data.get("candidates", [])
        self.winner_id = mapped_id

        self.lbl_query.configure(text=query)
        
        match_text = f"Match: {mapped_id}" if mapped_id else "No Match found"
        match_color = accent_color if mapped_id else "gray60"
        self.lbl_match.configure(text=match_text, text_color=match_color)

    def toggle(self, event=None):
        if self.is_expanded:
            if self.frame_detail:
                self.frame_detail.destroy()
                self.frame_detail = None
            self.header_frame.configure(fg_color="transparent")
        else:
            self.header_frame.configure(fg_color=("gray90", "gray25"))
            self._build_details()
            
        self.is_expanded = not self.is_expanded

    def _build_details(self):
        self.frame_detail = ctk.CTkFrame(self, fg_color=("gray95", "gray20"), corner_radius=0)
        self.frame_detail.pack(fill="x", padx=10, pady=(0, 5))

        others = [c for c in self.candidates_data if c.get("model_id") != self.winner_id]

        if not others:
            lbl = ctk.CTkLabel(self.frame_detail, text="No other candidates.", text_color="gray50", font=("Roboto", 11, "italic"))
            lbl.pack(anchor="w", padx=20, pady=5)
        else:
            ctk.CTkLabel(self.frame_detail, text="Other Candidates:", font=("Roboto", 11, "bold")).pack(anchor="w", padx=20, pady=(5,0))
            for cand in others:
                mod_id = cand.get("model_id", "Unknown")
                score = cand.get("score", 0.0)
                c_lbl = ctk.CTkLabel(
                    self.frame_detail, 
                    text=f"• {mod_id}  (Score: {score:.2f})", 
                    font=("Consolas", 11),
                    text_color="gray70"
                )
                c_lbl.pack(anchor="w", padx=30)
            ctk.CTkFrame(self.frame_detail, height=5, fg_color="transparent").pack()
