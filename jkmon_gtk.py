#!/usr/bin/env python3
"""
JKMONs - GTK3 desktop monitor for JK BMS (connection and monitor in one window).
Interface languages: English (default), Ukrainian, Russian - dropdown on the connection tab.

    python3 jkmon_gtk.py              # normal start
    python3 jkmon_gtk.py --selftest   # check that all libraries are installed

Needs system packages:  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 bluez
and Python packages:    bleak, dbus-fast
"""
import json
import logging
import re
import sys
import threading
from pathlib import Path


def selftest() -> int:
    problems = []
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa: F401
        import cairo  # noqa: F401
    except Exception as e:  # noqa: BLE001
        problems.append(f"GTK3 / python3-gi / python3-gi-cairo: {e!r}\n"
                        "  -> sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0")
    for mod in ("bleak", "dbus_fast", "jkcore", "blepair", "i18n"):
        try:
            __import__(mod)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{mod}: {e!r}")
    if problems:
        print("SELFTEST FAILED:\n" + "\n".join(problems))
        return 1
    print("SELFTEST OK")
    return 0


if "--selftest" in sys.argv:
    sys.exit(selftest())

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

try:
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf  # noqa: E402
except Exception:  # noqa: BLE001
    GdkPixbuf = None

import i18n  # noqa: E402
import jkcore  # noqa: E402
from i18n import tr  # noqa: E402

CONFIG = Path.home() / ".config" / "jkmon" / "config.json"
log = logging.getLogger("jkmon.gui")
LOGFILE = Path.home() / ".cache" / "jkmon" / "jkmon.log"

CSS = b"""
.card { background-color: alpha(@theme_fg_color, 0.06); border-radius: 12px; padding: 12px 14px; }
.cardtitle { font-size: 9pt; font-weight: 600; opacity: 0.6; }
.big { font-size: 26pt; font-weight: 700; }
.sub { opacity: 0.65; font-size: 9.5pt; }
.cellcard { background-color: alpha(@theme_fg_color, 0.07); border-radius: 10px; padding: 8px 10px; }
.cellv { font-size: 15pt; font-weight: 600; }
.cell-max { box-shadow: inset 0 0 0 1px #f5a524; }
.cell-min { box-shadow: inset 0 0 0 1px #4da3ff; }
levelbar block { min-height: 6px; border-radius: 3px; }
levelbar block.filled { background-color: #3ecf8e; }
levelbar block.empty { background-color: alpha(@theme_fg_color, 0.12); }
.cell-max levelbar block.filled { background-color: #f5a524; }
.cell-min levelbar block.filled { background-color: #4da3ff; }
.soc-mid levelbar block.filled { background-color: #f5a524; }
.soc-low levelbar block.filled { background-color: #f4564a; }
.errbox { border-radius: 12px; padding: 8px 14px; }
.errbox.ok { background-color: alpha(#3ecf8e, 0.18); }
.errbox.bad { background-color: alpha(#f4564a, 0.25); }
.errbox.warn { background-color: alpha(#f5a524, 0.25); }
.errbox.info { background-color: alpha(#4da3ff, 0.18); }
.chip { border-radius: 8px; padding: 3px 10px; background-color: alpha(@theme_fg_color, 0.08); }
.chip.on { background-color: alpha(#3ecf8e, 0.25); }
.chip.warn { background-color: alpha(#f5a524, 0.30); }
.chip.off { background-color: alpha(#f4564a, 0.25); }
flowboxchild, flowboxchild:focus, flowboxchild:selected { outline: none; outline-width: 0; box-shadow: none; background: none; }
.pos { color: #2fa36f; }
.neg { color: #d98a0b; }
"""

def load_icon_list():
    """The app icon in several sizes (rendered from jkmon.svg): panels pick the size they need from the window's icon list."""
    if GdkPixbuf is None:
        return []
    here = Path(__file__).resolve().parent
    sizes = (16, 22, 24, 32, 48, 64, 128, 256, 512)
    icons = []
    svg = here / "jkmon.svg"
    if svg.exists():
        for size in sizes:
            try:
                icons.append(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg), size, size, True))
            except GLib.Error:  # no SVG loader (librsvg) installed: use the PNG below
                icons = []
                break
    if icons:
        return icons
    for p in (here / "jkmon.png", Path("/usr/share/pixmaps/jkmons.png")):
        if p.exists():
            try:
                base = GdkPixbuf.Pixbuf.new_from_file(str(p))
            except GLib.Error:
                continue
            return [base.scale_simple(s, s, GdkPixbuf.InterpType.BILINEAR) for s in (16, 24, 32, 48, 64, 128, 256)] + [base]
    return []


ICONS = load_icon_list()
GREY, AMBER, GREEN, RED = "#999999", "#f5a524", "#3ecf8e", "#f4564a"


def cairo_gradient(x0, x1, charging):
    import cairo
    g = cairo.LinearGradient(x0, 0, x1, 0)
    cols = ((0.12, 0.64, 1.0), (0.24, 0.81, 0.56)) if charging else ((0.96, 0.65, 0.14), (0.96, 0.34, 0.29))
    if not charging:
        cols = cols[::-1]  # the intense colour is at the far (left) end
    g.add_color_stop_rgb(0, *cols[0])
    g.add_color_stop_rgb(1, *cols[1])
    return g


