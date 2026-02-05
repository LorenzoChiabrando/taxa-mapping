import customtkinter as ctk
from .result_row import ResultRow

BATCH_SIZE = 50
SEARCH_DELAY_MS = 300

class CategoryList(ctk.CTkFrame):
    def __init__(self, parent, items, accent_color):
        super().__init__(parent, fg_color="transparent")
        
        self.all_items = items
        self.filtered_items = items
        self.loaded_count = 0
        self.accent_color = accent_color
        self.search_timer = None
  
        self.last_query = None 

        self.active_rows = [] 
        self.row_pool = []

        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True)

        self.btn_load_more = None
        self.lbl_no_results = None

        self._bind_mouse_scroll(self.scroll_frame)
        
        self._perform_filter("") 

    def _bind_mouse_scroll(self, widget):
        def _on_mousewheel(event):
            try:
                if event.num == 4:
                    self.scroll_frame._parent_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.scroll_frame._parent_canvas.yview_scroll(1, "units")
                else:
                    self.scroll_frame._parent_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except Exception:
                pass
        
        safe_binds = ["<Button-4>", "<Button-5>", "<MouseWheel>"]
        for seq in safe_binds:
            try: widget.bind(seq, _on_mousewheel, add="+")
            except: pass

        for child in widget.winfo_children():
            self._bind_mouse_scroll(child)

    def filter(self, query):
        """Filtro con ritardo (per digitazione utente)"""
        if self.search_timer is not None:
            self.after_cancel(self.search_timer)
        self.search_timer = self.after(SEARCH_DELAY_MS, lambda: self._perform_filter(query))

    def filter_immediate(self, query):
        """Filtro istantaneo (per cambio tab o reset)"""
        if self.search_timer is not None:
            self.after_cancel(self.search_timer)
            self.search_timer = None
        self._perform_filter(query)

    def _perform_filter(self, query):
        try:
            if not self.winfo_exists(): return
        except: return

        query = query.lower().strip()

        if query == self.last_query:
            return
        
        self.last_query = query

        for row in self.active_rows:
            row.pack_forget()
            self.row_pool.append(row)
        self.active_rows.clear()
        
        if self.btn_load_more:
            self.btn_load_more.destroy()
            self.btn_load_more = None
        if self.lbl_no_results:
            self.lbl_no_results.destroy()
            self.lbl_no_results = None

        self.loaded_count = 0
        if not query:
            self.filtered_items = self.all_items
        else:
            self.filtered_items = []
            for i in self.all_items:
                q_name = i.get("query_name", "").lower()
                m_id = str(i.get("mapped_id", "")).lower()
                if query in q_name or query in m_id:
                    self.filtered_items.append(i)

        self.load_batch()

    def load_batch(self):
        start = self.loaded_count
        end = min(start + BATCH_SIZE, len(self.filtered_items))
        
        if self.btn_load_more:
            self.btn_load_more.destroy()
            self.btn_load_more = None

        if not self.filtered_items and start == 0:
            self.lbl_no_results = ctk.CTkLabel(self.scroll_frame, text="No bacteria found.", text_color="gray50")
            self.lbl_no_results.pack(pady=20)
            self._bind_mouse_scroll(self.lbl_no_results)
            return

        for i in range(start, end):
            item_data = self.filtered_items[i]
            
            if self.row_pool:
                row = self.row_pool.pop() 
                row.update_data(item_data, self.accent_color)
                row.pack(fill="x", pady=2)
            else:
                row = ResultRow(self.scroll_frame, item_data, self.accent_color)
                row.pack(fill="x", pady=2)
                self._bind_mouse_scroll(row)
            
            self.active_rows.append(row)
        
        self.loaded_count = end

        if self.loaded_count < len(self.filtered_items):
            remaining = len(self.filtered_items) - self.loaded_count
            self.btn_load_more = ctk.CTkButton(
                self.scroll_frame,
                text=f"Load {min(BATCH_SIZE, remaining)} more... ({remaining} remaining)",
                fg_color="transparent",
                border_width=1,
                border_color=("gray70", "gray30"),
                text_color="gray60",
                command=self.load_batch
            )
            self.btn_load_more.pack(fill="x", pady=10)
            self._bind_mouse_scroll(self.btn_load_more)
