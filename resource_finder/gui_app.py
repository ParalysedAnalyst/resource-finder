import numbers
import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

import contextily as cx

from requests import HTTPError  # clear API error messages

from .api_config import geocode_postcode, fetch_isochrone, PostcodeNotFound
from .geo_config import (
    isochrone_to_gdf,
    teams_to_gdf,
    filter_teams_by_minutes,
    list_business_units,
    apply_team_filters,
)
from .routing_config import route_rank_teams

# Ground Control palette
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
    try:
        style.theme_use("clam")
    except Exception:
        # If theme selection fails, silently continue with defaults
        pass

    style.configure("TFrame", background=human_nature["GC Light Grey"])
    style.configure(
        "TLabel",
        background=human_nature["GC Light Grey"],
        foreground=human_nature["GC Dark Green"],
    )
    style.configure(
        "Header.TLabel",
        font=("Segoe UI", 11, "bold"),
        foreground=human_nature["GC Dark Green"],
    )
    style.configure(
        "TButton",
        padding=8,
        foreground="white",
        background=human_nature["GC Mid Green"],
    )
    style.map("TButton", background=[("active", human_nature["GC Light Green"])])
    style.configure(
        "Go.TButton",
        padding=12,
        font=("Segoe UI", 11, "bold"),
        foreground="white",
        background=human_nature["GC Orange"],
    )
    style.map("Go.TButton", background=[("active", "#ff8f3b")])


