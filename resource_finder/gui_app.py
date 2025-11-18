"""
Minimal Tkinter GUI that wires together modules:
- Single Mapbox fetch per postcode (all contours)
- Local filter: minutes tab + BU + internal flag
- OSRM only when 'Calculate drive times' pressed
"""

# resource_finder/gui_app.py
import tkinter as tk
from tkinter import ttk, messagebox
from requests import HTTPError
import pandas as pd

from .api_config import geocode_postcode, fetch_isochrone, PostcodeNotFound
from .geo_config import (
    isochrone_to_gdf,
    teams_to_gdf,
    filter_teams_by_minutes,
    list_business_units,
    apply_team_filters,
)
from .routing_config import route_rank_teams

# --- Ground Control palette ---
PALETTE = {
    "GC Dark Green": "#294238",
    "GC Light Green": "#b2d235",
    "GC Mid Green":  "#50b748",
    "GC Orange":     "#f57821",
    "GC Light Grey": "#e6ebe3",
}

def _apply_styles(root: tk.Tk):
    root.configure(bg=PALETTE["GC Light Grey"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=PALETTE["GC Light Grey"])
    style.configure("TLabel", background=PALETTE["GC Light Grey"], foreground=PALETTE["GC Dark Green"])
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=PALETTE["GC Dark Green"])
    style.configure("TButton", padding=8, foreground="white", background=PALETTE["GC Mid Green"])
    style.map("TButton", background=[("active", PALETTE["GC Light Green"])])
    style.configure("Go.TButton", padding=12, font=("Segoe UI", 11, "bold"),
                    foreground="white", background=PALETTE["GC Orange"])
    style.map("Go.TButton", background=[("active", "#ff8f3b")])

