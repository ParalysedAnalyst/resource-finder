"""
Minimal Tkinter GUI that wires together modules:
- Single Mapbox fetch per postcode (all contours)
- Local filter: minutes tab + BU + internal flag
- OSRM only when 'Calculate drive times' pressed
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

from api_config import geocode_postcode, fetch_isochrone, PostcodeNotFound
from geo_config import isochrone_to_gdf, teams_to_gdf, filter_teams_by_minutes, list_business_units, apply_team_filters
from routing_config import route_rank_teams

# --- GC palette ---
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
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("TFrame", background=PALETTE["GC Light Grey"])
    style.configure("TLabel", background=PALETTE["GC Light Grey"], foreground=PALETTE["GC Dark Green"])
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=PALETTE["GC Dark Green"])
    style.configure("TButton", padding=8, foreground="white", background=PALETTE["GC Mid Green"])
    style.map("TButton", background=[("active", PALETTE["GC Light Green"])])
    style.configure("Go.TButton", padding=12, font=("Segoe UI", 11, "bold"), foreground="white", background=PALETTE["GC Orange"])
    style.map("Go.TButton", background=[("active", "#ff8f3b")])

def _minutes_from_tab(nb: ttk.Notebook) -> int:
    return [15, 30, 45, 60][nb.index(nb.select())]

class ResourceFinderApp:
    COLS = ("Contractor","BusinessUnit","Postcode","InternalContractor","drive_min","drive_km","co2_kg")
    HEADINGS = {
        "Contractor":"Team Name","BusinessUnit":"Business Unit","Postcode":"Postcode",
        "InternalContractor":"Type","drive_min":"Drive (min)","drive_km":"Distance (km)","co2_kg":"CO₂ (kg)"
    }

    def __init__(self, root: tk.Tk, fieldteams: pd.DataFrame):
        self.root = root
        self.df = fieldteams
        self.site_lon = None; self.site_lat = None; self.iso_gdf = None
        self.pc_var = tk.StringVar(value=""); self.bu_var = tk.StringVar(value="(Any)")
        self.internal_var = tk.StringVar(value="either")
        self.sla_var = tk.BooleanVar(value=False)  # coming soon
        _apply_styles(self.root)
        self._build()

    def _build(self):
        top = ttk.Frame(self.root); top.pack(fill="x", padx=12, pady=8)
        ttk.Label(top, text="Field Team Resource Finder", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(0,6), columnspan=4)

        ttk.Label(top, text="Postcode:").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.pc_var, width=16).grid(row=2, column=0, sticky="w", padx=(0,8))

        ttk.Label(top, text="Business Unit:").grid(row=1, column=1, sticky="w")
        self.bu_combo = ttk.Combobox(top, textvariable=self.bu_var, width=28, state="readonly")
        self.bu_combo["values"] = list_business_units(self.df) if "BusinessUnit" in self.df.columns else ["(Any)"]
        self.bu_combo.set("(Any)")
        self.bu_combo.grid(row=2, column=1, sticky="w", padx=(0,8))

        # Internal/Contractor radios (compact)
        ic = ttk.Frame(top); ic.grid(row=2, column=2, sticky="w")
        ttk.Radiobutton(ic, text="Either", value="either", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Direct", value="1", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Contractor", value="0", variable=self.internal_var).pack(side="left", padx=3)

        ttk.Label(top, text="Include teams not meeting SLAs (coming soon)").grid(row=1, column=3, sticky="w")
        ttk.Checkbutton(top, variable=self.sla_var).grid(row=2, column=3, sticky="w")

        # Tabs for minutes
        self.tabs = ttk.Notebook(self.root); self.tabs.pack(fill="x", padx=12)
        for label in ("Within 15 Minutes","Within 30 Minutes","Within 45 Minutes","Within 60 Minutes"):
            self.tabs.add(ttk.Frame(self.tabs), text=label)

        # Buttons
        btns = ttk.Frame(self.root); btns.pack(fill="x", padx=12, pady=6)
        ttk.Button(btns, text="Apply filters", command=self.on_apply_filters).pack(side="left")
        ttk.Button(btns, text="Calculate drive times", style="Go.TButton", command=self.on_calculate_routes).pack(side="right")

        # Table
        table = ttk.Frame(self.root); table.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.tree = ttk.Treeview(table, columns=self.COLS, show="headings", height=18)
        for c, w in zip(self.COLS, (180,160,100,110,90,110,90)):
            self.tree.heading(c, text=self.HEADINGS[c])
            self.tree.column(c, width=w, anchor="w")
        ysb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); ysb.grid(row=0, column=1, sticky="ns")
        table.grid_rowconfigure(0, weight=1); table.grid_columnconfigure(0, weight=1)

        self.status = tk.StringVar(value="Enter a postcode and click Apply filters.")
        ttk.Label(self.root, textvariable=self.status).pack(fill="x", padx=12, pady=(0,6))

    def _populate(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        if "InternalContractor" in df.columns:
            df = df.copy()
            df["InternalContractor"] = df["InternalContractor"].map({1:"Direct",0:"Contractor"}).fillna("")
        for _, row in df.iterrows():
            self.tree.insert("", "end", values=tuple(row.get(c, "") for c in self.COLS))

    def on_apply_filters(self):
        pc = self.pc_var.get().strip()
        if not pc:
            messagebox.showinfo("Input needed", "Please enter a postcode.")
            return
        try:
            self.site_lon, self.site_lat = geocode_postcode(pc)
        except PostcodeNotFound as e:
            messagebox.showerror("Invalid postcode", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to geocode: {e}")
            return

        try:
            iso_gj = fetch_isochrone(self.site_lon, self.site_lat)  # single call
            self.iso_gdf = isochrone_to_gdf(iso_gj)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch isochrones: {e}")
            return

        mins = _minutes_from_tab(self.tabs)
        within = filter_teams_by_minutes(teams_to_gdf(self.df), self.iso_gdf, minutes=mins)

        internal_sel = self.internal_var.get()
        internal_flag = None if internal_sel == "either" else int(internal_sel)
        bu_choice = self.bu_var.get() or "(Any)"
        filtered = apply_team_filters(within, business_unit=bu_choice, internal_flag=internal_flag)

        self.bu_combo["values"] = list_business_units(filtered)
        if bu_choice not in self.bu_combo["values"]:
            self.bu_combo.set("(Any)")

        self._populate(filtered.assign(drive_min="", drive_km="", co2_kg=""))
        self.status.set(f"Applied filters: {len(filtered)} team(s) in {mins} minutes.")

        # keep a copy for routing step
        self.filtered = filtered

    def on_calculate_routes(self):
        if not hasattr(self, "filtered") or self.filtered.empty or self.site_lon is None:
            messagebox.showinfo("Info", "Apply filters first with at least one team.")
            return
        out = route_rank_teams(self.filtered, self.site_lon, self.site_lat, top_n=20)
        if out.empty:
            messagebox.showinfo("Info", "No routes calculated.")
            return
        self._populate(out)
        self.status.set(f"Calculated routes for {len(out)} team(s).")

if __name__ == "__main__":
    # For manual runs you can pipe in a tiny DataFrame here if needed.
    df = pd.DataFrame(columns=["intContractorID","Contractor","BusinessUnit","Postcode","Latitude","Longitude","InternalContractor"])
    root = tk.Tk(); app = ResourceFinderApp(root, df); root.geometry("1000x640"); root.mainloop()