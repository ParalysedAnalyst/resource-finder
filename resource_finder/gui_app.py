import tkinter as tk
from tkinter import ttk, messagebox
from requests import HTTPError
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import contextily as cx

from .api_config import geocode_postcode, fetch_isochrone, PostcodeNotFound
from .geo_config import (
    isochrone_to_gdf, teams_to_gdf, filter_teams_by_minutes,
    list_business_units, apply_team_filters,
)
from .routing_config import route_rank_teams

# Ground Control human_nature
human_nature = {
    "GC Dark Green": "#294238",
    "GC Light Green": "#b2d235",
    "GC Mid Green":  "#50b748",
    "GC Orange":     "#f57821",
    "GC Light Grey": "#e6ebe3",
}

def _apply_styles(root: tk.Tk):
    root.configure(bg=human_nature["GC Light Grey"])
    style = ttk.Style(root)
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("TFrame", background=human_nature["GC Light Grey"])
    style.configure("TLabel", background=human_nature["GC Light Grey"], foreground=human_nature["GC Dark Green"])
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=human_nature["GC Dark Green"])
    style.configure("TButton", padding=8, foreground="white", background=human_nature["GC Mid Green"])
    style.map("TButton", background=[("active", human_nature["GC Light Green"])])
    style.configure("Go.TButton", padding=12, font=("Segoe UI", 11, "bold"), foreground="white", background=human_nature["GC Orange"])
    style.map("Go.TButton", background=[("active", "#ff8f3b")])