def status_info(status: str):
    """(translated text, dot colour) for a worker status; evaluated at call time so it follows the language."""
    table = {
        "starting": (tr("Starting…"), GREY),
        "scanning": (tr("Searching for BMS…"), AMBER),
        "pairing": (tr("Pairing…"), AMBER),
        "connecting": (tr("Connecting…"), AMBER),
        "connected": (tr("Connected"), GREEN),
        "offline": (tr("No connection, retrying…"), RED),
        "pin_error": (tr("PIN rejected"), RED),
    }
    return table.get(status, (status, GREY))


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_config(cfg: dict):
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg))
    except Exception:  # noqa: BLE001
        pass


def dur(s: int) -> str:
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    if d:
        return tr("{d} d {h} h {m} min").format(d=d, h=h, m=m)
    return tr("{h} h {m} min").format(h=h, m=m)


def label(text="", xalign=0.0, css=None, markup=False, **kw):
    lb = Gtk.Label(xalign=xalign, **kw)
    if markup:
        lb.set_markup(text)
    else:
        lb.set_text(text)
    if css:
        for c in css.split():
            lb.get_style_context().add_class(c)
    return lb


def card(title: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.get_style_context().add_class("card")
    box.pack_start(label(title.upper(), css="cardtitle"), False, False, 0)
    return box


def set_class(widget, name: str, on: bool):
    ctx = widget.get_style_context()
    if on:
        ctx.add_class(name)
    else:
        ctx.remove_class(name)


class KV(Gtk.Grid):
    """Two-column table 'name ... value' that updates in place."""

    def __init__(self):
        super().__init__(column_spacing=14, row_spacing=4)
        self.items = []

    def set_rows(self, rows):
        if len(rows) != len(self.items):
            for ch in self.get_children():
                self.remove(ch)
            self.items = []
            for i in range(len(rows)):
                k = label(css="sub")
                v = label(xalign=1.0, hexpand=True)
                self.attach(k, 0, i, 1, 1)
                self.attach(v, 1, i, 1, 1)
                self.items.append((k, v))
            self.show_all()
        for (k, v), (a, b) in zip(self.items, rows):
            k.set_text(a)
            v.set_text(str(b))


class CellWidget(Gtk.Box):
    def __init__(self, n: int):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.get_style_context().add_class("cellcard")
        top = Gtk.Box(spacing=6)
        top.pack_start(label(tr("#{n}").format(n=n), css="sub"), False, False, 0)
        self.res = label(css="sub", xalign=1.0, hexpand=True)
        top.pack_start(self.res, True, True, 0)
        self.pack_start(top, False, False, 0)
        self.volt = label(css="cellv")
        self.pack_start(self.volt, False, False, 0)
        self.bar = Gtk.LevelBar()
        for name in ("low", "high", "full"):
            self.bar.remove_offset_value(name)
        self.bar.set_min_value(2.5)
        self.bar.set_max_value(4.25)
        self.pack_start(self.bar, False, False, 0)


class GtkLogHandler(logging.Handler):
    def __init__(self, buffer: Gtk.TextBuffer):
        super().__init__()
        self.buffer = buffer
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))

    def emit(self, record):
        GLib.idle_add(self._append, self.format(record) + "\n")

    def _append(self, text):
        self.buffer.insert(self.buffer.get_end_iter(), text)
        lines = self.buffer.get_line_count()
        if lines > 300:
            self.buffer.delete(self.buffer.get_start_iter(), self.buffer.get_iter_at_line(lines - 300))
        return False