class ResourceFinderApp:
    COLS = ("Contractor","BusinessUnit","Postcode","InternalContractor","drive_min","drive_km","co2_kg")
    HEADINGS = {
        "Contractor": "Team Name",
        "BusinessUnit": "Business Unit",
        "Postcode": "Postcode",
        "InternalContractor": "Type",
        "drive_min": "Drive (min)",
        "drive_km": "Distance (km)",
        "co2_kg": "CO₂ (kg)",
    }

    def __init__(self, root: tk.Tk, fieldteams: pd.DataFrame):
        self.root = root
        self.root.title("Field Team Resource Finder")
        _apply_styles(self.root)

        # data
        self.df = fieldteams
        self.teams_gdf = teams_to_gdf(self.df)

        # state (site & isochrone cache)
        self.current_pc = None
        self.site_lon = None
        self.site_lat = None
        self.iso_gdf = None
        self.filtered = pd.DataFrame()

        # tk vars
        self.pc_var = tk.StringVar(value="")
        self.bu_var = tk.StringVar(value="(Any)")
        self.internal_var = tk.StringVar(value="either")  # either / 1 / 0
        self.sla_var = tk.BooleanVar(value=False)         # coming soon
        self.minutes_var = tk.StringVar(value="60")       # 15/30/45/60

        self._build()

    # ---------------- UI ----------------
    def _build(self):
        top = ttk.Frame(self.root); top.pack(fill="x", padx=12, pady=8)

        ttk.Label(top, text="Field Team Resource Finder", style="Header.TLabel")\
            .grid(row=0, column=0, columnspan=5, sticky="w", pady=(0,6))

        # 1) Postcode
        ttk.Label(top, text="1) Postcode:").grid(row=1, column=0, sticky="w")
        pc_entry = ttk.Entry(top, textvariable=self.pc_var, width=18)
        pc_entry.grid(row=2, column=0, sticky="w", padx=(0,8))
        # Trigger geocode + isochrone on blur or Enter
        pc_entry.bind("<FocusOut>", self.on_postcode_changed)
        pc_entry.bind("<Return>", self.on_postcode_changed)

        # 2) Business Unit
        ttk.Label(top, text="2) Business Unit:").grid(row=1, column=1, sticky="w")
        self.bu_combo = ttk.Combobox(top, textvariable=self.bu_var, width=28, state="readonly")
        self.bu_combo["values"] = list_business_units(self.df) if "BusinessUnit" in self.df.columns else ["(Any)"]
        self.bu_combo.set("(Any)")
        self.bu_combo.grid(row=2, column=1, sticky="w", padx=(0,8))

        # Internal / Contractor radios
        ic = ttk.Frame(top); ic.grid(row=2, column=2, sticky="w")
        ttk.Radiobutton(ic, text="Either", value="either", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Direct", value="1", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Contractor", value="0", variable=self.internal_var).pack(side="left", padx=3)

        # SLA toggle (single line)
        ttk.Checkbutton(
            top,
            variable=self.sla_var,
            text="Include teams not meeting SLAs (coming soon)"
        ).grid(row=2, column=3, sticky="w")

        # Button row
        btns = ttk.Frame(self.root); btns.pack(fill="x", padx=12, pady=(0,6))
        ttk.Button(btns, text="3) Apply filters", command=self.on_apply_filters).pack(side="left")
        ttk.Button(btns, text="4) Calculate drive times", style="Go.TButton", command=self.on_calculate_routes)\
            .pack(side="right")

        # Table container with minutes bar on top
        table = ttk.Frame(self.root); table.pack(fill="both", expand=True, padx=12, pady=(0,12))
        # Minutes selection bar ABOVE the table
        minutes_bar = ttk.Frame(table)
        minutes_bar.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0,6))
        ttk.Label(minutes_bar, text="Travel time band:").pack(side="left", padx=(0,6))
        for m in ("15","30","45","60"):
            ttk.Radiobutton(minutes_bar, text=f"Within {m} Minutes", value=m, variable=self.minutes_var)\
                .pack(side="left", padx=4)

        # Treeview
        self.tree = ttk.Treeview(table, columns=self.COLS, show="headings", height=18)
        for c, w in zip(self.COLS, (180,160,100,110,90,110,90)):
            self.tree.heading(c, text=self.HEADINGS[c])
            self.tree.column(c, width=w, anchor="w")
        ysb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.grid(row=1, column=0, sticky="nsew"); ysb.grid(row=1, column=1, sticky="ns")
        table.grid_rowconfigure(1, weight=1); table.grid_columnconfigure(0, weight=1)

        # Status line
        self.status = tk.StringVar(value="Enter a postcode (1) and tab away to load isochrones, then Apply filters (3).")
        ttk.Label(self.root, textvariable=self.status).pack(fill="x", padx=12, pady=(0,6))

    # ---------------- Handlers ----------------
    def on_postcode_changed(self, event=None):
        pc = self.pc_var.get().strip().upper()
        if not pc or pc == self.current_pc:
            return  # nothing to do
        try:
            self.site_lon, self.site_lat = geocode_postcode(pc)
            iso_gj = fetch_isochrone(self.site_lon, self.site_lat)   # single call → all contours
            self.iso_gdf = isochrone_to_gdf(iso_gj)
            self.current_pc = pc

            # Initialise BU list based on default minutes (60)
            within60 = filter_teams_by_minutes(self.teams_gdf, self.iso_gdf, minutes=60)
            self.bu_combo["values"] = list_business_units(within60)
            if self.bu_var.get() not in self.bu_combo["values"]:
                self.bu_combo.set("(Any)")

            # Prepopulate the table (blank routing cols)
            self._populate(within60.assign(drive_min="", drive_km="", co2_kg=""))
            self.status.set(f"Loaded {pc}: {len(within60)} team(s) within 60 minutes. Adjust filters and Apply.")
        except PostcodeNotFound as e:
            messagebox.showerror("Invalid postcode", str(e))
        except HTTPError as e:
            messagebox.showerror("Service error", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load site: {e}")

    def on_apply_filters(self):
        if self.iso_gdf is None:
            messagebox.showinfo("Info", "Enter a postcode and tab away to load isochrones.")
            return

        minutes = int(self.minutes_var.get())
        within = filter_teams_by_minutes(self.teams_gdf, self.iso_gdf, minutes=minutes)

        internal_sel = self.internal_var.get()
        internal_flag = None if internal_sel == "either" else int(internal_sel)
        bu_choice = self.bu_var.get() or "(Any)"
        filtered = apply_team_filters(within, business_unit=bu_choice, internal_flag=internal_flag)

        self.filtered = filtered  # cache for routing step
        self._populate(filtered.assign(drive_min="", drive_km="", co2_kg=""))
        self.status.set(f"Applied filters: {len(filtered)} team(s) in {minutes} minutes.")

    def on_calculate_routes(self):
        if self.site_lon is None or self.filtered is None or self.filtered.empty:
            messagebox.showinfo("Info", "Apply filters first with at least one team.")
            return
        out = route_rank_teams(self.filtered, self.site_lon, self.site_lat, top_n=20)
        if out.empty:
            messagebox.showinfo("Info", "No routes calculated.")
            return
        self._populate(out)
        self.status.set(f"Calculated routes for {len(out)} team(s).")

    # ---------------- Helpers ----------------
    def _populate(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        disp = df.copy()
        if "InternalContractor" in disp.columns:
            disp["InternalContractor"] = disp["InternalContractor"].map({1:"Direct",0:"Contractor"}).fillna("")
        for _, row in disp.iterrows():
            self.tree.insert("", "end", values=tuple(row.get(c, "") for c in self.COLS))

def main(fieldteams=None):
    if fieldteams is None:
        fieldteams = pd.DataFrame(columns=[
            "intContractorID","Contractor","BusinessUnit","Postcode",
            "Latitude","Longitude","InternalContractor"
        ])
    root = tk.Tk()
    app = ResourceFinderApp(root, fieldteams)
    root.geometry("1000x640")
    root.mainloop()

if __name__ == "__main__":
    main()