class ResourceFinderApp:
    COLS = (
        "Contractor",
        "BusinessUnit",
        "Postcode",
        "Contact",
        "Email",
        "drive_min",
        "drive_km",
        "co2_kg",
    )
    HEADINGS = {
        "Contractor": "Team Name",
        "BusinessUnit": "Business Unit",
        "Postcode": "Postcode",
        "Contact": "Contact number",
        "Email": "Email",
        "drive_min": "Drive (min)",
        "drive_km": "Distance (km)",
        "co2_kg": "CO₂ (kg)",
    }

    def __init__(self, root: tk.Tk, fieldteams: pd.DataFrame):
        self.root = root
        self.root.title("Field Team Resource Finder")
        _apply_styles(self.root)

        # Data & state
        self.df = fieldteams.copy()
        self.teams_gdf = teams_to_gdf(self.df)
        self.current_pc = None
        self.site_lon = None
        self.site_lat = None
        self.iso_gdf = None
        self.filtered = pd.DataFrame()
        self.routes_df = pd.DataFrame()

        # Avoid repeated basemap error popups
        self._basemap_error_reported = False

        # Tk variables
        self.pc_var = tk.StringVar(master=self.root, value="")
        self.bu_var = tk.StringVar(master=self.root, value="(Any)")
        self.internal_var = tk.StringVar(master=self.root, value="either")  # either / 1 / 0
        self.sla_var = tk.BooleanVar(master=self.root, value=False)
        self.minutes_var = tk.StringVar(master=self.root, value="60")       # 15/30/45/60
        self.status = tk.StringVar(master=self.root, value="")

        self._build()


    # User Interface construction
    def _build(self):
        top = ttk.Frame(self.root)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=8)

        ttk.Label(top, text="Field Team Resource Finder", style="Header.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 6)
        )

    # Postcode
        ttk.Label(top, text="1) Postcode:").grid(row=1, column=0, sticky="w")
        pc_entry = ttk.Entry(top, textvariable=self.pc_var, width=18)
        pc_entry.grid(row=2, column=0, sticky="w", padx=(0, 8))
        pc_entry.bind("<FocusOut>", self.on_postcode_changed)
        pc_entry.bind("<Return>", self.on_postcode_changed)

    # Business Unit
        ttk.Label(top, text="2) Business Unit:").grid(row=1, column=1, sticky="w")
        self.bu_combo = ttk.Combobox(
            top, textvariable=self.bu_var, width=28, state="readonly"
        )
        self.bu_combo["values"] = (
            list_business_units(self.df)
            if "BusinessUnit" in self.df.columns
            else ["(Any)"]
        )
        self.bu_combo.set("(Any)")
        self.bu_combo.grid(row=2, column=1, sticky="w", padx=(0, 8))

    # Internal Contractor toggle
        ic = ttk.Frame(top)
        ic.grid(row=2, column=2, sticky="w")
        ttk.Radiobutton(ic, text="Either", value="either", variable=self.internal_var).pack(
            side="left", padx=3
        )
        ttk.Radiobutton(ic, text="Direct", value="1", variable=self.internal_var).pack(
            side="left", padx=3
        )
        ttk.Radiobutton(
            ic, text="Contractor", value="0", variable=self.internal_var
        ).pack(side="left", padx=3)

    # SLA placeholder
        ttk.Checkbutton(
            top,
            variable=self.sla_var,
            text="Include teams not meeting SLAs (coming soon)",
        ).grid(row=2, column=3, sticky="w")

    # Travel time band
        bar = ttk.Frame(self.root)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        ttk.Label(bar, text="Travel time band:").pack(side="left", padx=(0, 6))
        for m in ("15", "30", "45", "60"):
            ttk.Radiobutton(
                bar, text=f"Within {m} Minutes", value=m, variable=self.minutes_var
            ).pack(side="left", padx=4)

    # Buttons
        btns = ttk.Frame(self.root)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        ttk.Button(btns, text="3) Apply filters", command=self.on_apply_filters).pack(
            side="left"
        )
        ttk.Button(
            btns,
            text="4) Calculate drive times",
            style="Go.TButton",
            command=self.on_calculate_routes,
        ).pack(side="right")

    # Layout: table (left), map (right)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

    # Table
        table = ttk.Frame(self.root)
        table.grid(row=3, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        self.tree = ttk.Treeview(
            table, columns=self.COLS, show="headings", height=18
        )
        for c, w in zip(self.COLS, (180, 160, 100, 140, 180, 90, 110, 90)):
            self.tree.heading(c, text=self.HEADINGS[c])
            self.tree.column(c, width=w, anchor="w")

        ysb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=ysb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

    # Map
        map_wrap = ttk.Frame(self.root)
        map_wrap.grid(row=3, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        map_wrap.grid_rowconfigure(0, weight=1)
        map_wrap.grid_columnconfigure(0, weight=1)

        self.fig, self.ax = plt.subplots(figsize=(5, 4), dpi=100)
        self.fig.set_facecolor("#dadfde")

    # Make the map fill the entire canvas area
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.canvas = FigureCanvasTkAgg(self.fig, master=map_wrap)
        widget = self.canvas.get_tk_widget()
        widget.grid(row=0, column=0, sticky="nsew")
        widget.configure(borderwidth=0, highlightthickness=0)
        self._draw_map()

    # Status line
        if not self.status.get():
            self.status.set(
                "Enter a postcode (1) and press Enter, then Apply filters (3)."
            )
        ttk.Label(self.root, textvariable=self.status).grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8)
        )


    # Helper methods
    def _populate(self, df: pd.DataFrame):
        self.tree.delete(*self.tree.get_children())
        disp = df.copy()

        for _, row in disp.iterrows():
            values = []
            for col in self.COLS:
                if col == "Contact":
                    val = row.get("MobileTel", "")
                elif col == "Email":
                    val = row.get("Email", "")
                else:
                    val = row.get(col, "")

                # Round numeric values to 2 decimal places
                if isinstance(val, numbers.Number):
                    val = f"{float(val):.2f}"
                values.append(val)

            self.tree.insert("", "end", values=tuple(values))

    def _refresh_bu_options(self, within_df: pd.DataFrame):
        values = (
            list_business_units(within_df)
            if not within_df.empty
            else list_business_units(self.df)
        )
        self.bu_combo["values"] = values
        if self.bu_var.get() not in values:
            self.bu_combo.set("(Any)")

    def _draw_map(self, show_route: LineString | None = None):
        """
        Draw a detailed web basemap (OpenStreetMap via contextily) and overlay
        the isochrone, teams, site, and optional route.

        If the basemap cannot be loaded (missing contextily, no internet, etc.),
        a simple message is shown once and the app continues with a plain background.
        """
        self.ax.clear()
        self.ax.set_facecolor("#dadfde")

        # --- prepare layers in EPSG:3857 ---
        iso3857 = None
        if self.iso_gdf is not None:
            minutes = int(self.minutes_var.get())
            sel = self.iso_gdf[self.iso_gdf["minutes"] == minutes]
            if not sel.empty:
                iso3857 = sel.to_crs(epsg=3857)

        teams3857 = None
        if not self.filtered.empty:
            gdf4326 = gpd.GeoDataFrame(
                self.filtered,
                geometry=[
                    Point(lon, lat)
                    for lon, lat in zip(
                        self.filtered["Longitude"], self.filtered["Latitude"]
                    )
                ],
                crs="EPSG:4326",
            )
            teams3857 = gdf4326.to_crs(epsg=3857)

        site3857 = None
        if self.site_lon is not None and self.site_lat is not None:
            site3857 = gpd.GeoSeries(
                [Point(self.site_lon, self.site_lat)], crs="EPSG:4326"
            ).to_crs(epsg=3857)

        route3857 = None
        if show_route is not None:
            route3857 = gpd.GeoSeries([show_route], crs="EPSG:4326").to_crs(epsg=3857)

        # --- bounds ---
        layers_for_bounds = [
            g for g in (iso3857, teams3857, site3857, route3857)
            if g is not None and len(g) > 0
        ]

        if layers_for_bounds:
            bounds = gpd.GeoSeries(
                [
                    g.unary_union if hasattr(g, "unary_union") else g.iloc[0]
                    for g in layers_for_bounds
                ],
                crs="EPSG:3857",
            ).total_bounds
            xmin, ymin, xmax, ymax = bounds
            dx, dy = (xmax - xmin) * 0.08 or 1000, (ymax - ymin) * 0.08 or 1000
        else:
            # Simple default extent (roughly UK area) if nothing is selected yet
            xmin, ymin, xmax, ymax = (-900000, 6000000, 500000, 8500000)
            dx, dy = 0, 0

        xmin_b, xmax_b = xmin - dx, xmax + dx
        ymin_b, ymax_b = ymin - dy, ymax + dy

        # --- detailed basemap via contextily ---
        if cx is not None:
            try:
                self.ax.set_xlim(xmin_b, xmax_b)
                self.ax.set_ylim(ymin_b, ymax_b)
                # Tiles with roads and features
                cx.add_basemap(self.ax, crs="EPSG:3857", attribution=False)
            except Exception:
                # If tiles fail, fall back to plain background and show a simple message
                self.ax.set_facecolor("#dadfde")
                if not self._basemap_error_reported:
                    self._basemap_error_reported = True
                    messagebox.showerror(
                        "Map background",
                        "Unable to load the detailed map background.\n\n"
                        "The application will still work without it.",
                    )
                    self.status.set("Map background not available.")
        else:
            # contextily is not installed
            if not self._basemap_error_reported:
                self._basemap_error_reported = True
                messagebox.showerror(
                    "Map background",
                    "Detailed map background is not available (contextily not installed).",
                )
                self.status.set("Map background not available.")

        # --- overlays (drawn on top of basemap) ---
        if iso3857 is not None:
            iso3857.plot(
                ax=self.ax,
                facecolor="#b2d235",
                edgecolor="#294238",
                alpha=0.35,
                zorder=2,
            )
        if teams3857 is not None:
            teams3857.plot(
                ax=self.ax,
                marker="o",
                markersize=20,
                color="#50b748",
                alpha=0.95,
                zorder=4,
            )
        if site3857 is not None:
            site3857.plot(
                ax=self.ax, marker="*", color="#f57821", markersize=140, zorder=5
            )
        if route3857 is not None:
            route3857.plot(ax=self.ax, linewidth=3, color="#294238", zorder=6)

        self.ax.set_xlim(xmin_b, xmax_b)
        self.ax.set_ylim(ymin_b, ymax_b)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.set_title("Map view", fontsize=10)
        self.canvas.draw_idle()


    # Event handlers

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
            within60 = filter_teams_by_minutes(
                self.teams_gdf, self.iso_gdf, minutes=60
            )
            self._refresh_bu_options(within60)

            self.filtered = within60.assign(
                drive_min="", drive_km="", co2_kg=""
            )
            self._populate(self.filtered)
            self._draw_map()
            self.status.set(
                f"Loaded {pc}: {len(within60)} team(s) within 60 minutes. "
                "Adjust filters and Apply."
            )
        except PostcodeNotFound as e:
            messagebox.showerror("Invalid postcode", str(e))
        except HTTPError as e:
            messagebox.showerror("Service error", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load site: {e}")

    def on_apply_filters(self):
        if self.iso_gdf is None:
            messagebox.showinfo(
                "Info", "Enter a postcode and press Enter to load isochrones first."
            )
            return

        minutes = int(self.minutes_var.get())
        within = filter_teams_by_minutes(
            self.teams_gdf, self.iso_gdf, minutes=minutes
        )
        self._refresh_bu_options(within)

        internal_sel = self.internal_var.get()
        internal_flag = None if internal_sel == "either" else int(internal_sel)
        bu_choice = self.bu_var.get() or "(Any)"

        self.filtered = apply_team_filters(
            within, business_unit=bu_choice, internal_flag=internal_flag
        ).assign(drive_min="", drive_km="", co2_kg="")
        self._populate(self.filtered)
        self._draw_map()
        self.status.set(
            f"Applied filters: {len(self.filtered)} team(s) in {minutes} minutes."
        )

    def on_calculate_routes(self):
        if self.site_lon is None or self.filtered is None or self.filtered.empty:
            messagebox.showinfo(
                "Info", "Apply filters first with at least one team selected."
            )
            return

        try:
            routed = route_rank_teams(
                self.filtered,
                self.site_lon,
                self.site_lat,
                top_n=20,
                include_geometry=True,
            )
        except Exception as e:
            messagebox.showerror("Routing error", f"Failed to calculate routes: {e}")
            return

        if routed.empty:
            messagebox.showinfo("Info", "No routes calculated.")
            return

        self.routes_df = routed
        self._populate(routed)

        # Auto-select fastest row and draw its route
        first_id = next(iter(self.tree.get_children()), None)
        if first_id:
            self.tree.selection_set(first_id)
            self.tree.focus(first_id)
            self.on_row_select()  # draws selected route

            fastest = routed.iloc[0]
            self.status.set(
                f"Calculated routes for {len(routed)} team(s). "
                f"Showing fastest: {fastest['Contractor']} "
                f"({float(fastest['drive_min']):.2f} min)."
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
        if geom and isinstance(geom, dict) and geom.get("type") in (
            "LineString",
            "MultiLineString",
        ):
            if geom["type"] == "LineString":
                line = LineString(geom["coordinates"])
            else:
                coords = geom.get("coordinates") or []
                if coords:
                    line = LineString(coords[0])

        self._draw_map(show_route=line)


# Entrypoint from __main__.py passes the real SQL DataFrame here
def main(fieldteams=None):
    if fieldteams is None:
        raise RuntimeError(
            "This application must be launched via 'python -m resource_finder' "
            "(__main__ loads the SQL data)."
        )
    root = tk.Tk()
    _ = ResourceFinderApp(root, fieldteams)
    root.geometry("1100x700")
    root.mainloop()


if __name__ == "__main__":
    # Prevent accidental direct run of this module without SQL
    raise SystemExit("Run the app with: python -m resource_finder")