class App(Gtk.Window):
    def __init__(self):
        super().__init__(title="JKMONs")
        if ICONS:
            self.set_icon_list(ICONS)
        self.cfg = load_config()
        w, h = self.cfg.get("win_size", [1000, 780])
        self.set_default_size(max(600, min(int(w), 4000)), max(400, min(int(h), 3000)))
        if self.cfg.get("win_max"):
            self.maximize()
        i18n.set_lang(self.cfg.get("lang", i18n.DEFAULT))
        self.worker = None
        self.devices = {}
        self.bar_scale = None  # watts that fill the load bar (100%): 1C power, set from the first reading
        self.bar_value = 0.0
        self.err_msgs = []      # status messages shown one at a time in the plaque
        self.err_idx = 0
        self.err_warn = False
        self.err_logged = frozenset()
        self.last_data = None
        self.cell_widgets = []
        self.chips_key = None
        self.scanning = False
        self.status = (None, None)  # (worker status or None, optional text override)
        self.body = None
        self.stopping = False
        self.auto_switched = False

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.log_buffer = Gtk.TextBuffer()
        self.log_handler = GtkLogHandler(self.log_buffer)
        self.log_buffer.connect("changed", self.scroll_log)

        self.build_header()
        self.build_body()

        saved = self.cfg.get("address")
        if saved:
            self.devices[saved] = {"name": self.cfg.get("name", ""), "rssi": None, "ffe0": False}
            self.render_devices(select=saved)

        self.connect("delete-event", self.save_window_state)
        self.connect("destroy", self.on_destroy)
        GLib.timeout_add(500, self.tick)
        GLib.timeout_add_seconds(3, self.rotate_err)

    # ------------------------------------------------------------ header / language
    def build_header(self):
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("JKMONs")
        self.stop_btn = Gtk.Button()
        self.stop_btn.connect("clicked", lambda *_: self.stop_worker())
        self.stop_btn.set_no_show_all(True)
        hb.pack_start(self.stop_btn)
        self.status_lbl = label("")
        self.status_lbl.set_margin_end(14)
        hb.pack_end(self.status_lbl)
        self.set_titlebar(hb)
        self.set_status(*self.status)

    def on_lang_changed(self, combo):
        code = combo.get_active_id()
        if not code or code == i18n.get_lang():
            return
        i18n.set_lang(code)
        self.cfg["lang"] = code
        save_config(self.cfg)
        # rebuild after this handler returns: the rebuild destroys the combo box that fired the signal
        GLib.idle_add(self.relocalize)

    def relocalize(self):
        """Rebuild the window body in the new language, keeping what the user typed and the current tab."""
        tab = self.stack.get_visible_child_name()
        addr, pin = self.addr_entry.get_text(), self.pin_entry.get_text()
        show_all = self.show_all_chk.get_active()
        model, it = self.tree.get_selection().get_selected()
        selected = model[it][1] if it else None

        self.remove(self.body)
        self.body.destroy()
        self.cell_widgets = []
        self.chips_key = None
        self.build_body()

        self.addr_entry.set_text(addr)
        self.pin_entry.set_text(pin)
        self.show_all_chk.set_active(show_all)
        self.render_devices(select=selected)
        if self.scanning:
            self.spinner.start()
            self.scan_info.set_text(tr("scanning for 8 seconds…"))
        self.show_all()
        self.stack.set_visible_child_name(tab)
        self.set_status(*self.status)
        self.update_toolbar()
        if self.last_data is not None:
            self.update_monitor(self.last_data, record=False)
        else:
            self.refresh_placeholder()
        return False

    def build_body(self):
        """Tabs are a plain Gtk.StackSwitcher without custom CSS: every GTK theme draws them in its own style."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.body = outer
        self.add(outer)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self.build_connect_page(), "connect", tr("Connection"))
        self.stack.add_titled(self.build_monitor_page(), "monitor", tr("Monitor"))

        self.log_view = Gtk.TextView(buffer=self.log_buffer, editable=False, monospace=True,
                                     wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.log_view.set_left_margin(8)
        self.log_view.set_top_margin(6)
        sw = Gtk.ScrolledWindow()
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.log_view)
        logpage = Gtk.Box()
        logpage.set_margin_start(16)
        logpage.set_margin_end(16)
        logpage.set_margin_top(10)
        logpage.set_margin_bottom(16)
        logpage.pack_start(sw, True, True, 0)
        self.stack.add_titled(logpage, "log", tr("Log"))

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        switcher.set_homogeneous(True)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(12)
        switcher.set_margin_bottom(6)
        outer.pack_start(switcher, False, False, 0)
        outer.pack_start(self.stack, True, True, 0)

    def update_toolbar(self):
        running = self.worker is not None
        busy = self.stopping
        self.stop_btn.set_label(tr("Disconnect"))
        self.stop_btn.set_sensitive(not busy)
        if running or busy:
            self.stop_btn.show()
        else:
            self.stop_btn.hide()
        free = not running and not busy
        self.connect_btn.set_sensitive(free)
        self.demo_btn.set_sensitive(free)
        self.scan_btn.set_sensitive(free and not self.scanning)

    def scroll_log(self, buf):
        view = getattr(self, "log_view", None)
        if view is not None:
            view.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0, 0)

    # ------------------------------------------------------------ connect page
    def build_connect_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("start", "end"):
            getattr(page, f"set_margin_{side}")(28)
        page.set_margin_top(20)
        page.set_margin_bottom(28)

        title = GLib.markup_escape_text(tr("Connect to JK BMS"))
        head = Gtk.Box(spacing=10)
        head.pack_start(label(f'<span size="x-large" weight="bold">{title}</span>', markup=True, hexpand=True),
                        True, True, 0)
        self.lang_combo = Gtk.ComboBoxText()
        for code, name in i18n.LANGS:
            self.lang_combo.append(code, name)
        self.lang_combo.set_active_id(i18n.get_lang())
        self.lang_combo.set_tooltip_text(tr("Language"))
        self.lang_combo.set_valign(Gtk.Align.CENTER)
        self.lang_combo.connect("changed", self.on_lang_changed)
        head.pack_end(self.lang_combo, False, False, 0)
        page.pack_start(head, False, False, 0)
        page.pack_start(label(tr("Before connecting, close the JK app on your phone and turn off Bluetooth on it: "
                                 "the BMS accepts only one connection."), css="sub", wrap=True), False, False, 0)

        srow = Gtk.Box(spacing=8)
        self.scan_btn = Gtk.Button(label=tr("Find devices"))
        self.scan_btn.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.scan_btn.set_always_show_image(True)
        self.scan_btn.connect("clicked", self.on_scan)
        srow.pack_start(self.scan_btn, False, False, 0)
        self.connect_btn = Gtk.Button(label=tr("Connect"))
        self.connect_btn.get_style_context().add_class("suggested-action")
        self.connect_btn.connect("clicked", lambda *_: self.on_connect())
        srow.pack_start(self.connect_btn, False, False, 0)
        self.demo_btn = Gtk.Button(label=tr("Demo"))
        self.demo_btn.connect("clicked", lambda *_: self.start_worker(demo=True))
        srow.pack_end(self.demo_btn, False, False, 0)
        self.spinner = Gtk.Spinner()
        srow.pack_start(self.spinner, False, False, 4)
        self.scan_info = label(css="sub")
        srow.pack_start(self.scan_info, False, False, 0)
        page.pack_start(srow, False, False, 2)

        self.store = Gtk.ListStore(str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        for i, (title, width) in enumerate(((tr("Name"), 260), (tr("Address"), 180), (tr("Signal"), 90))):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_min_width(width)
            self.tree.append_column(col)
        sw = Gtk.ScrolledWindow()
        self.tree.connect("row-activated", lambda *_: self.on_connect())
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(300)  # about 10 rows, more rows scroll
        sw.set_max_content_height(300)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.tree)
        page.pack_start(sw, False, False, 0)
        page.pack_start(label(tr("★ marks devices that look like a JK BMS. The name can be anything "
                                 "(for example, JK-B2A8S20P)."), css="sub"), False, False, 0)

        opts = Gtk.Box(spacing=10)
        self.show_all_chk = Gtk.CheckButton(label=tr("show unnamed"))
        self.show_all_chk.connect("toggled", lambda *_: self.render_devices())
        opts.pack_start(self.show_all_chk, False, False, 0)
        page.pack_start(opts, False, False, 4)

        arow = Gtk.Box(spacing=10)
        arow.pack_start(label(tr("Enter the address manually:")), False, False, 0)
        self.addr_entry = Gtk.Entry()
        self.addr_entry.set_width_chars(20)
        self.addr_entry.set_placeholder_text("AA:BB:CC:DD:EE:FF")
        self.addr_entry.set_text(self.cfg.get("address", ""))
        arow.pack_start(self.addr_entry, False, False, 0)
        arow.pack_start(label(tr("(if an address is entered, the list above is ignored)"), css="sub"),
                        False, False, 0)
        page.pack_start(arow, False, False, 0)

        page.pack_start(label("<b>" + GLib.markup_escape_text(tr("PIN (optional)")) + "</b>", markup=True),
                        False, False, 6)
        prow = Gtk.Box(spacing=10)
        self.pin_entry = Gtk.Entry()
        self.pin_entry.set_visibility(False)
        self.pin_entry.set_width_chars(10)
        self.pin_entry.set_text(self.cfg.get("pin_v2", ""))
        prow.pack_start(self.pin_entry, False, False, 0)
        prow.pack_start(label(tr("Usually leave empty. Needed only if the BMS asks for a PIN during pairing."),
                              css="sub"), False, False, 0)
        page.pack_start(prow, False, False, 0)

        return page

    def render_devices(self, select=None):
        keep = select
        if keep is None:
            model, it = self.tree.get_selection().get_selected()
            keep = model[it][1] if it else None
        self.store.clear()
        items = sorted(self.devices.items(), key=lambda kv: (not kv[1]["ffe0"], -(kv[1]["rssi"] or -999)))
        sel_iter = None
        for addr, d in items:
            if not d["name"] and not self.show_all_chk.get_active() and addr != keep:
                continue
            name = ("★ " if d["ffe0"] else "") + (d["name"] or tr("(no name)"))
            rssi = tr("{v} dBm").format(v=d["rssi"]) if d["rssi"] is not None else "—"
            it = self.store.append([name, addr, rssi])
            if addr == keep:
                sel_iter = it
        if sel_iter is not None:
            self.tree.get_selection().select_iter(sel_iter)

    def on_scan(self, *_):
        if self.scanning:
            return
        self.scanning = True
        self.update_toolbar()
        self.spinner.start()
        self.scan_info.set_text(tr("scanning for 8 seconds…"))

        def work():
            try:
                res, err = jkcore.scan_devices(8.0), None
            except Exception as e:  # noqa: BLE001
                res, err = {}, e
            GLib.idle_add(self.scan_done, res, err)

        threading.Thread(target=work, daemon=True).start()

    def scan_done(self, res, err):
        self.scanning = False
        self.update_toolbar()
        self.spinner.stop()
        if err:
            self.scan_info.set_text("")
            self.message(tr("Search failed: {err}\n\nCheck that Bluetooth is on "
                            "(in a terminal: bluetoothctl power on).").format(err=repr(err)))
        else:
            self.scan_info.set_text(tr("found: {n}").format(n=len(res)))
            self.devices.update(res)
            self.render_devices()
        return False

    def message(self, text, kind=Gtk.MessageType.ERROR):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=kind,
                                buttons=Gtk.ButtonsType.OK, text=text)
        dlg.run()
        dlg.destroy()

    def on_connect(self, *_):
        manual = self.addr_entry.get_text().strip().upper().replace("-", ":")
        model, it = self.tree.get_selection().get_selected()
        if manual:
            if not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", manual):
                self.stack.set_visible_child_name("connect")
                self.message(tr("The address must look like this: AA:BB:CC:DD:EE:FF"))
                return
            address = manual
        elif it is not None:
            address = model[it][1]
        else:
            self.stack.set_visible_child_name("connect")
            self.message(tr("Press “Find devices” and pick the BMS in the list, or enter the address manually."),
                         Gtk.MessageType.INFO)
            return
        pin = self.pin_entry.get_text().strip()
        if pin and not pin.isdigit():
            self.stack.set_visible_child_name("connect")
            self.message(tr("The PIN must contain digits only."))
            return
        self.cfg.update(address=address, pin_v2=pin, name=self.devices.get(address, {}).get("name", ""))
        save_config(self.cfg)
        self.start_worker(address=address, pin=pin or None)

    # ------------------------------------------------------------ monitor page
    def build_monitor_page(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("start", "end", "top", "bottom"):
            getattr(root, f"set_margin_{side}")(16)
        sw.add(root)

        self.mon_stack = Gtk.Stack()
        self.wait_lbl = label("", css="sub", xalign=0.5)
        self.mon_stack.add_named(self.wait_lbl, "empty")
        self.mon_stack.add_named(sw, "data")

        hero = Gtk.Grid(column_spacing=12, column_homogeneous=True)
        root.pack_start(hero, False, False, 0)

        c = card(tr("State of charge (SOC)"))
        self.soc_big = label(css="big", markup=True)
        self.soc_bar = Gtk.LevelBar()
        for name in ("low", "high", "full"):
            self.soc_bar.remove_offset_value(name)
        self.soc_bar.set_min_value(0)
        self.soc_bar.set_max_value(100)
        self.soh_lbl = label(css="sub")
        for w in (self.soc_big, self.soc_bar, self.soh_lbl):
            c.pack_start(w, False, False, 0)
        self.soc_card = c
        hero.attach(c, 0, 0, 1, 1)

        c = card(tr("Voltage"))
        self.volt_big = label(css="big", markup=True)
        self.cellsum_lbl = label(css="sub")
        c.pack_start(self.volt_big, False, False, 0)
        c.pack_start(self.cellsum_lbl, False, False, 0)
        hero.attach(c, 1, 0, 1, 1)

        c = card(tr("Current"))
        self.cur_big = label(css="big", markup=True)
        self.curdir_lbl = label(css="sub")
        c.pack_start(self.cur_big, False, False, 0)
        c.pack_start(self.curdir_lbl, False, False, 0)
        hero.attach(c, 2, 0, 1, 1)

        c = card(tr("Power"))
        self.pow_big = label(css="big", markup=True)
        self.powsub_lbl = label(css="sub")
        c.pack_start(self.pow_big, False, False, 0)
        c.pack_start(self.powsub_lbl, False, False, 0)
        hero.attach(c, 3, 0, 1, 1)

        self.err_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.err_box.get_style_context().add_class("errbox")
        self.err_lbl = label(tr("No errors"), wrap=True)
        self.err_box.pack_start(self.err_lbl, False, False, 0)
        set_class(self.err_box, "ok", True)
        root.pack_start(self.err_box, False, False, 0)

        mid = Gtk.Grid(column_spacing=12)
        root.pack_start(mid, False, False, 0)
        c = card(tr("Cells"))
        self.cells_title = c.get_children()[0]
        self.cells_flow = Gtk.FlowBox()
        self.cells_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.cells_flow.set_can_focus(False)
        self.cells_flow.set_homogeneous(True)
        self.cells_flow.set_min_children_per_line(2)
        self.cells_flow.set_max_children_per_line(4)
        self.cells_flow.set_column_spacing(8)
        self.cells_flow.set_row_spacing(8)
        c.pack_start(self.cells_flow, False, False, 4)
        self.delta_lbl = label(markup=True)
        c.pack_start(self.delta_lbl, False, False, 2)
        self.cellstats_lbl = label(css="sub", wrap=True)
        c.pack_start(self.cellstats_lbl, False, False, 0)
        c.set_hexpand(True)
        mid.attach(c, 0, 0, 1, 1)

        c = card(tr("State"))
        c.set_size_request(260, -1)
        self.chips = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)  # one chip per line, always
        c.pack_start(self.chips, False, False, 0)
        c.pack_start(label(tr("Temperatures").upper(), css="cardtitle"), False, False, 6)
        self.temps_kv = KV()
        c.pack_start(self.temps_kv, False, False, 0)
        mid.attach(c, 1, 0, 1, 1)

        low = Gtk.Grid(column_spacing=12, column_homogeneous=True)
        root.pack_start(low, False, False, 0)
        self.cap_kv, self.life_kv, self.dev_kv = KV(), KV(), KV()
        for i, (title, kv) in enumerate(((tr("Capacity"), self.cap_kv), (tr("Lifetime"), self.life_kv),
                                         (tr("Device"), self.dev_kv))):
            c = card(title)
            c.pack_start(kv, False, False, 0)
            low.attach(c, i, 0, 1, 1)

        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        c.get_style_context().add_class("card")
        top = Gtk.Grid(column_homogeneous=True)
        self.load_cur_lbl = label(markup=True)
        self.load_pow_lbl = label(markup=True)
        top.attach(self.load_cur_lbl, 0, 0, 1, 1)
        top.attach(self.load_pow_lbl, 1, 0, 1, 1)
        c.pack_start(top, False, False, 0)
        self.load_bar = Gtk.DrawingArea()
        self.load_bar.set_size_request(-1, 14)
        self.load_bar.connect("draw", self.draw_load_bar)
        c.pack_start(self.load_bar, False, False, 2)
        bot = Gtk.Grid(column_homogeneous=True)
        self.load_state_lbl = label(markup=True)
        self.load_time_lbl = label(markup=True)
        bot.attach(self.load_state_lbl, 0, 0, 1, 1)
        bot.attach(self.load_time_lbl, 1, 0, 1, 1)
        c.pack_start(bot, False, False, 0)
        root.pack_start(c, False, False, 0)
        self.refresh_placeholder()
        return self.mon_stack

    def refresh_placeholder(self):
        self.wait_lbl.set_text(tr("Waiting for data from the BMS…") if self.worker else tr("Not connected"))
        self.mon_stack.set_visible_child_name("empty")

    def draw_load_bar(self, area, cr):
        """Bidirectional load bar: zero in the middle, charge to the right (blue to green), discharge to the left."""
        w, h = area.get_allocated_width(), area.get_allocated_height()
        fg = area.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        r = h / 2
        mid = w / 2

        def pill(x0, x1):
            cr.new_sub_path()
            cr.arc(x1 - r, r, r, -1.5708, 1.5708)
            cr.arc(x0 + r, r, r, 1.5708, 4.7124)
            cr.close_path()

        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.18)
        pill(0, w)
        cr.fill()
        frac = max(-1.0, min(1.0, self.bar_value / (self.bar_scale or 1.0)))
        if abs(frac) > 0.005:
            x0, x1 = (mid, mid + frac * mid) if frac > 0 else (mid + frac * mid, mid)
            cr.save()
            cr.rectangle(x0, 0, x1 - x0, h)
            cr.clip()
            grad = cairo_gradient(x0, x1, frac > 0)
            cr.set_source(grad)
            pill(0, w)
            cr.fill()
            cr.restore()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.45)
        cr.set_line_width(1)
        cr.move_to(mid, 0)
        cr.line_to(mid, h)
        cr.stroke()
        return False

    # ------------------------------------------------------------ worker control
    def start_worker(self, address=None, pin=None, demo=False):
        if self.worker:
            self.worker.stop()
        self.last_data = None
        self.auto_switched = False
        self.bar_scale = None
        self.bar_value = 0.0
        self.worker = jkcore.BmsWorker(address=address, pin=pin, demo=demo)
        self.worker.start()
        self.refresh_placeholder()
        self.update_toolbar()

    def stop_worker(self):
        worker, self.worker = self.worker, None
        self.stopping = True
        self.update_toolbar()
        self.set_status("starting", "Disconnecting…")

        def work():
            if worker:
                worker.stop()
            GLib.idle_add(self.after_stop)

        threading.Thread(target=work, daemon=True).start()

    def after_stop(self):
        self.stopping = False
        self.last_data = None
        self.update_toolbar()
        self.refresh_placeholder()
        self.stack.set_visible_child_name("connect")
        self.set_status(None)
        return False

    def save_window_state(self, *_):
        """Remember the window size (and maximized state) for the next start."""
        try:
            maximized = self.is_maximized()
            if not maximized:
                self.cfg["win_size"] = list(self.get_size())
            self.cfg["win_max"] = maximized
            save_config(self.cfg)
        except Exception:  # noqa: BLE001
            pass
        return False

    def on_destroy(self, *_):
        if self.worker:
            self.worker.stop()
        Gtk.main_quit()

    # ------------------------------------------------------------ periodic update
    def set_status(self, status, text=None):
        """text is an English message key (translated here) that overrides the standard status text."""
        self.status = (status, text)
        if status is None:
            self.status_lbl.set_text(tr("Not connected"))
            return
        t, color = status_info(status)
        if text == "Disconnecting…":
            t = tr("Disconnecting…")
        self.status_lbl.set_markup(f'<span foreground="{color}">●</span> {GLib.markup_escape_text(t)}')

    def tick(self):
        if not self.worker:
            return True
        snap = self.worker.mon.snapshot()
        self.set_status(snap["status"])
        if snap["status"] == "connected" and not self.auto_switched:
            self.auto_switched = True
            self.stack.set_visible_child_name("monitor")
        dv = snap["device"] or {}
        self.dev_kv.set_rows([(tr("Model"), dv.get("vendor") or "–"), (tr("Hardware"), dv.get("hw") or "–"),
                              (tr("Firmware"), dv.get("sw") or "–"), (tr("Power-ons"), dv.get("power_on", "–")),
                              (tr("Uptime"), dur(dv["uptime_s"]) if dv.get("uptime_s") else "–")])
        d = snap["data"]
        if d is not None and d is not self.last_data:
            self.last_data = d
            self.update_monitor(d)
        return True

    def show_err(self):
        """Show the current message of the status plaque (one line) and colour the plaque."""
        msgs = self.err_msgs
        if msgs:
            self.err_lbl.set_markup(msgs[self.err_idx % len(msgs)])
        else:
            self.err_lbl.set_text(tr("No errors"))
        set_class(self.err_box, "warn", bool(msgs) and self.err_warn)
        set_class(self.err_box, "info", bool(msgs) and not self.err_warn)
        set_class(self.err_box, "ok", not msgs)

    def rotate_err(self):
        if len(self.err_msgs) > 1:
            self.err_idx = (self.err_idx + 1) % len(self.err_msgs)
            self.show_err()
        return True

    def update_monitor(self, d, record=True):
        self.mon_stack.set_visible_child_name("data")
        unit = lambda u: f'<span alpha="60%"> {u}</span>'  # noqa: E731

        self.soc_big.set_markup(f'{d["soc"]}{unit("%")}')
        self.soc_bar.set_value(d["soc"])
        set_class(self.soc_card, "soc-low", d["soc"] < 15)
        set_class(self.soc_card, "soc-mid", 15 <= d["soc"] < 30)
        self.soh_lbl.set_text(f'SOH {d["soh"]}%')

        self.volt_big.set_markup(f'{d["pack_v"]:.2f}{unit(tr("V"))}')
        self.cellsum_lbl.set_text(tr("sum of cells {v:.2f} V").format(v=sum(c["v"] for c in d["cells"])))

        cur = d["current"]
        self.cur_big.set_markup(f'{cur:.2f}{unit(tr("A"))}')
        set_class(self.cur_big, "pos", cur > 0.05)
        set_class(self.cur_big, "neg", cur < -0.05)
        self.curdir_lbl.set_text(tr("charging") if cur > 0.05 else tr("discharging") if cur < -0.05 else tr("idle"))
        self.pow_big.set_markup(f'{d["power"]:.0f}{unit(tr("W"))}')
        self.powsub_lbl.set_text(tr("{v:.1f} / {n:.1f} Ah").format(v=d["cap_remaining"], n=d["cap_nominal"]))

        # Status plaque: the known flags are shown one at a time (rotating every 3 s) so that they take one line.
        # Flags with an unknown meaning are not shown, they are written to the log instead.
        bits = d["error_bits"]
        bitset = frozenset(bits)
        if bitset != self.err_logged:
            if bits:
                names = ", ".join(f"bit {b}: {jkcore.ERROR_NAMES.get(b, 'unknown meaning')}" for b in bits)
                log.info("BMS flags %s (%s)", d["errors_raw"], names)
            else:
                log.info("BMS flags cleared")
            self.err_logged = bitset
        msgs = []
        for bit in bits:
            known = jkcore.ERROR_NAMES.get(bit)
            if known:
                prefix = "ℹ " if bit in jkcore.INFO_BITS else "• "
                msgs.append(prefix + GLib.markup_escape_text(tr(known)))
        self.err_warn = any(b in jkcore.ERROR_NAMES and b not in jkcore.INFO_BITS for b in bits)

        # cells
        cells, st = d["cells"], d["cell_stats"]
        if len(self.cell_widgets) != len(cells):
            for ch in self.cells_flow.get_children():
                self.cells_flow.remove(ch)
            self.cell_widgets = [CellWidget(c["n"]) for c in cells]
            for cw in self.cell_widgets:
                self.cells_flow.add(cw)
                cw.get_parent().set_can_focus(False)
            self.cells_flow.show_all()
        for cw, c in zip(self.cell_widgets, cells):
            cw.volt.set_text(tr("{v:.3f} V").format(v=c["v"]))
            cw.res.set_text(tr("{x:.0f} mΩ").format(x=c["r"] * 1000))
            cw.bar.set_value(min(4.25, max(2.5, c["v"])))
            set_class(cw, "cell-max", c["n"] == st["max_cell"])
            set_class(cw, "cell-min", c["n"] == st["min_cell"] and st["min_cell"] != st["max_cell"])
        self.cells_title.set_text(f'{tr("Cells").upper()} · {d["cell_count"]}S')
        self.delta_lbl.set_markup(
            f'<span alpha="65%">{GLib.markup_escape_text(tr("Voltage difference"))}</span>  '
            f'<span size="large" weight="bold">{GLib.markup_escape_text(tr("{v:.0f} mV").format(v=st["delta"] * 1000))}</span>')
        self.cellstats_lbl.set_text(tr(
            "average {avg:.3f} V · min {min:.3f} V (#{min_cell}) · max {max:.3f} V (#{max_cell})"
        ).format(avg=st["avg"], min=st["min"], min_cell=st["min_cell"], max=st["max"], max_cell=st["max_cell"]))

        # chips
        bal = d["balance_mode"]
        on_off = lambda b: "ON" if b else "OFF"  # noqa: E731
        chips = [(tr("Charge {state}").format(state=on_off(d["chg_mos"])), "on" if d["chg_mos"] else "off"),
                 (tr("Discharge {state}").format(state=on_off(d["dsg_mos"])), "on" if d["dsg_mos"] else "off")]
        if bal:
            key = "Balance: charging {a:.2f} A" if bal == 1 else "Balance: discharging {a:.2f} A"
            chips.append((tr(key).format(a=abs(d["balance_current"])), "warn"))
        else:
            chips.append((tr("Balance: off"), ""))
        if d["heating"]:
            chips.append((tr("Heating {a:.2f} A").format(a=d["heating_current"]), "warn"))
        if d["precharge"]:
            chips.append((tr("Precharge"), "warn"))
        if chips != self.chips_key:
            self.chips_key = chips
            for ch in self.chips.get_children():
                self.chips.remove(ch)
            for text, kind in chips:
                self.chips.pack_start(label(text, css="chip " + kind if kind else "chip"), False, False, 0)
            self.chips.show_all()

        rows = []
        for k, v in d["temps"].items():
            name = "MOSFET" if k == "mos" else tr("Sensor {n}").format(n=k[1:])
            rows.append((name, f"{v:.1f} °C"))
        self.temps_kv.set_rows(rows)

        self.cap_kv.set_rows([(tr("Remaining"), tr("{v:.2f} Ah").format(v=d["cap_remaining"])),
                              (tr("Nominal"), tr("{v:.2f} Ah").format(v=d["cap_nominal"])),
                              (tr("Stored energy"), tr("{v:.2f} kWh").format(v=d["cap_remaining"] * d["pack_v"] / 1000))])
        self.life_kv.set_rows([(tr("Cycles"), d["cycles"]),
                               (tr("Total throughput"), tr("{v:.0f} Ah").format(v=d["cycle_capacity"])),
                               (tr("Run time"), dur(d["runtime_s"]))])

        if not d["sane"]:
            msgs.append("<i>" + GLib.markup_escape_text(tr(
                "Pack voltage does not match the sum of the cells: your firmware may use different field offsets. "
                "Send a screenshot of the JK app.")) + "</i>")
            self.err_warn = True
        self.err_msgs = msgs
        self.show_err()

        # load bar: current, power, status and the estimated time to full / empty
        green, amber = "#3ecf8e", "#f5a524"
        col = green if cur >= -0.05 else amber
        val = lambda t: f'<span size="large" weight="bold" foreground="{col}">{GLib.markup_escape_text(t)}</span>'  # noqa: E731
        self.load_cur_lbl.set_markup(GLib.markup_escape_text(tr("Current (A):")) + " " + val(f"{cur:.2f}"))
        self.load_pow_lbl.set_markup(GLib.markup_escape_text(tr("Power (W):")) + " " + val(f"{d['power']:.1f}"))
        state = tr("Charging") if cur > 0.05 else tr("Discharging") if cur < -0.05 else tr("Idle")
        self.load_state_lbl.set_markup(GLib.markup_escape_text(tr("Status:")) + " " + val(state))
        secs = None
        if cur > 0.05:
            secs = (d["cap_nominal"] - d["cap_remaining"]) / cur * 3600
        elif cur < -0.05:
            secs = d["cap_remaining"] / -cur * 3600
        if secs is not None and 0 <= secs < 100 * 3600:
            t = f"{int(secs) // 3600:02d}:{int(secs) % 3600 // 60:02d}:{int(secs) % 60:02d}"
        else:
            t = "--:--:--"
        self.load_time_lbl.set_markup(GLib.markup_escape_text(tr("Time left:")) + " " + val(t))
        if self.bar_scale is None:  # 100% of the bar = capacity (Ah) x nominal voltage (V) = the 1C power in W
            # LiFePO4 nominal cell voltage is 3.2 V: 4S = 12.8 V; the cell count and capacity come
            # from the BMS. If the cells are not in the LiFePO4 range, the measured pack voltage is used instead.
            avg_cell = d["pack_v"] / max(1, d["cell_count"])
            volts = d["cell_count"] * 3.2 if 2.4 <= avg_cell <= 3.7 else d["pack_v"]
            self.bar_scale = (d["cap_nominal"] * volts) or 1000.0
        self.bar_value = d["power"]
        self.load_bar.queue_draw()


def main():
    GLib.set_prgname("jkmons")
    GLib.set_application_name("JKMONs")
    if ICONS:
        Gtk.Window.set_default_icon_list(ICONS)
    app = App()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(app.log_handler)
    try:
        LOGFILE.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOGFILE, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(fh)
    except Exception:  # noqa: BLE001
        pass
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