class ResourceFinderApp:
    COLS = ("Contractor","BusinessUnit","Postcode","InternalContractor","drive_min","drive_km","co2_kg")
    HEADINGS = {
        "Contractor":"Team Name","BusinessUnit":"Business Unit","Postcode":"Postcode",
        "InternalContractor":"Type","drive_min":"Drive (min)","drive_km":"Distance (km)","co2_kg":"CO₂ (kg)"
    }

    def __init__(self, root: tk.Tk, fieldteams: pd.DataFrame):
        self.root = root; self.root.title("Field Team Resource Finder"); _apply_styles(self.root)

        # Data & state
        self.df = fieldteams.copy()
        self.teams_gdf = teams_to_gdf(self.df)
        self.current_pc = None
        self.site_lon = None; self.site_lat = None
        self.iso_gdf = None
        self.filtered = pd.DataFrame()
        self.routes_df = pd.DataFrame()

        # Tk variables
        self.pc_var = tk.StringVar(value="")
        self.bu_var = tk.StringVar(value="(Any)")
        self.internal_var = tk.StringVar(value="either")  # either / 1 / 0
        self.sla_var = tk.BooleanVar(value=False)
        self.minutes_var = tk.StringVar(value="60")       # 15/30/45/60

        self._build()

    # GUI Details
    def _build(self):
        top = ttk.Frame(self.root); top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        ttk.Label(top, text="Field Team Resource Finder", style="Header.TLabel").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0,6))

        # 1) Postcode
        ttk.Label(top, text="1) Postcode:").grid(row=1, column=0, sticky="w")
        pc_entry = ttk.Entry(top, textvariable=self.pc_var, width=18)
        pc_entry.grid(row=2, column=0, sticky="w", padx=(0,8))
        pc_entry.bind("<FocusOut>", self.on_postcode_changed)
        pc_entry.bind("<Return>", self.on_postcode_changed)

        # 2) Business Unit
        ttk.Label(top, text="2) Business Unit:").grid(row=1, column=1, sticky="w")
        self.bu_combo = ttk.Combobox(top, textvariable=self.bu_var, width=28, state="readonly")
        self.bu_combo["values"] = list_business_units(self.df) if "BusinessUnit" in self.df.columns else ["(Any)"]
        self.bu_combo.set("(Any)")
        self.bu_combo.grid(row=2, column=1, sticky="w", padx=(0,8))

        # Internal Contractor
        ic = ttk.Frame(top); ic.grid(row=2, column=2, sticky="w")
        ttk.Radiobutton(ic, text="Either", value="either", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Direct", value="1", variable=self.internal_var).pack(side="left", padx=3)
        ttk.Radiobutton(ic, text="Contractor", value="0", variable=self.internal_var).pack(side="left", padx=3)

        # SLA toggle (inline)
        ttk.Checkbutton(top, variable=self.sla_var, text="Include teams not meeting SLAs (coming soon)")\
            .grid(row=2, column=3, sticky="w")

        # Minutes
        bar = ttk.Frame(self.root); bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,6))
        ttk.Label(bar, text="Travel time band:").pack(side="left", padx=(0,6))
        for m in ("15","30","45","60"):
            ttk.Radiobutton(bar, text=f"Within {m} Minutes", value=m, variable=self.minutes_var).pack(side="left", padx=4)

        # Action buttons
        btns = ttk.Frame(self.root); btns.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,6))
        ttk.Button(btns, text="3) Apply filters", command=self.on_apply_filters).pack(side="left")
        ttk.Button(btns, text="4) Calculate drive times", style="Go.TButton", command=self.on_calculate_routes).pack(side="right")

        # Layout: table (left) and map (right)
        self.root.grid_columnconfigure(0, weight=1); self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

        table = ttk.Frame(self.root); table.grid(row=3, column=0, sticky="nsew", padx=(12,6), pady=(0,12))
        self.tree = ttk.Treeview(table, columns=self.COLS, show="headings", height=18)
        for c, w in zip(self.COLS, (180,160,100,110,90,110,90)):
            self.tree.heading(c, text=self.HEADINGS[c]); self.tree.column(c, width=w, anchor="w")
        ysb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); ysb.grid(row=0, column=1, sticky="ns")
        table.grid_rowconfigure(0, weight=1); table.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

        # Map figure
        map_wrap = ttk.Frame(self.root); map_wrap.grid(row=3, column=1, sticky="nsew", padx=(6,12), pady=(0,12))
        map_wrap.grid_rowconfigure(0, weight=1); map_wrap.grid_columnconfigure(0, weight=1)
        self.fig, self.ax = plt.subplots(figsize=(5,4), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=map_wrap)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._draw_map()  # initial blank map

        # Status line
        self.status = tk.StringVar(value="Enter a postcode (1) and tab away to load isochrones, then Apply filters (3).")
        ttk.Label(self.root, textvariable=self.status).grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,8))

    # ------------ helpers ------------
    def _populate(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        disp = df.copy()
        if "InternalContractor" in disp.columns:
            disp["InternalContractor"] = disp["InternalContractor"].map({1:"Direct",0:"Contractor"}).fillna("")
        for _, row in disp.iterrows():
            self.tree.insert("", "end", values=tuple(row.get(c, "") for c in self.COLS))

    def _refresh_bu_options(self, within_df: pd.DataFrame):
        # Prefer BUs from the minutes subset; fall back to all BUs if none
        values = list_business_units(within_df) if not within_df.empty else list_business_units(self.df)
        self.bu_combo["values"] = values
        if self.bu_var.get() not in values:
            self.bu_combo.set("(Any)")

    def _draw_map(self, show_route: LineString | None = None):
        self.ax.clear()
        self.ax.set_facecolor("#eef2eb")

        layers = []

        # 1) Isochrone polygon (selected minutes) → 3857
        if self.iso_gdf is not None:
            minutes = int(self.minutes_var.get())
            sel = self.iso_gdf[self.iso_gdf["minutes"] == minutes]
            if not sel.empty:
                iso3857 = sel.to_crs(epsg=3857)
                iso3857.plot(ax=self.ax, facecolor="#b2d235", edgecolor="#294238", alpha=0.25, zorder=2)
                layers.append(iso3857)

        # 2) Teams (filtered) → 3857 points
        if not self.filtered.empty:
            gdf4326 = gpd.GeoDataFrame(
                self.filtered,
                geometry=[Point(lon, lat) for lon, lat in zip(self.filtered["Longitude"], self.filtered["Latitude"])],
                crs="EPSG:4326",
            )
            teams3857 = gdf4326.to_crs(epsg=3857)
            teams3857.plot(ax=self.ax, marker="o", markersize=20, color="#50b748", alpha=0.95, zorder=4)
            layers.append(teams3857)

        # 3) Site point
        if self.site_lon is not None and self.site_lat is not None:
            site3857 = gpd.GeoSeries([Point(self.site_lon, self.site_lat)], crs="EPSG:4326").to_crs(epsg=3857)
            site3857.plot(ax=self.ax, marker="*", color="#f57821", markersize=140, zorder=5)
            layers.append(site3857)

        # 4) Selected route (if any)
        if show_route is not None:
            route3857 = gpd.GeoSeries([show_route], crs="EPSG:4326").to_crs(epsg=3857)
            route3857.plot(ax=self.ax, linewidth=3, color="#294238", zorder=6)
            layers.append(route3857)

        # Fit bounds
        if layers:
            bounds = gpd.GeoSeries(
                [lay.unary_union if hasattr(lay, "unary_union") else lay.iloc[0] for lay in layers],
                crs="EPSG:3857"
            ).total_bounds
            xmin, ymin, xmax, ymax = bounds
            dx, dy = (xmax - xmin) * 0.08 or 1000, (ymax - ymin) * 0.08 or 1000
            self.ax.set_xlim(xmin - dx, xmax + dx); self.ax.set_ylim(ymin - dy, ymax + dy)

        # Basemap tiles
        try:
            cx.add_basemap(self.ax, source=cx.providers.CartoDB.Positron, zoom=None)
        except Exception:
            pass

        self.ax.set_xticks([]); self.ax.set_yticks([])
        self.ax.set_title("Map view", fontsize=10)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ------------ events ------------
    def on_postcode_changed(self, event=None):
        pc = self.pc_var.get().strip().upper()
        if not pc or pc == self.current_pc:
            return
        try:
            self.site_lon, self.site_lat = geocode_postcode(pc)
            iso_gj = fetch_isochrone(self.site_lon, self.site_lat)  # one call -> all contours
            self.iso_gdf = isochrone_to_gdf(iso_gj)
            self.current_pc = pc

            # Default preview: within 60 minutes
            within60 = filter_teams_by_minutes(self.teams_gdf, self.iso_gdf, minutes=60)
            self._refresh_bu_options(within60)

            self.filtered = within60.assign(drive_min="", drive_km="", co2_kg="")
            self._populate(self.filtered)
            self._draw_map()
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
        self._refresh_bu_options(within)

        internal_sel = self.internal_var.get()
        internal_flag = None if internal_sel == "either" else int(internal_sel)
        bu_choice = self.bu_var.get() or "(Any)"

        self.filtered = apply_team_filters(within, business_unit=bu_choice, internal_flag=internal_flag)\
                            .assign(drive_min="", drive_km="", co2_kg="")
        self._populate(self.filtered)
        self._draw_map()
        self.status.set(f"Applied filters: {len(self.filtered)} team(s) in {minutes} minutes.")

    def on_calculate_routes(self):
        if self.site_lon is None or self.filtered is None or self.filtered.empty:
            messagebox.showinfo("Info", "Apply filters first with at least one team.")
            return

        routed = route_rank_teams(self.filtered, self.site_lon, self.site_lat, top_n=20, include_geometry=True)
        if routed.empty:
            messagebox.showinfo("Info", "No routes calculated.")
            return

        self.routes_df = routed
        self._populate(routed[list(self.COLS)])

        # Auto-select fastest row and draw its route
        first_id = next(iter(self.tree.get_children()), None)
        if first_id:
            self.tree.selection_set(first_id)
            self.tree.focus(first_id)
            self.on_row_select()  # will draw the selected route

            fastest = routed.iloc[0]
            self.status.set(
                f"Calculated routes for {len(routed)} team(s). "
                f"Showing fastest: {fastest['Contractor']} ({fastest['drive_min']:.1f} min)."
            )
        else:
            self._draw_map()
            self.status.set(f"Calculated routes for {len(routed)} team(s).")

    def on_row_select(self, event=None):
        if self.routes_df.empty:
            return
        sel = self.tree.selection()
        if not sel:
            self._draw_map()
            return
        values = self.tree.item(sel[0], "values")
        contractor = values[0]
        row = self.routes_df[self.routes_df["Contractor"] == contractor]
        if row.empty:
            self._draw_map()
            return

        geom = row.iloc[0].get("geometry")
        line = None
        if geom and isinstance(geom, dict) and geom.get("type") in ("LineString", "MultiLineString"):
            if geom["type"] == "LineString":
                line = LineString(geom["coordinates"])
            else:
                # take first part of MultiLineString
                coords = geom.get("coordinates") or []
                if coords:
                    line = LineString(coords[0])

        self._draw_map(show_route=line)

def main(fieldteams=None):
    if fieldteams is None:
        fieldteams = pd.DataFrame(columns=[
            "intContractorID","Contractor","BusinessUnit","Postcode",
            "Latitude","Longitude","InternalContractor"
        ])
    root = tk.Tk()
    app = ResourceFinderApp(root, fieldteams)
    root.geometry("1100x700")
    root.mainloop()

if __name__ == "__main__":
    main()