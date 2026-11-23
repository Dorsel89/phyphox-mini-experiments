# -*- coding: utf-8 -*-
"""Erzeugt die Fehlvorstellungs-Experimente (E01-E15) als .phyphox-Dateien.

Grundlage: fehlvorstellungen_experimente.md, Vorlage wolle_waermt.phyphox.

Aufruf (aus phyphox_phyfob_experiments/):
    python generator/fehlvorstellungen.py                    # mit Hintergrund-View
    python generator/fehlvorstellungen.py --ohne-hintergrund # fuer den Einsatz
    python generator/fehlvorstellungen.py --nur aufzug wurf  # nur einzelne Dateien
    python generator/fehlvorstellungen.py --ziel ordner/     # anderer Zielordner

Jede Datei hat die Reiter 0 Hintergrund (optional), 1 Vortest, 2 Experiment, 3 Nachtest.
Die Hintergrund-View steht zusaetzlich zwischen den Kommentaren
<!-- BEGIN HINTERGRUND --> und <!-- END HINTERGRUND -->, falls man sie von Hand entfernen will.
"""
import argparse
import os
import re
from xml.sax.saxutils import escape

UUID = "-30f7-4671-8b43-5e40ba53514a"
SERVER = "https://didaktik.physik.rwth-aachen.de/phyphox/api"


def ch(short):
    return "cddf" + short + UUID


def a(s):
    """Text fuer ein XML-Attribut."""
    return escape(str(s), {'"': "&quot;"})


# ---------------------------------------------------------------------------
# View-Elemente
# ---------------------------------------------------------------------------

def attrs(**kw):
    out = []
    for k, v in kw.items():
        if v is None:
            continue
        k = k.rstrip("_")
        if isinstance(v, bool):
            v = "true" if v else "false"
        out.append(f'{k}="{a(v)}"')
    return (" " + " ".join(out)) if out else ""


def I(text, **kw):
    return f"<info{attrs(label=text, **kw)} />"


def H(text):
    return I(text, bold=True)


def S(h=2, **kw):
    return f'<separator{attrs(height=h, **kw)} />'


def V(label, inp, unit=None, prec=2, maps=None, **kw):
    s = f"<value{attrs(label=label, precision=prec, unit=unit, **kw)}>\n    <input>{inp}</input>"
    for mn, mx, txt in (maps or []):
        s += f"\n    <map{attrs(min=mn, max=mx)}>{escape(txt)}</map>"
    return s + "\n</value>"


def B(label, pairs=(), trigger=None, empties=(), dyn=None, maps=None, **kw):
    s = f"<button{attrs(label=label, dynamicLabel=dyn, **kw)}>"
    for src, dst in pairs:
        s += f'\n    <input type="buffer">{src}</input>\n    <output>{dst}</output>'
    for dst in empties:
        s += f'\n    <input type="empty"></input>\n    <output>{dst}</output>'
    for mn, mx, txt in (maps or []):
        s += f"\n    <map{attrs(min=mn, max=mx)}>{escape(txt)}</map>"
    if trigger:
        s += f"\n    <trigger>{trigger}</trigger>"
    return s + "\n</button>"


def G(label, data, lx="Zeit", ux="s", ly="", uy="", picks=(), **kw):
    """data: Liste (x, y[, farbe])."""
    kw.setdefault("partialUpdate", True)
    s = f"<graph{attrs(label=label, labelX=lx, unitX=ux, labelY=ly, unitY=uy, **kw)}>"
    for d in data:
        col = f' color="{d[2]}"' if len(d) > 2 else ""
        s += f'\n    <input axis="x"{col}>{d[0]}</input>\n    <input axis="y">{d[1]}</input>'
    for axis, lab, dst in picks:
        s += f'\n    <output axis="{axis}" label="{a(lab)}">{dst}</output>'
    return s + "\n</graph>"


def DD(out, opts, default=0, **kw):
    s = f"<dropdown{attrs(default=default, **kw)}>\n    <output>{out}</output>"
    for v, t in opts:
        s += f'\n    <map value="{v}">{escape(t)}</map>'
    return s + "\n</dropdown>"


def E(label, out, unit=None, default=0, **kw):
    return f"<edit{attrs(label=label, unit=unit, default=default, **kw)}>\n    <output>{out}</output>\n</edit>"


def T(label, out, default=0, **kw):
    return f"<toggle{attrs(label=label, default=default, **kw)}>\n    <output>{out}</output>\n</toggle>"


def gate(el, cond):
    """Haengt visibility an das Element, falls es noch keine hat."""
    first = el.split("\n", 1)[0]
    if "visibility=" in first:
        return el
    return re.sub(r"^<(\w[\w-]*)", lambda m: f'<{m.group(1)} visibility="{cond}"', el, count=1)


# ---------------------------------------------------------------------------
# Analyse-Bausteine
# ---------------------------------------------------------------------------

def inp(name, keep=True, as_=None):
    if isinstance(name, (int, float)):
        return f'<input{attrs(as_=as_)} type="value">{name}</input>'
    return f'<input{attrs(as_=as_)} keep="{"true" if keep else "false"}">{name}</input>'


def outp(name, append=False, as_=None):
    app = ' append="true"' if append else ""
    return f'<output{attrs(as_=as_)}{app}>{name}</output>'


def F(formula, ins, out, append=False, **kw):
    """ins: Liste von Namen (keep=true) oder (name, keep)."""
    s = f'<formula{attrs(formula=formula, **kw)}>'
    for x in ins:
        n, k = (x if isinstance(x, tuple) else (x, True))
        s += "\n    " + inp(n, k)
    return s + "\n    " + outp(out, append) + "\n</formula>"


def APP(src, dst, keep=False, append=False):
    return f"<append>\n    {inp(src, keep)}\n    {outp(dst, append)}\n</append>"


def LAST(src, dst):
    """Letzten Wert von src (behalten) in einen Ein-Wert-Container."""
    return APP(src, dst, keep=True)


def AVG(src, dst, std=None, keep=True):
    s = f'<average>\n    {inp(src, keep, "buffer")}\n    {outp(dst, as_="average")}'
    if std:
        s += "\n    " + outp(std, as_="stddev")
    return s + "\n</average>"


def MAX(y, dst, x=None, pos=None, mod="max"):
    s = f"<{mod}>"
    if x:
        s += "\n    " + inp(x, True, "x")
    s += "\n    " + inp(y, True, "y") + "\n    " + outp(dst, as_=mod)
    if pos:
        s += "\n    " + outp(pos, as_="position")
    return s + f"\n</{mod}>"


def MIN(y, dst, x=None, pos=None):
    return MAX(y, dst, x, pos, mod="min")


def COUNT(src, dst):
    return f'<count>\n    {inp(src, True, "buffer")}\n    {outp(dst, as_="count")}\n</count>'


def FIRST(src, dst):
    return f'<first>\n    {inp(src, True, "value")}\n    {outp(dst, as_="first")}\n</first>'


def RANGE(pairs, outs):
    """pairs: Liste (buffer, min, max); min/max None, Zahl oder Containername."""
    s = "<rangefilter>"
    for buf, mn, mx in pairs:
        s += "\n    " + inp(buf, True)
        if mn is not None:
            s += "\n    " + inp(mn, True, "min")
        if mx is not None:
            s += "\n    " + inp(mx, True, "max")
    for o in outs:
        s += "\n    " + outp(o)
    return s + "\n</rangefilter>"


def DIFF(src, dst):
    return f'<differentiate>\n    {inp(src, True, "in")}\n    {outp(dst, as_="out")}\n</differentiate>'


def SMOOTH(src, dst, sigma):
    return f'<gausssmooth sigma="{sigma}">\n    {inp(src, True, "in")}\n    {outp(dst, as_="out")}\n</gausssmooth>'


def SUB_FROM(src, dst, start):
    return (f'<subrange>\n    {inp(start, as_="from")}\n    {inp(src, True)}\n'
            f'    {outp(dst)}\n</subrange>')


def MATCH(ins, outs, append=True):
    s = "<match>"
    for i in ins:
        s += "\n    " + inp(i, True, "in")
    for o in outs:
        s += "\n    " + outp(o, append, "out")
    return s + "\n</match>"


# ---------------------------------------------------------------------------
# Bluetooth-Bausteine (phyphox:mini)
# ---------------------------------------------------------------------------

def ble_block(configs, outputs, dev_id="mini", mtu=None):
    s = (f'<bluetooth id="{a(dev_id)}" name="phyphox:mini" mode="notification"'
         f'{attrs(mtu=mtu)} subscribeOnStart="true">')
    for c, val, comment in configs:
        s += f"\n    <!-- {comment} -->\n    <config char=\"{ch(c)}\" conversion=\"hexadecimal\">{val}</config>"
    for c, off, rep, name in outputs:
        r = f' repeating="{rep}"' if rep else ""
        s += f'\n    <output char="{ch(c)}" conversion="float32LittleEndian" offset="{off}"{r}>{name}</output>'
    return s + "\n</bluetooth>"


def hdc_cfg(interval_100ms):
    return ("1006", f"01{interval_100ms:02X}",
            f"HDC1080 an, Messintervall {interval_100ms} x 100 ms")


HDC_OUT = [("1005", 0, None, "temp"), ("1005", 4, None, "hum"), ("1005", 8, None, "t")]


def bmp_cfg(osr=5, iir=2):
    return ("1008", f"01{osr:02X}{iir:02X}",
            f"BMP581 an, Oversampling-Code {osr} (5 = 32x), IIR-Code {iir}")


def bmp_out(p="p_raw", T="Tb_raw", t="tp_raw"):
    return [("1007", 0, 12, p), ("1007", 4, 12, T), ("1007", 8, 12, t)]


LSM_RATE = {1: "12,5 Hz", 2: "26 Hz", 3: "52 Hz", 4: "104 Hz", 5: "208 Hz", 6: "416 Hz"}


def lsm_cfg(enable, rate, range_acc=0x01, range_gyr=0x0C, event=10):
    return ("1002", f"{enable:02X}{rate:02X}{range_acc:02X}{range_gyr:02X}00{event:02X}",
            f"LSM6DSR: enable={enable} (1 Beschl., 3 beides), {LSM_RATE[rate]}, "
            f"Bereich-Code {range_acc}, Drehraten-Code {range_gyr}, float, {event} Werte/Paket")


def acc_out(p=""):
    return [("1001", 0, 16, f"{p}t_raw"), ("1001", 4, 16, f"{p}ax_raw"),
            ("1001", 8, 16, f"{p}ay_raw"), ("1001", 12, 16, f"{p}az_raw")]


def gyr_out(p=""):
    return [("1000", 0, 16, f"{p}tg_raw"), ("1000", 4, 16, f"{p}gx_raw"),
            ("1000", 8, 16, f"{p}gy_raw"), ("1000", 12, 16, f"{p}gz_raw")]


def acc_analysis(p="", win=None):
    """Betrag aus den neuen Rohdaten, dann Rohdaten an die Gesamt-Puffer anhaengen.
    win: Liste von Fenster-Containern (feste Groesse), die den Betrag zusaetzlich erhalten."""
    s = [F("sqrt([1_]^2+[2_]^2+[3_]^2)", [f"{p}ax_raw", f"{p}ay_raw", f"{p}az_raw"], f"{p}a_new")]
    s.append(APP(f"{p}a_new", f"{p}a_abs", keep=True, append=True))
    for w in (win or []):
        s.append(APP(f"{p}a_new", w, keep=True, append=True))
    for q in ("t", "ax", "ay", "az"):
        s.append(APP(f"{p}{q}_raw", f"{p}{q}" if q != "t" else f"{p}ta", append=True))
    return s


def acc_containers(p=""):
    return [c(f"{p}{q}_raw", 0) for q in ("t", "ax", "ay", "az")] + \
           [c(f"{p}{q}", 0) for q in ("ta", "ax", "ay", "az")] + [c(f"{p}a_new", 0), c(f"{p}a_abs", 0)]


def c(name, size=1, init=None, group=None, static=None):
    return (name, size, init, group, static)


SENSOR_INTRO = ("So funktioniert der Beschleunigungssensor: Er fühlt, wie stark er gerade geschoben, "
                "gehalten oder gezogen wird – also die Kraft der Unterlage, der Hand oder der Schnur "
                "(geteilt durch seine Masse). Die Schwerkraft selbst fühlt er nicht. Liegt er ruhig auf dem "
                "Tisch, zeigt er deshalb etwa 9,8 m/s², weil der Tisch ihn nach oben drückt.")

# ---------------------------------------------------------------------------
# Fragen
# ---------------------------------------------------------------------------
SICHER = [(0, "– bitte auswählen –"), (1, "geraten"), (2, "eher unsicher"),
          (3, "eher sicher"), (4, "sehr sicher")]
LIKERT_MAP = [(0.5, 1.5, "stimme nicht zu"), (1.5, 2.5, "stimme eher nicht zu"),
              (2.5, 3.5, "teils / teils"), (3.5, 4.5, "stimme eher zu"), (4.5, 5.5, "stimme zu")]


def MC(id_, text, opts, sicher=True, post_only=False):
    """opts: Liste (Antworttext, Bedeutung) – Bedeutung 'R' = richtig, sonst Vorstellung."""
    return dict(kind="mc", id=id_, text=text, opts=opts, sicher=sicher, post_only=post_only)


def LK(id_, text, key, post_only=False):
    return dict(kind="likert", id=id_, text=text, key=key, post_only=post_only)


def item_xml(it, prefix, nr):
    name = f"{prefix}_{it['id']}"
    out = [S(), I(f"{nr}. {it['text']}", bold=True)]
    if it["kind"] == "mc":
        opts = [(0, "– bitte auswählen –")] + [(i + 1, o[0]) for i, o in enumerate(it["opts"])]
        out.append(DD(name, opts))
        if it["sicher"]:
            out.append(I("Wie sicher bist du dir?", size=0.85))
            out.append(DD(name + "_sicher", SICHER))
    else:
        out.append(I("1 = stimme nicht zu   …   5 = stimme zu", size=0.85))
        out.append(f'<slider minValue="1" maxValue="5" stepSize="1" default="3" precision="0" '
                   f'showValue="false">\n    <output>{name}</output>\n</slider>')
        out.append(V("Deine Antwort", name, maps=LIKERT_MAP, visibility=name))
    return out


def item_containers(it, prefix):
    n = f"{prefix}_{it['id']}"
    names = [n]
    if it["kind"] == "mc" and it["sicher"]:
        names.append(n + "_sicher")
    return names


def mc_names(items, prefix):
    out = []
    for it in items:
        if it["kind"] == "mc":
            out += item_containers(it, prefix)
    return out


# ---------------------------------------------------------------------------
# Experiment-Klasse und Zusammenbau
# ---------------------------------------------------------------------------
G_PRE = "Antworten Vortest"
G_POST = "Vorhersage und Antworten Nachtest"


class Exp:
    def __init__(self, key, title, description, items, post_items, prediction,
                 containers, inputs, analysis, intro, body, results, export_sets,
                 background, outputs="", start_hint=None, pre_prediction=(),
                 analysis_attrs=""):
        self.__dict__.update(locals())
        del self.__dict__["self"]


def build(e, with_background=True):
    pre_items = [it for it in e.items]
    post_all = e.items + e.post_items
    L = []
    L.append('<?xml version="1.0" encoding="UTF-8"?>')
    L.append('<phyphox version="1.20" locale="de">')
    L.append(f"    <title>{escape(e.title)}</title>")
    L.append("    <category>phyphox:mini Fehlvorstellungen</category>")
    L.append("    <color>ADEBB3</color>")
    L.append(f"    <description>{escape(e.description)}</description>")

    # ---- Container
    L.append("\n    <data-containers>")
    L.append("        <!-- Messdaten und Auswertung -->")
    for name, size, init, group, static in e.containers:
        L.append(f"        <container{attrs(size=size, init=init, static=static, clearGroup=group)}>{name}</container>")
    L.append("\n        <!-- Vortest -->")
    for it in pre_items:
        for n in item_containers(it, "pre"):
            L.append(f'        <container size="1" clearGroup="{G_PRE}">{n}</container>')
    L.append("\n        <!-- Vorhersage und Nachtest -->")
    L.append(f'        <container size="1" clearGroup="{G_POST}">vorhersage</container>')
    for it in post_all:
        for n in item_containers(it, "post"):
            L.append(f'        <container size="1" clearGroup="{G_POST}">{n}</container>')
    L.append("\n        <!-- Steuerung der Anzeige (visibility) -->")
    for n in ("vorhersage_offen", "pre_offen", "post_offen"):
        L.append(f'        <container size="1">{n}</container>')
    L.append("\n        <!-- Phase und Rückmeldung des Servers -->")
    L.append('        <container size="1" init="1" clearGroup="_">phase_pre</container>')
    L.append('        <container size="1" init="2" clearGroup="_">phase_post</container>')
    for n, g in (("rx_pre_stored", G_PRE), ("rx_pre_total", G_PRE),
                 ("rx_post_stored", G_POST), ("rx_post_total", G_POST)):
        L.append(f'        <container size="1" clearGroup="{g}">{n}</container>')
    L.append("    </data-containers>")

    # ---- Input / Output
    L.append("\n    <input>")
    L.append(indent(e.inputs, 8))
    L.append("    </input>")
    if e.outputs:
        L.append("\n    <output>")
        L.append(indent(e.outputs, 8))
        L.append("    </output>")

    # ---- Analyse
    an = list(e.analysis)
    an.append("<!-- Anzeige steuern: offene Vorhersage und unbeantwortete Fragen -->")
    an.append(F("1-sign([1])", ["vorhersage"], "vorhersage_offen"))
    for prefix, items, target in (("pre", pre_items, "pre_offen"), ("post", post_all, "post_offen")):
        names = mc_names(items, prefix)
        formula = "+".join(f"(1-sign([{i + 1}]))" for i in range(len(names))) or "0"
        an.append(F(formula, names, target))
    L.append(f"\n    <analysis{e.analysis_attrs}>")
    L.append(indent("\n".join(an), 8))
    L.append("    </analysis>")

    # ---- Views
    L.append("\n    <views>")
    if with_background:
        L.append("        <!-- BEGIN HINTERGRUND: für den Einsatz im Unterricht entfernen -->")
        L.append('        <view label="0 Hintergrund">')
        bg = [I(f"{e.title} – Hintergrund für Lehrkräfte", bold=True, size=1.2),
              I("Diese Seite ist nur für die Erprobung gedacht und wird für den Einsatz entfernt.",
                italic=True, size=0.85)]
        for head, text in e.background:
            bg += [S(), H(head)]
            for para in text.strip().split("\n\n"):
                bg.append(I(" ".join(para.split())))
        bg += [S(), H("Antwortschlüssel")]
        nr = 0
        for it in post_all:
            nr += 1
            tag = " (nur Nachtest)" if it in e.post_items else ""
            bg.append(I(f"{nr}{tag}. {it['text']}", italic=True, size=0.85))
            if it["kind"] == "mc":
                lines = []
                for i, (txt, note) in enumerate(it["opts"]):
                    lines.append(f"{i + 1} = {txt} → {'richtig' if note == 'R' else note}")
                bg.append(I("\n".join(lines), size=0.85))
            else:
                bg.append(I(it["key"], size=0.85))
        bg.append(I("Vorhersage im Experiment", italic=True, size=0.85))
        for i, (t, n) in enumerate(e.prediction[1]):
            bg.append(I(f"{i + 1} = {t} → {'ERWARTET' if n == 'R' else n}", size=0.85))
        L.append(indent("\n".join(bg), 12))
        L.append("        </view>")
        L.append("        <!-- END HINTERGRUND -->")

    # Vortest
    v = [I(f"{e.title} – Vortest", bold=True, size=1.2),
         I(e.start_hint or "Verbinde den phyphox:mini, lege ihn ruhig auf den Tisch und tippe oben rechts "
                           "auf ▶. Beantworte dann die Fragen."),
         I("Wenn du die Messung über den Papierkorb löschst, bleiben deine Antworten erhalten, solange du "
           "sie im Dialog nicht mit auswählst.", size=0.85)]
    for i, it in enumerate(pre_items):
        v += item_xml(it, "pre", i + 1)
    v += submit_block("pre", "Vortest", "pretest")
    v.append(I("Danach weiter zum Reiter „2 Experiment“."))
    L.append('\n        <view label="1 Vortest">')
    L.append(indent("\n".join(v), 12))
    L.append("        </view>")

    # Experiment
    q, opts = e.prediction
    x = [I(f"{e.title} – Experiment", bold=True, size=1.2)] + list(e.intro)
    x += [S(), H("Schritt 1 – Vorhersage")] + list(e.pre_prediction) + [I(q)]
    x.append(DD("vorhersage", [(0, "– bitte auswählen –")] + [(i + 1, o[0]) for i, o in enumerate(opts)]))
    x.append(I("Wähle zuerst deine Vorhersage. Danach erscheinen die nächsten Schritte.",
               italic=True, visibility="vorhersage_offen"))
    x += [gate(el, "vorhersage") for el in e.body]
    L.append('\n        <view label="2 Experiment">')
    L.append(indent("\n".join(x), 12))
    L.append("        </view>")

    # Nachtest
    n = [I(f"{e.title} – Nachtest", bold=True, size=1.2),
         I("Beantworte die Fragen jetzt noch einmal, nachdem du gemessen hast.")]
    for i, it in enumerate(post_all):
        n += item_xml(it, "post", i + 1)
    n += submit_block("post", "Nachtest", "posttest")
    n.append(V("Rückmeldungen insgesamt", "rx_post_total", prec=0, visibility="rx_post_total"))
    L.append('\n        <view label="3 Nachtest">')
    L.append(indent("\n".join(n), 12))
    L.append("        </view>")
    L.append("    </views>")

    # ---- Export
    L.append("\n    <export>")
    for set_name, rows in e.export_sets:
        L.append(f'        <set name="{a(set_name)}">')
        for lab, buf in rows:
            L.append(f'            <data name="{a(lab)}">{buf}</data>')
        L.append("        </set>")
    if e.results:
        L.append('        <set name="Ergebnisse">')
        for buf, lab in e.results:
            L.append(f'            <data name="{a(lab)}">{buf}</data>')
        L.append("        </set>")
    L.append('        <set name="Antworten">')
    for it in pre_items:
        for nm in item_containers(it, "pre"):
            L.append(f'            <data name="{nm}">{nm}</data>')
    L.append('            <data name="vorhersage">vorhersage</data>')
    for it in post_all:
        for nm in item_containers(it, "post"):
            L.append(f'            <data name="{nm}">{nm}</data>')
    L.append("        </set>")
    L.append("    </export>")

    # ---- Netzwerk
    L.append("\n    <network>")
    for cid, phase, items, prefix, extra, rx in (
            ("pretest", "phase_pre", pre_items, "pre", [], "rx_pre"),
            ("posttest", "phase_post", post_all, "post", ["vorhersage"] + [r[0] for r in e.results], "rx_post")):
        L.append(f'        <connection id="{cid}" privacy="{SERVER}/privacy.php#umfrage" '
                 f'address="{SERVER}/survey_ingest.php?survey={e.key}" autoConnect="true" '
                 f'service="http/post" conversion="json">')
        L.append(f'            <send id="phase" type="buffer" keep="true">{phase}</send>')
        for nm in extra:
            L.append(f'            <send id="{nm}" type="buffer" keep="true">{nm}</send>')
        for it in items:
            for nm in item_containers(it, prefix):
                L.append(f'            <send id="{nm}" type="buffer" keep="true">{nm}</send>')
        L.append('            <send id="client" type="meta">uniqueID</send>')
        L.append('            <send id="time" type="time" />')
        L.append(f'            <receive id="stored" append="false">{rx}_stored</receive>')
        L.append(f'            <receive id="total" append="false">{rx}_total</receive>')
        L.append("        </connection>")
    L.append("    </network>")
    L.append("</phyphox>\n")
    return "\n".join(L)


def submit_block(prefix, label, trigger):
    return [S(),
            V("Noch nicht beantwortet", f"{prefix}_offen", prec=0, unit="Auswahlfelder",
              visibility=f"{prefix}_offen", color="orange"),
            B(f"{label} absenden", trigger=trigger, dyn=f"rx_{prefix}_stored",
              maps=[(0.5, None, f"{label} übertragen ✓ – erneut senden")]),
            V("Übertragene Antworten", f"rx_{prefix}_stored", prec=0, visibility=f"rx_{prefix}_total")]


def indent(text, n):
    pad = " " * n
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


# ===========================================================================
# Gemeinsame Mess-Bausteine
# ===========================================================================

def hdc_now():
    """t_now, T_now, H_now, Zeit seit dem letzten Marker."""
    return [LAST("temp", "T_now"), LAST("hum", "H_now"), LAST("t", "t_now"),
            F("[1]-[2]", ["t_now", "t_mark"], "t_since")]


HDC_NOW_CONT = [c("t", 0), c("temp", 0), c("hum", 0), c("t_now"), c("T_now"), c("H_now"),
                c("t_mark"), c("t_since")]


def mark(label, pairs, now="t_now"):
    """Marker-Knopf, der zusaetzlich den Zeitpunkt fuer 'Zeit seit Marker' setzt."""
    return B(label, list(pairs) + [(now, "t_mark")])


def bmp_analysis(win="p_win", Twin="Tb_win"):
    return [APP("p_raw", win, keep=True, append=True), APP("Tb_raw", Twin, keep=True, append=True),
            APP("p_raw", "p", append=True), APP("Tb_raw", "Tb", append=True),
            APP("tp_raw", "tp", append=True),
            AVG(win, "p_avg"), AVG(Twin, "Tb_avg"), LAST("p", "p_now"), LAST("tp", "tp_now"),
            F("[1]-[2]", ["tp_now", "t_mark"], "t_since")]


def bmp_containers(win=40):
    return [c("p_raw", 0), c("Tb_raw", 0), c("tp_raw", 0), c("p", 0), c("Tb", 0), c("tp", 0),
            c("p_win", win), c("Tb_win", win), c("p_avg"), c("Tb_avg"), c("p_now"), c("tp_now"),
            c("t_mark"), c("t_since")]


def free_fall_analysis(thr=2.5):
    """Zeit im freien Fall = (Anzahl Werte mit |a| unter thr) x Abtastintervall."""
    return [RANGE([("a_abs", 0, thr)], ["a_free"]), COUNT("a_free", "n_free"), COUNT("ta", "n_all"),
            FIRST("ta", "ta_first"), LAST("ta", "ta_last"),
            F("([3]-[2])/([4]-1)", ["n_free", "ta_first", "ta_last", "n_all"], "dt_s"),
            F("[1]*[2]", ["n_free", "dt_s"], "t_free"), AVG("a_free", "a_free_avg")]


FREE_FALL_CONT = [c("a_free", 0), c("n_free"), c("n_all"), c("ta_first"), c("ta_last"), c("dt_s"),
                  c("t_free"), c("a_free_avg")]
ACC_CLEAR = ["ta", "ax", "ay", "az", "a_abs"]


# ===========================================================================
# Die Experimente
# ===========================================================================
EXPS = []

# ---------------------------------------------------------------------------
# E01 Wolle waermt (Feldnamen wie in der ersten Fassung, damit der Server gleich bleibt)
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="wolle_waermt", title="Wolle wärmt?",
    description="Vortest, Experiment mit dem phyphox:mini (Temperatur in einer Wollsocke) und Nachtest zur "
                "Vorstellung „Wolle macht warm“. Die Antworten werden an den Umfrage-Server übertragen.",
    start_hint="Lege den phyphox:mini auf den Tisch und fasse ihn nicht mehr an. Tippe dann oben rechts auf ▶ "
               "und beantworte die Fragen. Die Messung läuft währenddessen schon mit.",
    items=[
        MC("schal", "Ein Thermometer liegt seit einer Stunde in einem Zimmer mit 21 °C. Du wickelst es in einen "
                    "dicken Wollschal. Was zeigt es nach 15 Minuten an?",
           [("deutlich mehr als 21 °C", "Wolle macht warm"), ("etwa 21 °C", "R"),
            ("weniger als 21 °C", "Wolle kühlt / unklare Vorstellung")]),
        MC("eis", "Du willst ein Eis am Stiel ohne Kühlschrank möglichst lange kalt halten. Was ist am besten?",
           [("offen auf den Tisch legen", "Wolle macht warm (also schlecht fürs Eis)"),
            ("in einen Wollpullover wickeln", "R"),
            ("das macht keinen Unterschied", "Isolation nicht verstanden")]),
        LK("jacke", "Eine Winterjacke erzeugt Wärme.", "Zustimmung (4–5) = Fehlvorstellung"),
        LK("decke", "Unter einer dicken Decke wird es auch dann wärmer, wenn niemand darunter liegt.",
           "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("schneemann", "Zwei gleiche Schneemänner stehen in der Sonne. Einer bekommt einen Wintermantel "
                         "angezogen. Welcher schmilzt schneller?",
           [("der mit Mantel", "Wolle/Mantel macht warm"), ("der ohne Mantel", "R"),
            ("beide gleich schnell", "Isolation nicht verstanden")], sicher=False),
        MC("erklaerung", "Warum ist die Temperatur gestiegen, als deine Hand mit in der Socke war?",
           [("Wolle erzeugt Wärme, sobald sie etwas berührt", "Wolle macht warm"),
            ("Die Hand gibt Wärme ab, die Wolle hält sie zurück", "R"),
            ("Durch die Reibung der Hand an der Wolle", "Ausweicherklärung")], sicher=False),
    ],
    prediction=("Der mini kommt gleich für 5 Minuten in die Socke. Was passiert mit der Temperatur?",
                [("sie steigt deutlich", "Wolle macht warm"), ("sie bleibt etwa gleich", "R"),
                 ("sie sinkt", "unklare Vorstellung")]),
    containers=HDC_NOW_CONT + [c(n) for n in ("t0", "T0", "T1", "T2", "dT_socke", "dT_hand")],
    inputs=ble_block([hdc_cfg(10)], HDC_OUT),
    analysis=hdc_now() + [F("[1]-[2]", ["T1", "T0"], "dT_socke"), F("[1]-[2]", ["T2", "T1"], "dT_hand")],
    intro=[I("Du brauchst eine Wollsocke, einen Handschuh oder einen Schal. Das Kleidungsstück muss "
             "Zimmertemperatur haben (nicht gerade getragen, nicht von der Heizung).")],
    body=[
        G("Temperatur am phyphox:mini", [("t", "temp")], ly="Temperatur", uy="°C", scaleMinY="fixed",
          scaleMaxY="fixed", minY=15, maxY=40),
        V("Temperatur jetzt", "T_now", "°C"),
        S(), H("Schritt 2 – Nur die Socke"),
        I("Stecke den mini tief in die Socke. Fasse ihn dabei möglichst nur kurz an und lege die Socke auf den "
          "Tisch. Tippe dann sofort:"),
        mark("Der mini ist jetzt in der Socke", [("T_now", "T0"), ("t_now", "t0")]),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        I("Warte, bis 300 s vergangen sind, und tippe dann:"),
        mark("5 Minuten sind um", [("T_now", "T1")]),
        V("Änderung nur in der Socke", "dT_socke", "K"),
        S(), H("Schritt 3 – Socke mit Hand"),
        I("Stecke jetzt deine Hand mit in die Socke und umschließe den mini locker. Warte 2 Minuten (120 s) und "
          "tippe dann:"),
        mark("2 Minuten mit Hand sind um", [("T_now", "T2")]),
        V("Änderung mit Hand in der Socke", "dT_hand", "K"),
        S(), I("Vergleiche die beiden Änderungen mit deiner Vorhersage. Woher kommt die Wärme? Weiter zum Reiter "
               "„3 Nachtest“."),
    ],
    results=[("T0", "T beim Einwickeln (°C)"), ("dT_socke", "Änderung in der Socke (K)"),
             ("dT_hand", "Änderung mit Hand (K)")],
    export_sets=[("Messung", [("Zeit (s)", "t"), ("Temperatur (°C)", "temp"), ("Relative Feuchte (%)", "hum")]),
                 ("Marker", [("Zeitpunkt Einwickeln (s)", "t0"), ("T beim Einwickeln (°C)", "T0"),
                             ("T nach 5 min Socke (°C)", "T1"), ("T nach 2 min Hand (°C)", "T2")])],
    background=[
        ("Zweck", """Die Lernenden prüfen, ob Wolle selbst Wärme erzeugt. Der mini liegt 5 Minuten in einer Socke
         mit Zimmertemperatur – die Temperatur ändert sich kaum. Erst mit der Hand in der Socke steigt sie deutlich.
         Ersatzvorstellung: Die Wärme kommt vom Körper, die Wolle bremst nur den Wärmestrom (Isolation)."""),
        ("Fehlvorstellung", """„Wolle macht warm“ (Schecker u. a. 2018, S. 151; Handout). Materialien wird die
         Eigenschaft „warm“ zugeschrieben; jüngere Lernende meinen, eine Puppe unter der Bettdecke werde gewärmt."""),
        ("Physik", """Wolle schließt viel ruhende Luft ein und leitet Wärme schlecht. Sie verlangsamt den Wärmestrom
         in beide Richtungen: Ein warmer Körper bleibt länger warm, ein kalter länger kalt. Ohne Wärmequelle im
         Inneren stellt sich Zimmertemperatur ein."""),
        ("Erwartung", """Nur Socke: Änderung unter etwa 0,5 K. Mit Hand: mehrere Kelvin Anstieg in 2 Minuten."""),
        ("Erweiterung (noch nicht umgesetzt)", """Kalt-Vergleich: mini abkühlen, einmal offen und einmal in der
         Socke aufwärmen lassen – in der Socke bleibt er länger kalt. Trennt die Vorstellungen am besten. Dazu passt
         die Cola-Dose aus dem Kühlschrank in der Wolldecke (Buch S. 151)."""),
        ("Hinweise", """Eigenerwärmung der Elektronik in der Isolation könnte einige Zehntel Kelvin Anstieg erzeugen
         und die Fehlvorstellung scheinbar bestätigen – vor dem Einsatz testen. Die Socke darf nicht gerade getragen
         worden sein oder von der Heizung kommen. Beim Einwickeln den mini nur kurz anfassen."""),
    ],
))

# ---------------------------------------------------------------------------
# E02 Ventilator
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="ventilator", title="Macht der Ventilator die Luft kälter?",
    description="Vortest, Experiment mit dem phyphox:mini (Temperatur im Luftstrom eines Ventilators, "
                "trocken und mit feuchtem Tuch) und Nachtest zur Vorstellung „Wind kühlt die Luft“.",
    items=[
        MC("zimmer", "Ein Ventilator läuft eine Stunde lang in einem geschlossenen Zimmer. Die Lufttemperatur "
                     "im Zimmer ist danach …",
           [("niedriger als vorher", "Wind/Ventilator kühlt die Luft"),
            ("gleich oder minimal höher", "R"),
            ("deutlich höher", "Motorwärme überschätzt")]),
        MC("nass", "Warum fühlt sich Wind auf nasser Haut kalt an?",
           [("Der Wind ist kälter als ruhende Luft.", "bewegte Luft ist kälter"),
            ("Das Wasser verdunstet und entzieht der Haut dabei Energie.", "R"),
            ("Der Wind bläst die Körperwärme weg.", "teilweise richtig (Konvektion), erklärt nicht den Unterschied nass/trocken")]),
        LK("bewegt", "Bewegte Luft ist kälter als ruhende Luft.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("thermometer", "Ein Thermometer hängt bei Windstille im Schatten. Dann kommt trockener Wind auf. "
                          "Das Thermometer zeigt …",
           [("weniger an", "Wind kühlt"), ("etwa dasselbe an", "R"), ("mehr an", "Reibung erwärmt")],
           sicher=False),
        MC("erklaerung", "Warum sank die Temperatur, als das feuchte Tuch im Luftstrom war?",
           [("Das Tuch war kälter als die Luft.", "Ausweicherklärung"),
            ("Wasser verdunstete und nahm dabei Energie auf.", "R"),
            ("Mit Tuch bläst der Ventilator stärker.", "bewegte Luft ist kälter")], sicher=False),
    ],
    prediction=("Der mini kommt gleich 2 Minuten in den Luftstrom des Ventilators. Was passiert mit der "
                "Temperatur, die er misst?",
                [("sie sinkt deutlich", "Wind kühlt die Luft"), ("sie bleibt etwa gleich", "R"),
                 ("sie steigt", "Reibung/Motor")]),
    containers=HDC_NOW_CONT + [c(n) for n in ("T_a", "T_b", "T_c", "T_d", "H_c", "H_d",
                                                "dT_trocken", "dT_feucht", "dH_feucht")],
    inputs=ble_block([hdc_cfg(10)], HDC_OUT),
    analysis=hdc_now() + [
        F("[1]-[2]", ["T_b", "T_a"], "dT_trocken"),
        F("[1]-[2]", ["T_d", "T_c"], "dT_feucht"),
        F("[1]-[2]", ["H_d", "H_c"], "dH_feucht")],
    intro=[I("Du brauchst einen Ventilator (oder eine Pappe zum Fächeln) und ein feuchtes, nicht "
             "tropfnasses Tuch. Der mini liegt die ganze Zeit an derselben Stelle.")],
    body=[
        G("Temperatur", [("t", "temp")], ly="Temperatur", uy="°C", scaleMinY="fixed", scaleMaxY="fixed",
          minY=10, maxY=30),
        G("Relative Luftfeuchtigkeit", [("t", "hum")], ly="rel. Feuchte", uy="%", scaleMinY="fixed",
          scaleMaxY="fixed", minY=0, maxY=100),
        V("Temperatur jetzt", "T_now", "°C"),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        S(), H("Schritt 2 – Trockener Luftstrom"),
        I("Lass den mini zuerst 2 Minuten ruhig liegen. Schalte dann den Ventilator ein (oder fächle "
          "gleichmäßig) und tippe sofort:"),
        mark("Ventilator ist an", [("T_now", "T_a")]),
        I("Warte 2 Minuten (120 s) im Luftstrom und tippe dann:"),
        mark("2 Minuten Luftstrom sind um", [("T_now", "T_b")]),
        V("Temperaturänderung im trockenen Luftstrom", "dT_trocken", "K"),
        S(), H("Schritt 3 – Luftstrom mit feuchtem Tuch"),
        I("Lege das feuchte Tuch locker über den mini (Gehäuse geschlossen lassen, nicht tropfnass!) und "
          "lass den Ventilator weiterlaufen. Tippe dabei:"),
        mark("Feuchtes Tuch liegt auf dem mini", [("T_now", "T_c"), ("H_now", "H_c")]),
        I("Warte wieder 2 Minuten und tippe dann:"),
        mark("2 Minuten mit Tuch sind um", [("T_now", "T_d"), ("H_now", "H_d")]),
        V("Temperaturänderung mit feuchtem Tuch", "dT_feucht", "K"),
        V("Änderung der Luftfeuchtigkeit", "dH_feucht", "%"),
        S(), I("Vergleiche beide Änderungen mit deiner Vorhersage. Was ist beim Tuch anders als beim "
               "trockenen Luftstrom? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("dT_trocken", "Temperaturänderung trocken (K)"), ("dT_feucht", "Temperaturänderung feucht (K)"),
             ("dH_feucht", "Feuchteänderung mit Tuch (%)")],
    export_sets=[("Messung", [("Zeit (s)", "t"), ("Temperatur (°C)", "temp"), ("Relative Feuchte (%)", "hum")]),
                 ("Marker", [("T Ventilator an (°C)", "T_a"), ("T nach 2 min trocken (°C)", "T_b"),
                             ("T Tuch aufgelegt (°C)", "T_c"), ("T nach 2 min Tuch (°C)", "T_d")])],
    background=[
        ("Zweck", """Die Lernenden prüfen die Alltagsvorstellung „Ein Ventilator oder Wind macht die Luft kälter“.
         Im trockenen Luftstrom bleibt die Temperatur gleich, mit feuchtem Tuch sinkt sie deutlich. So wird
         die Ersatzvorstellung aufgebaut: Kühl fühlt sich Wind an, weil er die Verdunstung (und den Wärmeabtransport)
         an der Haut beschleunigt – die Luft selbst wird nicht kälter."""),
        ("Fehlvorstellung", """„Bewegte Luft ist kälter als ruhende Luft.“ Alltagsvorstellung, im Buch nicht
         eigens aufgeführt (eigene Ergänzung im Konzeptpapier)."""),
        ("Physik", """Ein Ventilator bewegt die Luft, er entzieht ihr keine Energie. Sein Motor und die
         Luftreibung geben sogar etwas Wärme ab. Der Sensor hat (anders als die Haut) keine eigene Wärmequelle
         und ist trocken – er zeigt deshalb im Luftstrom die Lufttemperatur. Mit feuchtem Tuch verdunstet Wasser;
         die Verdampfungsenthalpie (rund 2,4 kJ pro Gramm) wird der Umgebung des Sensors entzogen. Der Sensor
         wirkt dann wie ein Feuchtthermometer (Psychrometer)."""),
        ("Erwartung", """Trocken: Änderung kleiner als etwa 0,3 K. Mit feuchtem Tuch: mehrere Kelvin Abkühlung,
         die relative Feuchte steigt deutlich."""),
        ("Hinweise", """Der Ventilator darf nicht von einer Heizung oder aus der Sonne warme Luft ansaugen.
         Tuch nur feucht, nicht tropfnass; das Silikongehäuse geschlossen lassen. Nach dem Versuch mini trocknen
         lassen. Bei warmer Hand vor dem Ablegen kurz warten, damit der Sensor nicht von der Hand erwärmt startet."""),
    ],
))

# ---------------------------------------------------------------------------
# E03 Lueften
# ---------------------------------------------------------------------------
AH = "6.112*exp(17.62*[1_]/(243.12+[1_]))*[2_]*2.1674/(273.15+[1_])"
AH1 = AH.replace("_", "")
EXPS.append(Exp(
    key="lueften", title="Feuchte Luft beim Lüften",
    description="Vortest, Experiment mit dem phyphox:mini (Temperatur, relative und absolute Luftfeuchtigkeit, "
                "CO₂ beim Stoßlüften oder im abgekühlten Glas) und Nachtest zur Vorstellung „Relative "
                "Luftfeuchtigkeit = Wassermenge in der Luft“.",
    items=[
        MC("lueften", "Draußen sind es 2 °C und es nieselt. Du lüftest 5 Minuten lang weit und heizt danach "
                      "wieder auf die alte Temperatur. Die relative Luftfeuchtigkeit im Zimmer ist dann …",
           [("höher als vorher", "relative Feuchte = Wassermenge; nasses Wetter bringt Feuchte herein"),
            ("niedriger als vorher", "R"), ("gleich wie vorher", "Lüften ändert nichts an der Feuchte")]),
        MC("glas", "Ein fest verschlossenes Glas mit Luft wird abgekühlt. Die relative Luftfeuchtigkeit im "
                   "Glas …",
           [("steigt", "R"), ("sinkt", "relative Feuchte folgt der Temperatur"),
            ("bleibt gleich, weil kein Wasser dazukommt", "relative Feuchte = Wassermenge")]),
        LK("kalt", "Kalte Luft enthält mehr Wasser als warme Luft.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("scheibe", "Im Winter beschlägt die Innenseite einer kalten Fensterscheibe. Warum?",
           [("Feuchtigkeit dringt von draußen durch das Glas.", "Feuchte kommt von außen"),
            ("Die Zimmerluft kühlt an der Scheibe ab und kann dort weniger Wasserdampf halten.", "R"),
            ("Kalte Luft enthält mehr Wasser.", "kalte Luft ist feuchter")], sicher=False),
        MC("erklaerung", "Was gibt die relative Luftfeuchtigkeit an?",
           [("wie viele Gramm Wasser in einem Kubikmeter Luft sind", "verwechselt mit absoluter Feuchte"),
            ("wie viel Prozent der bei dieser Temperatur höchstens möglichen Wasserdampfmenge in der Luft sind", "R"),
            ("wie nass sich die Luft anfühlt", "Alltagsbegriff")], sicher=False),
    ],
    pre_prediction=[
        I("Wähle zuerst, welche Variante du durchführst:"),
        DD("variante", [(1, "A: Stoßlüften im Zimmer (ca. 20 min)"), (2, "B: mini im verschlossenen Glas abkühlen (ca. 15 min)")],
           default=1),
        I("Variante A: Wie ist die relative Luftfeuchtigkeit, nachdem du gelüftet und das Zimmer wieder "
          "aufgewärmt hast, im Vergleich zu vorher?", visibility="var_a"),
        I("Variante B: Wie ändert sich die relative Luftfeuchtigkeit im Glas, wenn es abgekühlt wird?",
          visibility="var_b"),
    ],
    prediction=("Deine Vorhersage für die relative Luftfeuchtigkeit:",
                [("sie steigt", "A: Fehlvorstellung / B: erwartet"), ("sie bleibt gleich", "Fehlvorstellung"),
                 ("sie sinkt", "A: erwartet / B: Fehlvorstellung")]),
    containers=HDC_NOW_CONT + [
        c("variante", 1, init=1, group="_"), c("var_a"), c("var_b"), c("show_a"), c("show_b"),
        c("ah", 0), c("AH_now"), c("tc", 0), c("co2", 0), c("CO2_now")] +
        [c(n) for n in ("T_1", "H_1", "AH_1", "C_1", "T_2", "H_2", "AH_2", "C_2", "dH", "dAH", "dCO2")],
    inputs=ble_block([hdc_cfg(20), ("100c", "0128", "STCC4 an, Messintervall 40 x 100 ms = 4 s")],
                     HDC_OUT + [("100b", 0, None, "co2"), ("100b", 4, None, "tc")]),
    analysis=hdc_now() + [
        F("1-abs(sign([1]-1))", ["variante"], "var_a"),
        F("1-abs(sign([1]-2))", ["variante"], "var_b"),
        F("[1]*sign([2])", ["var_a", "vorhersage"], "show_a"),
        F("[1]*sign([2])", ["var_b", "vorhersage"], "show_b"),
        F(AH, ["temp", "hum"], "ah"),
        LAST("ah", "AH_now"), LAST("co2", "CO2_now"),
        F("[1]-[2]", ["H_2", "H_1"], "dH"), F("[1]-[2]", ["AH_2", "AH_1"], "dAH"),
        F("[1]-[2]", ["C_2", "C_1"], "dCO2")],
    intro=[I("Variante A braucht ein Zimmer mit Fenster an einem kalten Tag. Variante B braucht ein großes "
             "Schraubglas und kaltes Wasser oder eine kalte Fensterbank.")],
    body=[
        G("Temperatur", [("t", "temp")], ly="Temperatur", uy="°C"),
        G("Relative Luftfeuchtigkeit", [("t", "hum")], ly="rel. Feuchte", uy="%", scaleMinY="fixed",
          scaleMaxY="fixed", minY=0, maxY=100),
        G("Absolute Luftfeuchtigkeit (Wassermenge)", [("t", "ah")], ly="abs. Feuchte", uy="g/m³",
          scaleMinY="fixed", minY=0),
        G("CO₂", [("tc", "co2")], ly="CO₂", uy="ppm"),
        V("Temperatur", "T_now", "°C", prec=1),
        V("Relative Luftfeuchtigkeit", "H_now", "%", prec=1),
        V("Absolute Luftfeuchtigkeit", "AH_now", "g/m³", prec=2),
        V("CO₂", "CO2_now", "ppm", prec=0),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        S(), H("Schritt 2 – Ausgangszustand"),
        I("A: Das Fenster ist noch zu. Lass den mini 5 Minuten im Raum liegen (nicht in der Hand).",
          visibility="show_a"),
        I("B: Lege den mini in das Glas, schraube es dicht zu und lass es 5 Minuten bei Zimmertemperatur "
          "stehen. Prüfe, ob weiter Werte ankommen.", visibility="show_b"),
        mark("Ausgangszustand festhalten", [("T_now", "T_1"), ("H_now", "H_1"), ("AH_now", "AH_1"),
                                           ("CO2_now", "C_1")]),
        S(), H("Schritt 3 – Verändern"),
        I("A: Öffne das Fenster 5 Minuten weit (Stoßlüften), schließe es und warte etwa 10 Minuten, bis die "
          "Temperatur wieder ungefähr den Ausgangswert erreicht.", visibility="show_a"),
        I("B: Stelle das Glas in kaltes Wasser oder auf die kalte Fensterbank und warte etwa 10 Minuten. "
          "Das Glas bleibt dabei zu!", visibility="show_b"),
        mark("Endzustand festhalten", [("T_now", "T_2"), ("H_now", "H_2"), ("AH_now", "AH_2"), ("CO2_now", "C_2")]),
        V("Änderung der relativen Feuchte", "dH", "%", prec=1),
        V("Änderung der absoluten Feuchte", "dAH", "g/m³", prec=2),
        V("Änderung CO₂", "dCO2", "ppm", prec=0, visibility="show_a"),
        S(), I("Vergleiche die relative und die absolute Luftfeuchtigkeit: Hat sich die Wassermenge in der "
               "Luft so geändert wie die Prozentzahl? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("variante", "Variante (1 = Lüften, 2 = Glas)"), ("dH", "Änderung rel. Feuchte (%)"),
             ("dAH", "Änderung abs. Feuchte (g/m³)"), ("dCO2", "Änderung CO2 (ppm)"),
             ("T_1", "T Anfang (°C)"), ("T_2", "T Ende (°C)")],
    export_sets=[("Messung HDC", [("Zeit (s)", "t"), ("Temperatur (°C)", "temp"), ("Relative Feuchte (%)", "hum"),
                                  ("Absolute Feuchte (g/m³)", "ah")]),
                 ("Messung CO2", [("Zeit (s)", "tc"), ("CO2 (ppm)", "co2")]),
                 ("Marker", [("rel. Feuchte Anfang (%)", "H_1"), ("rel. Feuchte Ende (%)", "H_2"),
                             ("abs. Feuchte Anfang (g/m³)", "AH_1"), ("abs. Feuchte Ende (g/m³)", "AH_2"),
                             ("CO2 Anfang (ppm)", "C_1"), ("CO2 Ende (ppm)", "C_2")])],
    background=[
        ("Zweck", """Die Lernenden unterscheiden relative Luftfeuchtigkeit (Prozent der bei dieser Temperatur
         maximal möglichen Wasserdampfmenge) und absolute Feuchte (Gramm Wasser pro Kubikmeter). Das Experiment
         zeigt beide Größen nebeneinander; die absolute Feuchte wird aus Temperatur und relativer Feuchte
         berechnet (Magnus-Formel)."""),
        ("Fehlvorstellung", """Relative Feuchte wird mit der Wassermenge in der Luft gleichgesetzt; „Lüften bei
         Regenwetter holt Feuchtigkeit herein“; „Kalte Luft enthält mehr Wasser“. Alltagsvorstellung (eigene
         Ergänzung im Konzeptpapier)."""),
        ("Physik", """Kalte Außenluft (2 °C, 100 %) enthält nur etwa 5,6 g/m³ Wasser. Auf 20 °C erwärmt sind das
         nur noch rund 30 % relative Feuchte, denn bei 20 °C passen etwa 17,3 g/m³. Lüften senkt deshalb die
         relative Feuchte im Winter. Umgekehrt im Glas: Die Wassermenge bleibt konstant, die maximal mögliche
         sinkt mit der Temperatur – die relative Feuchte steigt."""),
        ("Erwartung", """A: rel. Feuchte nach dem Wiederaufwärmen niedriger, absolute Feuchte niedriger, CO₂ fällt
         deutlich. B: rel. Feuchte steigt beim Abkühlen (pro Kelvin grob 6 % ihres Werts), absolute Feuchte
         bleibt etwa gleich."""),
        ("Hinweise", """Dauert 15–20 Minuten und ist wetterabhängig, eher als Hausexperiment geeignet. In
         Variante B die Funkverbindung durch Glas und Wasser vorher prüfen. Der HDC1080 misst die Luft im Gehäuse,
         er reagiert träge. Formel für die absolute Feuchte: AH = 6,112 hPa · exp(17,62·T/(243,12 °C+T)) · RH ·
         2,1674 / (273,15+T), Ergebnis in g/m³."""),
    ],
))

# ---------------------------------------------------------------------------
# E04 Schmelzen
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="schmelzen", title="Wärme rein, Temperatur gleich?",
    description="Vortest, Experiment mit dem phyphox:mini (Temperatur in Eiswasser, während das Eis schmilzt) "
                "und Nachtest zur Vorstellung „Wärmezufuhr führt immer zu einer Temperaturerhöhung“.",
    items=[
        MC("eiswasser", "Ein Glas mit Eiswasser steht in einem warmen Zimmer. Solange noch Eis im Wasser "
                        "schwimmt, …",
           [("steigt die Temperatur langsam", "Wärmezufuhr = Temperaturanstieg"),
            ("bleibt die Temperatur gleich", "R"), ("sinkt die Temperatur", "Eis „gibt Kälte ab“")]),
        MC("energie", "Wohin geht die Energie, die das Eiswasser aus dem warmen Zimmer aufnimmt?",
           [("Sie erhöht die Temperatur.", "Wärmezufuhr = Temperaturanstieg"),
            ("Sie schmilzt das Eis.", "R"), ("Sie geht verloren.", "Energie geht verloren")]),
        LK("immer", "Wenn man einem Körper Wärme zuführt, wird er immer wärmer.",
           "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("kochen", "Wasser kocht auf dem Herd. Du drehst von voller auf halbe Leistung, es kocht aber "
                     "weiter. Die Temperatur des Wassers …",
           [("sinkt deutlich", "Temperatur = zugeführte Leistung"), ("bleibt bei etwa 100 °C", "R"),
            ("steigt weiter an", "Wärmezufuhr = Temperaturanstieg")], sicher=False),
        MC("erklaerung", "Warum blieb die Temperatur im Experiment nahe 0 °C, solange noch Eis da war?",
           [("Das Eis gibt Kälte ab, die die Wärme aufhebt.", "Kälte als eigener Stoff"),
            ("Die zugeführte Energie wird zum Schmelzen des Eises gebraucht.", "R"),
            ("Solange Eis da ist, kommt keine Wärme ins Glas.", "keine Wärmezufuhr")], sicher=False),
    ],
    prediction=("Das Glas mit viel Eis steht im warmen Zimmer, das ständig Wärme liefert. Was passiert mit "
                "der Temperatur am mini, solange noch Eis da ist?",
                [("sie steigt langsam und gleichmäßig", "Wärmezufuhr = Temperaturanstieg"),
                 ("sie bleibt nahe 0 °C, bis das Eis geschmolzen ist", "R"),
                 ("sie sinkt immer weiter", "Eis gibt Kälte ab")]),
    containers=HDC_NOW_CONT + [c(n) for n in ("t_start", "T_plateau", "t_melt", "T_melt", "T_end",
                                                "t_dauer", "dT_nach")],
    inputs=ble_block([hdc_cfg(20)], HDC_OUT),
    analysis=hdc_now() + [F("[1]-[2]", ["t_melt", "t_start"], "t_dauer"),
                          F("[1]-[2]", ["T_end", "T_melt"], "dT_nach")],
    intro=[I("Du brauchst ein Glas, viel zerstoßenes Eis, wenig Wasser und einen dichten Gefrierbeutel "
             "(Zip-Beutel). Der mini kommt in den Beutel, die Luft möglichst herausdrücken, gut verschließen.")],
    body=[
        G("Temperatur", [("t", "temp")], ly="Temperatur", uy="°C", scaleMinY="fixed", scaleMaxY="fixed",
          minY=-5, maxY=25),
        V("Temperatur jetzt", "T_now", "°C"),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        S(), H("Schritt 2 – mini ins Eiswasser"),
        I("Drücke den Beutel mit dem mini tief zwischen das Eis, sodass er rundum bedeckt ist. Tippe dann:"),
        mark("mini ist im Eiswasser", [("t_now", "t_start")]),
        I("Warte, bis die Temperatur nicht mehr fällt (einige Minuten). Solange noch Eis schwimmt, tippe:"),
        mark("Es ist noch Eis da – Wert festhalten", [("T_now", "T_plateau")]),
        V("Temperatur, solange Eis da ist", "T_plateau", "°C"),
        S(), H("Schritt 3 – Eis geschmolzen"),
        I("Lass das Glas stehen. Rühre ab und zu vorsichtig um. Sobald das letzte Eis geschmolzen ist, tippe:"),
        mark("Das Eis ist ganz geschmolzen", [("t_now", "t_melt"), ("T_now", "T_melt")]),
        V("Dauer, bis das Eis geschmolzen war", "t_dauer", "s", prec=0),
        I("Miss danach noch etwa 10 Minuten weiter und tippe dann:"),
        mark("10 Minuten nach dem Schmelzen", [("T_now", "T_end")]),
        V("Anstieg in den 10 Minuten nach dem Schmelzen", "dT_nach", "K"),
        S(), I("Wann stieg die Temperatur – während des Schmelzens oder danach? Woher kam in beiden Phasen die "
               "Energie? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("T_plateau", "Temperatur mit Eis (°C)"), ("t_dauer", "Dauer bis geschmolzen (s)"),
             ("dT_nach", "Anstieg nach dem Schmelzen (K)")],
    export_sets=[("Messung", [("Zeit (s)", "t"), ("Temperatur (°C)", "temp"), ("Relative Feuchte (%)", "hum")]),
                 ("Marker", [("Start im Eiswasser (s)", "t_start"), ("Eis geschmolzen (s)", "t_melt"),
                             ("T geschmolzen (°C)", "T_melt"), ("T 10 min später (°C)", "T_end")])],
    background=[
        ("Zweck", """Die Lernenden sehen, dass Wärmezufuhr nicht automatisch die Temperatur erhöht: Beim
         Schmelzen fließt Energie aus dem Zimmer ins Glas, die Temperatur bleibt aber nahe 0 °C, bis das Eis
         geschmolzen ist. Erst danach steigt sie."""),
        ("Fehlvorstellung", """„Wärmezufuhr führt immer zu einer Temperaturerhöhung“ (Schecker u. a. 2018,
         S. 174). Verwandt: Wärme und Temperatur werden nicht unterschieden; Kälte als eigener Stoff."""),
        ("Physik", """Zum Schmelzen von 1 g Eis braucht man rund 334 J (Schmelzwärme) – so viel, wie 1 g Wasser
         um etwa 80 K erwärmt. Solange Eis und Wasser im Gleichgewicht sind, bleibt die Temperatur bei 0 °C."""),
        ("Erwartung", """Nach dem Eintauchen fällt die Temperatur auf etwa 0 bis 2 °C (der Beutel und die Luft
         darin isolieren etwas) und bleibt dort, solange Eis da ist. Danach steigt sie langsam in Richtung
         Zimmertemperatur."""),
        ("Hinweise", """Machbarkeit zuerst testen: Der Sensor misst die Luft im Beutel, die Angleichung ist
         träge. Beutel wirklich dicht, sonst Wasser am mini. Kondenswasser im Beutel kann die Feuchtemessung
         sättigen. Dauer je nach Eismenge 30–90 Minuten – wenig Eis und ein kleines Glas verkürzen den Versuch.
         Funkverbindung durch Wasser vorher prüfen (mini möglichst nah an der Oberfläche)."""),
    ],
))

# ---------------------------------------------------------------------------
# E05 Luft hat Gewicht
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="luft_gewicht", title="Hat Luft ein Gewicht?",
    description="Vortest, Experiment mit dem phyphox:mini (Luftdruck unten und zwei Stockwerke höher, daraus "
                "Masse der Luftsäule und Luftdichte) und Nachtest zur Vorstellung „Luft ist nichts / wiegt nichts“.",
    items=[
        MC("ball", "Ein Fußball wird prall aufgepumpt. Im Vergleich zum schlaffen Ball ist er …",
           [("leichter", "Luft hat negatives Gewicht / zieht nach oben"), ("gleich schwer", "Luft wiegt nichts"),
            ("schwerer", "R")]),
        MC("berg", "Auf einem hohen Berg ist der Luftdruck …",
           [("höher als im Tal", "näher an der Sonne / mehr Wind"), ("gleich wie im Tal", "Luftdruck überall gleich"),
            ("niedriger als im Tal", "R")]),
        LK("nichts", "Luft wiegt nichts.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("hochhaus", "Warum sinkt der Luftdruck, wenn man im Hochhaus nach oben fährt?",
           [("Über einem liegt weniger Luft.", "R"),
            ("Die Luft ist oben dünner, weil sie kälter ist.", "Temperatur statt Gewicht"),
            ("Die Schwerkraft ist oben deutlich schwächer.", "Schwerkraft-Erklärung")], sicher=False),
        MC("erklaerung", "Was zeigt die Rechnung „Masse der Luft pro Quadratmeter“ im Experiment?",
           [("Die Luft zwischen den Stockwerken hat eine Masse und drückt mit ihrem Gewicht nach unten.", "R"),
            ("Nichts – der Druckunterschied kommt nur vom Treppensteigen.", "Wegerklären"),
            ("Dass Luft nur in Bewegung etwas wiegt.", "Luft wiegt nur als Wind")], sicher=False),
    ],
    prediction=("Was zeigt der Drucksensor zwei Stockwerke höher im Vergleich zu unten?",
                [("mehr", "Druck nimmt nach oben zu"), ("etwa gleich viel", "Luft wiegt nichts"),
                 ("weniger", "R")]),
    containers=bmp_containers(40) + [c("p_first"), c("h", 0), c("p_unten"), c("p_oben"), c("p_unten2"), c("dp"),
                                     c("dp2"), c("dh"), c("m_luft"), c("h_stock", 1, init=6, group="_"), c("rho")],
    inputs=ble_block([bmp_cfg(5, 2)], bmp_out(), mtu=180),
    analysis=bmp_analysis() + [
        FIRST("p", "p_first"),
        F("([1]-[2_])*8.43", ["p_first", "p"], "h"),
        F("[1]-[2]", ["p_oben", "p_unten"], "dp"),
        F("[1]-[2]", ["p_unten2", "p_oben"], "dp2"),
        F("-[1]*8.43", ["dp"], "dh"),
        F("abs([1])*100/9.81", ["dp"], "m_luft"),
        F("[1]/[2]", ["m_luft", "h_stock"], "rho")],
    intro=[I("Du brauchst ein Treppenhaus mit mindestens zwei Stockwerken. Halte den mini ruhig in der Hand "
             "oder in der Hosentasche; das Smartphone nimmst du mit.")],
    body=[
        G("Luftdruck", [("tp", "p")], ly="Luftdruck", uy="hPa", suppressScientificNotation=True, yPrecision=2),
        G("Höhe aus dem Luftdruck (relativ zum Start)", [("tp", "h")], ly="Höhe", uy="m"),
        V("Luftdruck (Mittel der letzten Werte)", "p_avg", "hPa", prec=2),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        S(), H("Schritt 2 – Unten"),
        I("Stell dich unten ins Treppenhaus und warte 30 Sekunden ruhig. Tippe dann:"),
        B("Unten: Druck festhalten", [("p_avg", "p_unten"), ("tp_now", "t_mark")]),
        S(), H("Schritt 3 – Oben"),
        I("Geh zügig zwei Stockwerke nach oben. Warte dort 30 Sekunden ruhig und tippe dann:"),
        B("Oben: Druck festhalten", [("p_avg", "p_oben"), ("tp_now", "t_mark")]),
        V("Druckunterschied oben – unten", "dp", "hPa", prec=2),
        V("Höhenunterschied (aus dem Druck)", "dh", "m", prec=1),
        S(), H("Schritt 4 – Wieder unten (Kontrolle)"),
        I("Geh wieder hinunter, warte 30 Sekunden und tippe. Der Druck sollte um denselben Betrag steigen."),
        B("Wieder unten: Druck festhalten", [("p_avg", "p_unten2"), ("tp_now", "t_mark")]),
        V("Druckanstieg beim Hinuntergehen", "dp2", "hPa", prec=2),
        S(), H("Schritt 5 – Wie schwer ist die Luft?"),
        I("Der Druckunterschied entsteht durch das Gewicht der Luft zwischen unten und oben. 1 hPa = 100 N pro "
          "Quadratmeter. Daraus folgt die Masse der Luft über jedem Quadratmeter Boden:"),
        V("Masse der Luftschicht pro m²", "m_luft", "kg", prec=1),
        I("Gib die Höhe zwischen den beiden Messorten ein (zwei Stockwerke sind etwa 6 m), dann erhältst du, "
          "wie viel ein Kubikmeter Luft wiegt:"),
        E("Höhenunterschied", "h_stock", "m", default=6, signed=False),
        V("Masse von 1 m³ Luft (Dichte)", "rho", "kg/m³", prec=2),
        S(), I("Zum Vergleich: Ein Klassenzimmer enthält etwa 200 m³ Luft. Wie schwer ist diese Luft? Weiter zum "
               "Reiter „3 Nachtest“."),
    ],
    results=[("dp", "Druckunterschied oben-unten (hPa)"), ("dp2", "Druckanstieg zurück unten (hPa)"),
             ("m_luft", "Masse Luft pro m2 (kg)"), ("rho", "Luftdichte (kg/m3)"), ("h_stock", "Eingegebene Höhe (m)")],
    export_sets=[("Messung", [("Zeit (s)", "tp"), ("Druck (hPa)", "p"), ("Temperatur BMP (°C)", "Tb"),
                              ("Höhe relativ (m)", "h")]),
                 ("Marker", [("p unten (hPa)", "p_unten"), ("p oben (hPa)", "p_oben"),
                             ("p wieder unten (hPa)", "p_unten2")])],
    background=[
        ("Zweck", """Die Lernenden messen, dass der Luftdruck zwei Stockwerke höher kleiner ist, und deuten das
         als Gewicht der Luftschicht dazwischen. Der zweite Schritt rechnet den Druckunterschied in die Masse der
         Luft pro Quadratmeter und in die Luftdichte um (rund 1,2 kg/m³) – so wird „Luft hat Masse“ greifbar."""),
        ("Fehlvorstellung", """„Luft ist nichts“; Luft hat kein oder sogar ein negatives Gewicht (Schecker u. a.
         2018, S. 249)."""),
        ("Physik", """Hydrostatischer Druck: Δp = ρ·g·Δh. Mit ρ = 1,2 kg/m³ sinkt der Druck um etwa 0,12 hPa pro
         Meter, also rund 8,4 m pro hPa. Zwei Stockwerke (6 m) ergeben etwa 0,7 hPa. Die Masse der Luftsäule pro
         Fläche ist m/A = Δp/g."""),
        ("Erwartung", """Oben etwa 0,6–0,8 hPa weniger, beim Zurückgehen gleich viel mehr. Luftdichte aus der
         Messung etwa 1,1–1,3 kg/m³ (abhängig von der eingegebenen Höhe)."""),
        ("Hinweise", """Wetterbedingte Druckänderungen (bis etwa 1 hPa pro Stunde) und Zugluft im Treppenhaus
         stören. Deshalb zügig messen; der Rückweg dient als Kontrolle. Den mini nicht in der warmen Hand
         umklammern (Temperaturdrift). Der Sensor läuft mit 32-fachem Oversampling und IIR-Filter, der angezeigte
         Druck ist zusätzlich über die letzten 40 Werte gemittelt."""),
    ],
))

# ---------------------------------------------------------------------------
# E06 Luft erwaermen
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="luft_erwaermen", title="Erwärmte Luft: steigt sie nur auf?",
    description="Vortest, Experiment mit dem phyphox:mini (Druck und Temperatur in einem verschlossenen Glas im "
                "warmen und kalten Wasserbad) und Nachtest zur Vorstellung „Warme Luft steigt nur auf“.",
    items=[
        MC("flasche", "Eine verschlossene Flasche mit Luft wird erwärmt. Die Luft in der Flasche …",
           [("sammelt sich oben", "warme Luft steigt nur auf"), ("drückt stärker gegen alle Wände", "R"),
            ("verändert sich nicht", "Luft ändert sich beim Erwärmen nicht")]),
        MC("ballon", "Über eine leere Flasche wird ein Luftballon gestülpt. Die Flasche kommt in heißes Wasser, "
                     "der Ballon bläht sich auf. Ist unten in der Flasche jetzt noch Luft?",
           [("ja, die Luft ist überall in der Flasche", "R"),
            ("nein, die Luft ist nach oben in den Ballon gestiegen", "warme Luft steigt nur auf")]),
        LK("platz", "Warme Luft nimmt genauso viel Platz ein wie kalte Luft.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("reifen", "Ein Fahrradreifen liegt im Sommer in der prallen Sonne und wird heiß. Der Druck im "
                     "Reifen …",
           [("steigt", "R"), ("bleibt gleich", "Erwärmen ändert die Luft nicht"),
            ("sinkt, weil die warme Luft nach oben steigt", "warme Luft steigt nur auf")], sicher=False),
        MC("erklaerung", "Warum stieg der Druck im Glas?",
           [("Die warme Luft stieg nach oben zum Sensor.", "warme Luft steigt nur auf"),
            ("Die Luftteilchen bewegen sich schneller und stoßen stärker gegen alle Wände.", "R"),
            ("Das warme Wasser drückt von außen auf das Glas.", "Ausweicherklärung")], sicher=False),
    ],
    prediction=("Was passiert mit dem Druck im geschlossenen Glas, wenn es in warmes Wasser gestellt wird?",
                [("er steigt", "R"), ("er bleibt gleich", "Luft ändert sich nicht"),
                 ("er sinkt", "Luft steigt weg / wird dünner")]),
    containers=bmp_containers(40) + [c(n) for n in ("p0", "T0", "p1", "T1", "p2", "T2", "dp_warm", "dp_kalt",
                                                     "p1_erw", "dp_erw")],
    inputs=ble_block([bmp_cfg(5, 1)], bmp_out(), mtu=180),
    analysis=bmp_analysis() + [
        F("[1]-[2]", ["p1", "p0"], "dp_warm"), F("[1]-[2]", ["p2", "p0"], "dp_kalt"),
        F("[1]*(273.15+[2])/(273.15+[3])", ["p0", "T1", "T0"], "p1_erw"),
        F("[1]-[2]", ["p1_erw", "p0"], "dp_erw")],
    intro=[I("Du brauchst ein dicht schließendes Schraubglas, eine Schüssel mit warmem Wasser (etwa 40 °C, "
             "nicht heißer) und eine mit kaltem Wasser. Der mini kommt in das trockene Glas.")],
    body=[
        G("Druck im Glas", [("tp", "p")], ly="Druck", uy="hPa", suppressScientificNotation=True),
        G("Temperatur im Glas", [("tp", "Tb")], ly="Temperatur", uy="°C"),
        G("Druck über Temperatur", [("Tb", "p")], lx="Temperatur", ux="°C", ly="Druck", uy="hPa",
          style="dots", partialUpdate=False, suppressScientificNotation=True),
        V("Druck", "p_avg", "hPa", prec=1), V("Temperatur", "Tb_avg", "°C", prec=1),
        V("Zeit seit dem letzten Knopfdruck", "t_since", "s", prec=0),
        S(), H("Schritt 2 – Glas verschließen"),
        I("Lege den mini ins Glas, schraube es fest zu und warte eine Minute. Tippe dann:"),
        B("Glas zu: Anfangswerte festhalten", [("p_avg", "p0"), ("Tb_avg", "T0"), ("tp_now", "t_mark")]),
        S(), H("Schritt 3 – Warmes Wasserbad"),
        I("Stelle das Glas für etwa 3 Minuten bis zum Deckel in das warme Wasser. Tippe dann:"),
        B("Nach 3 Minuten warm: festhalten", [("p_avg", "p1"), ("Tb_avg", "T1"), ("tp_now", "t_mark")]),
        V("Druckänderung im warmen Wasser", "dp_warm", "hPa", prec=1),
        S(), H("Schritt 4 – Kaltes Wasserbad"),
        I("Stelle das Glas jetzt für 3 Minuten in das kalte Wasser und tippe dann:"),
        B("Nach 3 Minuten kalt: festhalten", [("p_avg", "p2"), ("Tb_avg", "T2"), ("tp_now", "t_mark")]),
        V("Druckänderung gegenüber dem Anfang", "dp_kalt", "hPa", prec=1),
        S(), H("Schritt 5 – Vergleich mit der Rechnung"),
        I("Wenn die Luftteilchen bei höherer Temperatur stärker gegen alle Wände stoßen, wächst der Druck "
          "proportional zur absoluten Temperatur (in Kelvin). Erwartet wäre dann:"),
        V("Erwartete Druckänderung (aus der Temperatur)", "dp_erw", "hPa", prec=1),
        I("Vergleiche mit der gemessenen Änderung. Der Sensor liegt unten im Glas – trotzdem steigt der Druck. "
          "Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("dp_warm", "Druckänderung warm (hPa)"), ("dp_kalt", "Druckänderung kalt (hPa)"),
             ("dp_erw", "Erwartete Änderung (hPa)"), ("T0", "T Anfang (°C)"), ("T1", "T warm (°C)")],
    export_sets=[("Messung", [("Zeit (s)", "tp"), ("Druck (hPa)", "p"), ("Temperatur (°C)", "Tb")]),
                 ("Marker", [("p Anfang (hPa)", "p0"), ("T Anfang (°C)", "T0"), ("p warm (hPa)", "p1"),
                             ("T warm (°C)", "T1"), ("p kalt (hPa)", "p2"), ("T kalt (°C)", "T2")])],
    background=[
        ("Zweck", """„Warme Luft steigt auf“ ist eine richtige Beobachtung, wird aber oft als einzige Wirkung des
         Erwärmens verstanden. Im geschlossenen Glas kann die Luft nicht aufsteigen oder sich ausdehnen – stattdessen
         steigt der Druck, und zwar auch am Boden des Glases. Der Vergleich mit dem Gesetz von Gay-Lussac liefert
         die Teilchen-Erklärung als Ersatzvorstellung."""),
        ("Fehlvorstellung", """„Warme Luft steigt auf“; Lernende erwarten, dass sich Volumen, Dichte und Druck beim
         Erwärmen nicht ändern (Schecker u. a. 2018, S. 250)."""),
        ("Physik", """Bei konstantem Volumen gilt p/T = konstant (T in Kelvin). Von 20 °C auf 40 °C steigt der
         Druck um den Faktor 313/293 ≈ 1,07, also um etwa 70 hPa."""),
        ("Erwartung", """Druck steigt im warmen Bad um einige zehn hPa und fällt im kalten wieder. Die gemessene
         Änderung liegt meist etwas unter der Rechnung, weil der Sensor (im Gehäuse) etwas schneller warm wird als
         die gesamte Luft im Glas, oder weil der Deckel nicht ganz dicht ist."""),
        ("Hinweise", """Glas muss dicht sein (Gummidichtung). Nicht über etwa 50 °C erwärmen (Knopfzelle, Druck
         auf den Deckel). Funkverbindung durch Glas und Wasser vorher prüfen. Die Temperatur stammt vom BMP581
         selbst und folgt der Lufttemperatur träge."""),
    ],
))

# ---------------------------------------------------------------------------
# E07 Ruhende Luft drueckt
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="luft_drueckt", title="Drückt ruhende Luft?",
    description="Vortest, Experiment mit dem phyphox:mini (Luftdruck in verschiedenen Lagen und in einem "
                "zusammengedrückten Beutel) und Nachtest zur Vorstellung „Unbewegte Luft drückt nicht“.",
    items=[
        MC("papier", "Ein Blatt Papier liegt auf dem Tisch. Die Luft drückt auf das Papier …",
           [("nur von oben", "Luftdruck wirkt nur nach unten"), ("von allen Seiten gleich stark", "R"),
            ("gar nicht, weil sie sich nicht bewegt", "ruhende Luft tut nichts")]),
        MC("strohhalm", "Beim Trinken mit dem Strohhalm steigt der Saft nach oben, weil …",
           [("man ihn hochsaugt", "Vakuum saugt"), ("die Luft außen auf den Saft drückt und ihn hochschiebt", "R")]),
        LK("bewegt", "Luft kann nur dann drücken, wenn sie sich bewegt.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("karton", "Du saugst die Luft aus einem leeren Getränkekarton und er knickt zusammen. Warum?",
           [("Das Saugen zieht die Wände nach innen.", "Vakuum saugt"),
            ("Die Luft außen drückt stärker als die wenige Luft innen.", "R"),
            ("Die Pappe wird beim Saugen weich.", "Ausweicherklärung")], sicher=False),
        MC("erklaerung", "Warum zeigte der Sensor in jeder Lage denselben Druck?",
           [("Ruhende Luft drückt von allen Seiten gleich stark.", "R"),
            ("Ruhende Luft drückt gar nicht, deshalb ändert sich nichts.", "ruhende Luft tut nichts"),
            ("Der Sensor misst nur den Druck von oben.", "Ausweicherklärung")], sicher=False),
    ],
    prediction=("Ändert sich der angezeigte Druck, wenn du den mini langsam in verschiedene Lagen drehst?",
                [("ja, mit der Oberseite nach oben ist er am größten", "Luftdruck wirkt nur nach unten"),
                 ("nein, er bleibt gleich", "R"),
                 ("ja, mit der Oberseite nach unten ist er am größten", "Druck wirkt nur von unten"),
                 ("es gibt gar keinen Druck, die Luft bewegt sich ja nicht", "ruhende Luft tut nichts")]),
    containers=bmp_containers(40) + acc_containers() + [
        c("p_first"), c("p_rel", 0), c("p_win10", 120), c("p_max10"), c("p_min10"), c("dp10"),
        c("az_win", 26), c("a_win", 26), c("az_avg"), c("a_avg"), c("lage"),
        c("dp_drehen"), c("p_ref_b"), c("dp_beutel_now"), c("dp_beutel")],
    inputs=ble_block([bmp_cfg(5, 1), lsm_cfg(0x01, 0x02, 0x01, 0x00, 5)], bmp_out() + acc_out(), mtu=247),
    analysis=bmp_analysis() + [
        APP("p_raw", "p_win10", keep=True, append=True)] + acc_analysis(win=["a_win"]) + [
        APP("az", "az_win", keep=True), AVG("az_win", "az_avg"), AVG("a_win", "a_avg"),
        F("[1]/[2]", ["az_avg", "a_avg"], "lage"),
        FIRST("p", "p_first"), F("[2_]-[1]", ["p_first", "p"], "p_rel"),
        MAX("p_win10", "p_max10"), MIN("p_win10", "p_min10"), F("[1]-[2]", ["p_max10", "p_min10"], "dp10"),
        F("[1]-[2]", ["p_avg", "p_ref_b"], "dp_beutel_now")],
    intro=[I("Du brauchst einen Gefrierbeutel mit Zip-Verschluss, in den der mini mit etwas Luft passt.")],
    body=[
        G("Druck relativ zum Start", [("tp", "p_rel")], ly="Druckänderung", uy="hPa", scaleMinY="fixed",
          scaleMaxY="fixed", minY=-1, maxY=1),
        V("Druck", "p_avg", "hPa", prec=2),
        V("Lage des mini", "lage", maps=[(0.7, None, "Oberseite zeigt nach oben"),
                                         (None, -0.7, "Oberseite zeigt nach unten"),
                                         (None, None, "steht hochkant / schräg")]),
        S(), H("Schritt 2 – Drehen"),
        I("Halte den mini mit zwei Fingern am Rand und drehe ihn langsam: Oberseite nach oben, zur Seite, nach "
          "unten. Halte jede Lage einige Sekunden. Das dauert etwa 10 Sekunden. Danach tippe:"),
        V("Größter Druckunterschied der letzten Sekunden", "dp10", "hPa", prec=2),
        B("Druckunterschied beim Drehen festhalten", [("dp10", "dp_drehen"), ("tp_now", "t_mark")]),
        V("Festgehaltener Unterschied beim Drehen", "dp_drehen", "hPa", prec=2),
        S(), H("Schritt 3 – Beutel zusammendrücken"),
        I("Lege den mini mit etwas Luft in den Beutel und verschließe ihn. Die Luft im Beutel strömt nicht. "
          "Tippe, solange der Beutel locker liegt:"),
        B("Beutel liegt locker: Bezugswert", [("p_avg", "p_ref_b"), ("tp_now", "t_mark")]),
        I("Drücke den Beutel jetzt mit beiden Händen zusammen (ohne den mini zu quetschen) und halte den Druck:"),
        V("Druckänderung im Beutel", "dp_beutel_now", "hPa", prec=1, size=1.5),
        B("Beim Drücken festhalten", [("dp_beutel_now", "dp_beutel")]),
        G("Druckänderung im Beutel (automatisch skaliert)", [("tp", "p_rel")], ly="Druckänderung", uy="hPa"),
        S(), I("Die Luft im Beutel bewegt sich kaum und drückt trotzdem stärker. In welche Richtung drückt sie? "
               "Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("dp_drehen", "Druckunterschied beim Drehen (hPa)"), ("dp_beutel", "Druckanstieg im Beutel (hPa)")],
    export_sets=[("Messung Druck", [("Zeit (s)", "tp"), ("Druck (hPa)", "p"), ("Druck relativ (hPa)", "p_rel")]),
                 ("Messung Lage", [("Zeit (s)", "ta"), ("a_z (m/s²)", "az"), ("|a| (m/s²)", "a_abs")])],
    background=[
        ("Zweck", """Die Lernenden prüfen, ob der Luftdruck von der Richtung abhängt und ob ruhende Luft überhaupt
         drückt. Beim Drehen bleibt der Druck gleich (allseitig), im zusammengedrückten Beutel steigt er, obwohl
         die Luft nicht strömt. Ersatzvorstellung: Luft drückt immer und von allen Seiten; „Saugen“ heißt, dass
         außen mehr Druck herrscht als innen."""),
        ("Fehlvorstellung", """„Luft drückt nach vorne, Vakuum saugt“; unbewegte Luft „tut nichts“, Luftdruck wirkt
         nicht allseitig (Schecker u. a. 2018, S. 250)."""),
        ("Physik", """Der Druck in einem ruhenden Gas ist in einem Punkt in alle Richtungen gleich (Pascal). Beim
         Drehen ändert sich nur die Höhe um wenige Zentimeter, also weniger als 0,01 hPa. Im Beutel wird das
         Volumen verkleinert: p·V = konstant, wenige Prozent Volumenänderung ergeben einige zehn hPa."""),
        ("Erwartung", """Drehen: Unterschied unter etwa 0,05 hPa (Sensorrauschen). Beutel: deutlicher Anstieg,
         je nach Kraft 5 bis über 50 hPa."""),
        ("Hinweise", """Wenig überraschend, eher für jüngere Lernende. Die Strohhalm-Frage wird nur indirekt
         gestützt. Die Lageanzeige nutzt die z-Achse des Beschleunigungssensors; welche Seite des mini als
         „Oberseite“ gilt, vor dem Einsatz prüfen und ggf. in der Anleitung benennen. Beim Halten keine warme Hand
         um den Sensor legen (Temperaturdrift)."""),
    ],
))

# ---------------------------------------------------------------------------
# E08 Tisch uebt Kraft aus
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="tisch_kraft", title="Übt der Tisch eine Kraft aus?",
    description="Vortest, Experiment mit dem phyphox:mini (Beschleunigungssensor als Fühler für Berührkräfte: "
                "auf dem Tisch, auf der Hand, im Fall) und Nachtest zur Vorstellung „Passive Körper üben keine "
                "Kraft aus“.",
    items=[
        MC("buch", "Ein Buch liegt ruhig auf dem Tisch. Welche Kräfte wirken auf das Buch?",
           [("nur die Schwerkraft", "passive Körper üben keine Kraft aus"),
            ("die Schwerkraft und eine Kraft vom Tisch nach oben", "R"),
            ("keine, es bewegt sich ja nicht", "Kraft nur bei Bewegung")]),
        MC("hand", "Du hältst das Buch auf der flachen Hand statt auf dem Tisch. Wer übt eine Kraft nach oben "
                   "auf das Buch aus?",
           [("die Hand und vorher auch der Tisch", "R"), ("nur die Hand, der Tisch nicht", "nur aktive Körper üben Kräfte aus"),
            ("keiner von beiden", "Kraft nur bei Bewegung")]),
        LK("tisch", "Ein Tisch kann keine Kraft ausüben, er ist nur im Weg.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("auto", "Ein Auto fährt an. Wer übt die Kraft aus, die das Auto nach vorne beschleunigt?",
           [("der Motor", "nur aktive Körper üben Kräfte aus"), ("die Straße (über die Reifen)", "R"),
            ("niemand, das Auto beschleunigt sich selbst", "Kraft als innere Eigenschaft")], sicher=False),
        MC("erklaerung", "Warum zeigte der Sensor während des Falls etwa 0?",
           [("Im Fall wirkt keine Schwerkraft.", "neue Fehlvorstellung: keine Schwerkraft im Fall"),
            ("Nichts berührt den mini, also drückt ihn auch nichts.", "R"),
            ("Der Sensor ist beim Fallen zu langsam.", "Wegerklären")], sicher=False),
    ],
    prediction=("Was zeigt der Sensor, wenn der mini ruhig auf dem Tisch liegt?",
                [("etwa 0, weil sich nichts bewegt", "passive Körper üben keine Kraft aus"),
                 ("etwa 9,8 m/s², nach oben gerichtet", "R"),
                 ("etwa 9,8 m/s², nach unten gerichtet", "Sensor misst die Schwerkraft")]),
    containers=acc_containers() + [c("a_win", 52), c("az_win", 52), c("a_win3", 312), c("a_avg"), c("az_avg"),
                                   c("a_min3"), c("a_tisch"), c("a_hand"), c("a_fall")],
    inputs=ble_block([lsm_cfg(0x01, 0x04, 0x01, 0x00, 10)], acc_out(), mtu=247),
    analysis=acc_analysis(win=["a_win", "a_win3"]) + [
        APP("az", "az_win", keep=True), AVG("a_win", "a_avg"), AVG("az_win", "az_avg"), MIN("a_win3", "a_min3")],
    intro=[I(SENSOR_INTRO, bold=False)],
    body=[
        G("Betrag der gemessenen Beschleunigung", [("ta", "a_abs")], ly="|a|", uy="m/s²", scaleMinY="fixed",
          scaleMaxY="fixed", minY=0, maxY=20),
        V("Sensor zeigt", "a_avg", "m/s²", prec=1, size=2),
        V("Richtung (z-Achse)", "az_avg", positiveUnit="m/s², zur Oberseite des mini",
          negativeUnit="m/s², zur Unterseite des mini", prec=1),
        S(), H("Schritt 2 – Auf dem Tisch"),
        I("Lege den mini mit der Oberseite nach oben ruhig auf den Tisch und tippe:"),
        B("Wert auf dem Tisch festhalten", [("a_avg", "a_tisch")]),
        V("Auf dem Tisch", "a_tisch", "m/s²", prec=2),
        S(), H("Schritt 3 – Auf der flachen Hand"),
        I("Lege den mini auf deine flache, ruhige Hand und tippe:"),
        B("Wert auf der Hand festhalten", [("a_avg", "a_hand")]),
        V("Auf der Hand", "a_hand", "m/s²", prec=2),
        S(), H("Schritt 4 – Ohne Unterlage"),
        I("Halte den mini auf der flachen Hand über ein Kissen und ziehe die Hand schnell nach unten weg (oder "
          "lass ihn aus 30 cm auf das Kissen fallen). Tippe innerhalb von 3 Sekunden:"),
        V("Kleinster Wert der letzten 3 s", "a_min3", "m/s²", prec=2),
        B("Kleinsten Wert festhalten", [("a_min3", "a_fall")]),
        V("Ohne Unterlage (im Fall)", "a_fall", "m/s²", prec=2),
        S(), I("Tisch und Hand zeigen dasselbe. Was macht der Tisch also mit dem mini? Und was fehlt, wenn die "
               "Unterlage weg ist? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("a_tisch", "Wert auf dem Tisch (m/s2)"), ("a_hand", "Wert auf der Hand (m/s2)"),
             ("a_fall", "Wert im Fall (m/s2)")],
    export_sets=[("Messung", [("Zeit (s)", "ta"), ("a_x (m/s²)", "ax"), ("a_y (m/s²)", "ay"), ("a_z (m/s²)", "az"),
                              ("|a| (m/s²)", "a_abs")])],
    background=[
        ("Zweck", """Der Beschleunigungssensor wird als „Fühler für Berührkräfte“ eingeführt. Er zeigt auf dem
         Tisch dasselbe wie auf der Hand (etwa 9,8 m/s² nach oben) und im Fall 0. So wird die Kraft des Tisches
         sichtbar: Fehlt die Unterlage, fehlt die Kraft. Das Experiment ist kurz, braucht kein Material und ist
         die Grundlage für E09 bis E13."""),
        ("Fehlvorstellung", """„Nur aktive Körper können Kräfte ausüben, passive leisten nur Widerstand“; „Tische
         üben keine Kraft auf ein darauf liegendes Buch aus“ (Schecker u. a. 2018, S. 78; Handout Schecker)."""),
        ("Physik", """Ein Beschleunigungssensor misst die „spezifische Kraft“: die Summe aller Kräfte außer der
         Gravitation, geteilt durch die Masse (a − g). Ruht er auf dem Tisch, ist das die Normalkraft des Tisches
         pro Masse, also 9,81 m/s² nach oben. Im freien Fall wirkt nur die Gravitation, er zeigt 0."""),
        ("Erwartung", """Tisch und Hand je etwa 9,7–9,9 m/s² (kleiner Offset des Sensors möglich), im Fall unter
         etwa 1 m/s²."""),
        ("Hinweise", """Steht und fällt mit der Einführung des Sensors (Satz oben im Reiter Experiment). Ohne
         diese entsteht leicht die neue Fehlvorstellung „im Fall wirkt keine Schwerkraft“ – im Gespräch
         aufgreifen. Das Vorzeichen der z-Achse vorher prüfen: Mit der Oberseite nach oben auf dem Tisch sollte
         „zur Oberseite des mini“ erscheinen; sonst die Oberseite in der Anleitung anders benennen."""),
    ],
))

# ---------------------------------------------------------------------------
# E09 Aufzug
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="aufzug", title="Braucht Bewegung eine Kraft?",
    description="Vortest, Experiment mit dem phyphox:mini im Aufzug (Höhe und Geschwindigkeit aus dem Luftdruck, "
                "Beschleunigungssensor) und Nachtest zur Vorstellung „Bewegung braucht eine Kraft in "
                "Bewegungsrichtung“.",
    items=[
        MC("aufzug", "Ein Aufzug fährt mit gleichbleibender Geschwindigkeit nach oben. Die Kraft des Bodens auf "
                     "deine Füße ist …",
           [("größer als im Stehen", "Bewegung braucht Kraft in Bewegungsrichtung"),
            ("gleich wie im Stehen", "R"), ("kleiner als im Stehen", "unklare Vorstellung")]),
        MC("sonde", "Eine Raumsonde fliegt weit weg von allen Planeten mit ausgeschaltetem Triebwerk. Sie …",
           [("wird langsamer und bleibt irgendwann stehen", "Bewegung braucht Kraft (Impetus verbraucht sich)"),
            ("fliegt gleich schnell weiter", "R"), ("wird schneller", "unklare Vorstellung")]),
        LK("kraft", "Damit sich etwas gleichmäßig weiterbewegt, muss ständig eine Kraft in Bewegungsrichtung "
                    "wirken.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("puck", "Ein Eishockey-Puck gleitet nach dem Schuss über sehr glattes Eis (ohne Reibung). Welche "
                   "Kraft in Bewegungsrichtung wirkt auf ihn?",
           [("die Kraft des Schlägers, die langsam nachlässt", "Impetus"), ("keine", "R"),
            ("eine Kraft, die umso größer ist, je schneller er ist", "Kraft proportional zur Geschwindigkeit")],
           sicher=False),
        MC("erklaerung", "Wann zeigte der Sensor im Aufzug (nach oben) mehr als im Stillstand?",
           [("während der ganzen Fahrt nach oben", "Bewegung braucht Kraft"),
            ("nur beim Anfahren, also während die Geschwindigkeit zunahm", "R"),
            ("nur bei der schnellsten Fahrt", "Kraft proportional zur Geschwindigkeit")], sicher=False),
    ],
    prediction=("Der Aufzug fährt nach oben. Wann zeigt der Sensor mehr als im Stillstand?",
                [("während der ganzen Fahrt nach oben", "Bewegung braucht Kraft"),
                 ("nur beim Anfahren", "R"), ("nur beim Bremsen", "unklare Vorstellung"),
                 ("nie", "Sensor misst nur Ruhe")]),
    containers=bmp_containers(40) + acc_containers() + [
        c("a_win", 52), c("a_avg"), c("g0", 1, init=9.81), c("a_rel", 0),
        c("p_first"), c("h", 0), c("hs", 0), c("dhs", 0), c("dtp", 0), c("v", 0), c("tv", 0), c("v_now"),
        c("t_c1"), c("t_c2"), c("ta_c", 0), c("a_rel_c", 0), c("a_konst"), c("a_max"), c("a_min"), c("v_max"), c("v_min")],
    inputs=ble_block([bmp_cfg(5, 3), lsm_cfg(0x01, 0x03, 0x02, 0x00, 5)], bmp_out() + acc_out(), mtu=247),
    analysis=bmp_analysis() + acc_analysis(win=["a_win"]) + [
        AVG("a_win", "a_avg"),
        F("[1_]-[2]", ["a_abs", "g0"], "a_rel"),
        FIRST("p", "p_first"), F("([1]-[2_])*8.43", ["p_first", "p"], "h"),
        SMOOTH("h", "hs", 8), DIFF("hs", "dhs"), DIFF("tp", "dtp"),
        F("[1_]/[2_]", ["dhs", "dtp"], "v"), SUB_FROM("tp", "tv", 1), LAST("v", "v_now"),
        RANGE([("ta", "t_c1", "t_c2"), ("a_rel", None, None)], ["ta_c", "a_rel_c"]),
        AVG("a_rel_c", "a_konst"), MAX("a_rel", "a_max"), MIN("a_rel", "a_min"),
        MAX("v", "v_max"), MIN("v", "v_min")],
    analysis_attrs=' sleep="0.1"',
    intro=[I(SENSOR_INTRO),
           I("Du brauchst einen Aufzug, der über mehrere Stockwerke fährt. Lege den mini flach auf den Boden des "
             "Aufzugs.")],
    body=[
        G("Höhe (aus dem Luftdruck)", [("tp", "h")], ly="Höhe", uy="m"),
        G("Geschwindigkeit nach oben", [("tv", "v")], ly="v", uy="m/s",
          pickLabel="Gleichmäßige Fahrt markieren",
          picks=[("x", "Beginn der gleichmäßigen Fahrt", "t_c1"), ("x", "Ende der gleichmäßigen Fahrt", "t_c2")]),
        G("Sensor minus Stillstand", [("ta", "a_rel")], ly="a − a₀", uy="m/s²", scaleMinY="fixed",
          scaleMaxY="fixed", minY=-2, maxY=2),
        V("Geschwindigkeit", "v_now", "m/s", prec=2),
        S(), H("Schritt 2 – Stillstand"),
        I("Lege den mini auf den Boden des stehenden Aufzugs. Warte 5 Sekunden und tippe:"),
        B("Stillstand: Bezugswert festhalten", [("a_avg", "g0")]),
        V("Sensor im Stillstand", "g0", "m/s²", prec=2),
        S(), H("Schritt 3 – Fahren"),
        I("Fahre mehrere Stockwerke nach oben (und gern auch wieder nach unten). Rühre den mini während der "
          "Fahrt nicht an."),
        V("Größter Wert über dem Stillstand", "a_max", "m/s²", prec=2),
        V("Kleinster Wert unter dem Stillstand", "a_min", "m/s²", prec=2),
        V("Höchste Geschwindigkeit nach oben", "v_max", "m/s", prec=2),
        S(), H("Schritt 4 – Gleichmäßige Fahrt untersuchen"),
        I("Tippe auf das Diagramm „Geschwindigkeit“, dann auf „Gleichmäßige Fahrt markieren“. Wähle einen Punkt "
          "am Anfang und einen am Ende des flachen Abschnitts mit der höchsten Geschwindigkeit."),
        V("Mittlerer Wert während der gleichmäßigen Fahrt", "a_konst", "m/s²", prec=2, size=1.5),
        S(), I("Wann weicht der Sensor vom Stillstand ab: wenn der Aufzug schnell ist oder wenn sich seine "
               "Geschwindigkeit ändert? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("a_max", "Größte Abweichung nach oben (m/s2)"), ("a_min", "Größte Abweichung nach unten (m/s2)"),
             ("a_konst", "Mittel bei gleichmäßiger Fahrt (m/s2)"), ("v_max", "Höchste Geschwindigkeit (m/s)"),
             ("g0", "Bezugswert Stillstand (m/s2)")],
    export_sets=[("Messung Druck", [("Zeit (s)", "tp"), ("Druck (hPa)", "p"), ("Höhe (m)", "h")]),
                 ("Geschwindigkeit", [("Zeit (s)", "tv"), ("v (m/s)", "v")]),
                 ("Messung Beschleunigung", [("Zeit (s)", "ta"), ("|a| (m/s²)", "a_abs"), ("a - a0 (m/s²)", "a_rel")]),
                 ("Auswahl", [("Beginn gleichmäßig (s)", "t_c1"), ("Ende gleichmäßig (s)", "t_c2")])],
    background=[
        ("Zweck", """Im Aufzug weicht der Sensor nur beim Anfahren und Bremsen vom Stillstand ab, nicht während der
         schnellsten, gleichmäßigen Fahrt. Höhe und Geschwindigkeit (aus dem Luftdruck) stehen direkt darüber,
         sodass Lernende Geschwindigkeit und Kraft trennen können. Ersatzvorstellung: Eine (zusätzliche) Kraft
         braucht man nur, um die Geschwindigkeit zu ändern."""),
        ("Fehlvorstellung", """„Zur Aufrechterhaltung der Bewegung bedarf es einer Kraft in Bewegungsrichtung“; die
         „Antriebskraft“ sei proportional zur Geschwindigkeit (Schecker u. a. 2018, S. 73; Handout). Verwandt:
         Ruhe und gleichförmige Bewegung als wesensverschieden (S. 72)."""),
        ("Physik", """Der Boden drückt mit F = m·(g + a). Bei gleichförmiger Fahrt ist a = 0, der Sensor zeigt wie
         im Stillstand. Typische Aufzüge: 0,5–1 m/s² beim Anfahren, 1–2 m/s Fahrgeschwindigkeit. Höhe aus dem Druck:
         etwa 8,4 m pro hPa; die Geschwindigkeit ist die geglättete Ableitung der Höhe."""),
        ("Neue phyphox-Funktion", """Im Diagramm „Geschwindigkeit“ markieren die Lernenden per Datenauswahl
         (Data Picker, ab phyphox 1.2.1) Beginn und Ende der gleichmäßigen Fahrt; daraus wird der mittlere
         Sensorwert in genau diesem Abschnitt berechnet."""),
        ("Hinweise", """Braucht einen Aufzug. Die Geschwindigkeit aus dem Druck ist verrauscht und um etwa eine
         Sekunde verzögert (Glättung und IIR-Filter). Der Bezugswert im Stillstand gleicht den Offset des Sensors
         aus. Ersatz ohne Aufzug: gleichmäßig rollender Wagen (weniger sauber, keine Druckmessung)."""),
    ],
))

# ---------------------------------------------------------------------------
# E10 Wurf
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="wurf", title="Was fühlt der Ball im Flug?",
    description="Vortest, Experiment mit dem phyphox:mini (Beschleunigungssensor beim senkrechten Wurf, "
                "Flugzeit und Steighöhe) und Nachtest zur Vorstellung „Ein geworfener Körper trägt die Kraft der "
                "Hand in sich“.",
    items=[
        MC("kraefte", "Ein Ball wird senkrecht hochgeworfen. Welche Kräfte wirken auf ihn, während er nach oben "
                      "fliegt (ohne Luftwiderstand)?",
           [("die Schwerkraft und eine Wurfkraft nach oben", "Impetus / Kraft im Körper"),
            ("nur die Schwerkraft", "R"), ("nur die Wurfkraft", "Impetus")]),
        MC("oben", "Im höchsten Punkt seiner Bahn ist die Beschleunigung des Balls …",
           [("null", "keine Beschleunigung zu einem Zeitpunkt"), ("9,81 m/s² nach unten", "R"),
            ("kurz nach oben gerichtet", "Impetus")]),
        LK("hand", "Ein geworfener Ball trägt die Kraft der Hand noch eine Weile in sich.",
           "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("golf", "Ein Golfball fliegt nach dem Abschlag durch die Luft. Welche Kräfte wirken im Flug "
                   "(Luftwiderstand vernachlässigt)?",
           [("die Abschlagskraft und die Schwerkraft", "Impetus"), ("nur die Schwerkraft", "R"),
            ("zuerst die Abschlagskraft, die nachlässt, dann die Schwerkraft", "Impetus verbraucht sich")],
           sicher=False),
        MC("erklaerung", "Warum zeigte der Sensor während des ganzen Flugs etwa 0?",
           [("Im Flug wirkt keine Schwerkraft.", "neue Fehlvorstellung: keine Schwerkraft im Flug"),
            ("Nur die Schwerkraft wirkt – und die fühlt der Sensor nicht, weil ihn nichts berührt.", "R"),
            ("Wurfkraft und Schwerkraft heben sich auf.", "Impetus")], sicher=False),
    ],
    prediction=("Was zeigt der Sensor, nachdem er die Hand verlassen hat?",
                [("erst noch einen Wert, der langsam abnimmt, oben 0, danach wieder mehr", "Impetus"),
                 ("während des ganzen Flugs etwa denselben Wert (etwa 0)", "R"),
                 ("nur im höchsten Punkt 0, sonst deutlich mehr", "keine Beschleunigung im Umkehrpunkt")]),
    containers=acc_containers() + FREE_FALL_CONT + [c("h_wurf")],
    inputs=ble_block([lsm_cfg(0x01, 0x05, 0x01, 0x00, 15)], acc_out(), mtu=247),
    analysis=acc_analysis() + free_fall_analysis(2.5) + [F("9.81*[1]^2/8", ["t_free"], "h_wurf")],
    intro=[I(SENSOR_INTRO),
           I("Du brauchst ein Kissen oder eine weiche Decke zum Fangen. Wirf den mini nur senkrecht und ohne Drall, "
             "etwa 30–50 cm hoch, und fange ihn mit beiden Händen weich.")],
    body=[
        G("Betrag der gemessenen Beschleunigung", [("ta", "a_abs")], ly="|a|", uy="m/s²", scaleMinY="fixed",
          scaleMaxY="fixed", minY=0, maxY=40, partialUpdate=False),
        S(), H("Schritt 2 – Werfen"),
        I("Tippe vor jedem Wurf auf „Neuer Wurf“. Halte den mini dann ruhig, wirf ihn hoch und fange ihn weich."),
        B("Neuer Wurf", empties=ACC_CLEAR),
        V("Flugzeit (Sensor zeigt fast 0)", "t_free", "s", prec=3, size=1.5),
        V("Mittlerer Wert während des Flugs", "a_free_avg", "m/s²", prec=2),
        V("Steighöhe aus der Flugzeit", "h_wurf", "m", prec=2),
        S(), I("Schau dir die Kurve genau an: Gibt es einen Unterschied zwischen Aufstieg, höchstem Punkt und Fall? "
               "Die Steighöhe wurde allein aus der Flugzeit und g = 9,81 m/s² berechnet – passt sie zu deinem Wurf? "
               "Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("t_free", "Flugzeit (s)"), ("a_free_avg", "Mittelwert im Flug (m/s2)"), ("h_wurf", "Steighöhe (m)")],
    export_sets=[("Messung", [("Zeit (s)", "ta"), ("a_x (m/s²)", "ax"), ("a_y (m/s²)", "ay"), ("a_z (m/s²)", "az"),
                              ("|a| (m/s²)", "a_abs")])],
    background=[
        ("Zweck", """Der Sensor zeigt beim Abwurf einen großen Ausschlag, danach während des gesamten Flugs etwa 0 –
         ohne Unterschied zwischen Aufstieg, höchstem Punkt und Fall – und beim Fangen wieder einen Ausschlag. Die
         Hand wirkt nur, solange sie berührt. Im Flug wirkt nur die Schwerkraft, die ganze Zeit gleich. Die aus der
         Flugzeit berechnete Steighöhe (h = g·t²/8) zeigt, dass g die ganze Zeit wirkt."""),
        ("Fehlvorstellung", """„Ein bewegter Körper hat Kraft“ / gespeicherte Bewegungskraft, „Abschlagskraft“
         (Schecker u. a. 2018, S. 72–73; Handout); „Zu einem Zeitpunkt kann keine Beschleunigung vorliegen“, im
         Umkehrpunkt wird keine Beschleunigung angegeben (S. 67)."""),
        ("Physik", """Der Sensor misst a − g. Im Flug ist a = g, also zeigt er 0 (bis auf Luftwiderstand und
         Drehung). Flugzeit und Steighöhe: t = 2·v₀/g, h = v₀²/(2g) = g·t²/8."""),
        ("Auswertung", """Die Flugzeit ist die Anzahl der Messwerte mit |a| unter 2,5 m/s² mal dem Abtastabstand
         (aus den Zeitstempeln, 208 Hz). Deshalb vor jedem Wurf „Neuer Wurf“ tippen. Kurzes Abheben beim Fangen
         zählt mit."""),
        ("Hinweise", """Riskantestes Experiment: Ohne die Einführung des Sensors (aus E08) entsteht die neue
         Fehlvorstellung „im Flug wirkt keine Schwerkraft“ – die Erklärungsfrage im Nachtest prüft genau das. Drall
         erzeugt Zusatzsignale (Zentripetalbeschleunigung des Sensors). Weich fangen, nicht auf harten Boden fallen
         lassen. Nach E08 einsetzen."""),
    ],
))

# ---------------------------------------------------------------------------
# E11 Kreisbewegung
# ---------------------------------------------------------------------------
sel = "achse"
EXPS.append(Exp(
    key="kreisbewegung", title="Wohin zeigt die Kraft im Kreis?",
    description="Vortest, Experiment mit dem phyphox:mini auf einem Drehteller (radiale Beschleunigung und "
                "Drehrate, a über ω²) und Nachtest zu den Vorstellungen „Zentrifugalkraft nach außen“ und "
                "„Beschleunigung ist nur Tempoänderung“.",
    items=[
        MC("kurve", "Ein Auto fährt mit gleichbleibendem Tempo durch eine Linkskurve. Die Gesamtkraft auf das "
                    "Auto zeigt …",
           [("nach außen (rechts)", "Zentrifugalkraft"), ("nach innen (links)", "R"), ("nach vorn", "Kraft in Bewegungsrichtung"),
            ("es wirkt keine, das Tempo ist ja gleich", "Beschleunigung = Tempoänderung")]),
        MC("karussell", "Ein Karussell dreht sich gleichmäßig. Wird ein Kind auf dem Karussell beschleunigt?",
           [("nein, das Tempo bleibt gleich", "Beschleunigung = Tempoänderung"), ("ja, zur Mitte hin", "R"),
            ("ja, nach außen", "Zentrifugalkraft")]),
        LK("aussen", "In der Kurve drückt mich eine Kraft nach außen.", "Zustimmung (4–5) = Fehlvorstellung "
                                                                      "(Zentrifugalkraft als reale Kraft)"),
    ],
    post_items=[
        MC("satellit", "Ein Satellit kreist um die Erde. Welche Kräfte wirken auf ihn?",
           [("die Schwerkraft und die Fliehkraft, die sich aufheben", "Zentrifugalkraft"),
            ("nur die Schwerkraft, zur Erde hin", "R"), ("keine, er ist schwerelos", "Schwerelosigkeit = keine Kraft")],
           sicher=False),
        MC("erklaerung", "Die gemessene Beschleunigung zeigte zur Drehachse, weil …",
           [("die Unterlage den mini ständig zur Mitte hin von der geraden Bahn ablenkt", "R"),
            ("die Fliehkraft nach innen wirkt", "Begriffsverwirrung"),
            ("der Sensor nur die Drehung misst, nicht die Kraft", "Wegerklären")], sicher=False),
    ],
    pre_prediction=[
        I("Lege den mini flach auf den Drehteller (oder in die Salatschleuder), etwa 10 cm von der Drehachse "
          "entfernt. Welche Achse des mini zeigt zur Drehachse (nach innen)? Die Achsen sind auf dem Gehäuse "
          "markiert."),
        DD(sel, [(1, "+x zeigt nach innen"), (2, "−x zeigt nach innen"), (3, "+y zeigt nach innen"),
                 (4, "−y zeigt nach innen")], default=1),
    ],
    prediction=("In welche Richtung zeigt die gemessene Beschleunigung, wenn sich der Teller gleichmäßig dreht?",
                [("nach außen", "Zentrifugalkraft"), ("nach innen, zur Drehachse", "R"),
                 ("in Bewegungsrichtung", "Kraft in Bewegungsrichtung"),
                 ("es gibt keine, das Tempo ist ja gleich", "Beschleunigung = Tempoänderung")]),
    containers=[c(sel, 1, init=1, group="_"), c("sx"), c("sy")] + acc_containers() + [
        c("tg_raw", 0), c("gx_raw", 0), c("gy_raw", 0), c("gz_raw", 0), c("tg", 0), c("gz", 0),
        c("ain_new", 0), c("ain", 0), c("w2_new", 0), c("ain_chunk"), c("w2_chunk"), c("w2_sc", 0), c("ain_sc", 0),
        c("ain_win", 52), c("w_win", 52), c("ain_avg"), c("w_avg"), c("w2_avg"), c("r_mess"), c("w2_vis"),
        c("ain_hold"), c("w_hold"), c("r_hold")],
    inputs=ble_block([lsm_cfg(0x03, 0x04, 0x01, 0x0C, 10)], acc_out() + gyr_out(), mtu=247),
    analysis=[
        F("(1-abs(sign([1]-1)))-(1-abs(sign([1]-2)))", [sel], "sx"),
        F("(1-abs(sign([1]-3)))-(1-abs(sign([1]-4)))", [sel], "sy"),
        F("[1]*[3_]+[2]*[4_]", ["sx", "sy", "ax_raw", "ay_raw"], "ain_new"),
        APP("ain_new", "ain", keep=True, append=True), APP("ain_new", "ain_win", keep=True, append=True),
        F("([1_]*3.14159265/180)^2", ["gz_raw"], "w2_new"),
        APP("gz_raw", "w_win", keep=True, append=True),
        AVG("ain_new", "ain_chunk", keep=False), AVG("w2_new", "w2_chunk", keep=False),
        MATCH(["w2_chunk", "ain_chunk"], ["w2_sc", "ain_sc"]),
        APP("tg_raw", "tg", append=True), APP("gz_raw", "gz", append=True),
        APP("gx_raw", "gx_dump"), APP("gy_raw", "gx_dump"),
    ] + acc_analysis() + [
        AVG("ain_win", "ain_avg"), AVG("w_win", "w_avg"),
        F("([1]*3.14159265/180)^2", ["w_avg"], "w2_avg"),
        F("[1]/[2]", ["ain_avg", "w2_avg"], "r_mess"), F("[1]-1", ["w2_avg"], "w2_vis"),
        F("[1]/([2]*3.14159265/180)^2", ["ain_hold", "w_hold"], "r_hold")],
    intro=[I(SENSOR_INTRO),
           I("Du brauchst einen waagerechten Drehteller (Plattenspieler, Drehhocker mit Brett, Salatschleuder) "
             "und Klebeband, um den mini zu befestigen.")],
    body=[
        G("Beschleunigung zur Drehachse hin", [("ta", "ain")], ly="a nach innen", uy="m/s²"),
        V("Gemessene Beschleunigung", "ain_avg", "m/s²", prec=2, size=1.5),
        V("Richtung", "ain_avg", maps=[(0.3, None, "nach innen, zur Drehachse"), (None, -0.3, "nach außen"),
                                       (None, None, "etwa 0")]),
        V("Drehrate", "w_avg", "°/s", prec=0),
        S(), H("Schritt 2 – Gleichmäßig drehen"),
        I("Drehe den Teller gleichmäßig, erst langsam (etwa eine Umdrehung in 2 Sekunden), dann schneller. Halte "
          "jede Geschwindigkeit einige Sekunden. Tippe bei gleichmäßiger Drehung:"),
        B("Werte bei gleichmäßiger Drehung festhalten", [("ain_avg", "ain_hold"), ("w_avg", "w_hold")]),
        V("Festgehalten: Beschleunigung nach innen", "ain_hold", "m/s²", prec=2),
        V("Festgehalten: Drehrate", "w_hold", "°/s", prec=0),
        S(), H("Schritt 3 – Je schneller, desto mehr?"),
        G("Beschleunigung über ω² (Drehrate zum Quadrat)", [("w2_sc", "ain_sc")], lx="ω²", ux="1/s²",
          ly="a nach innen", uy="m/s²", style="dots", partialUpdate=False, scaleMinX="fixed", minX=0),
        I("Liegen die Punkte auf einer Geraden durch den Ursprung, gilt a = ω²·r. Die Steigung ist der Abstand "
          "von der Drehachse:"),
        V("Radius aus der Messung (aktuell)", "r_mess", "cm", factor=100, prec=1, visibility="w2_vis"),
        V("Radius aus den festgehaltenen Werten", "r_hold", "cm", factor=100, prec=1),
        S(), I("Miss den Abstand des mini von der Drehachse mit dem Lineal und vergleiche. Wer übt die Kraft zur "
               "Mitte hin aus? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[(sel, "Gewählte Achse"), ("ain_hold", "a nach innen (m/s2)"), ("w_hold", "Drehrate (Grad/s)"),
             ("r_hold", "Radius aus Messung (m)")],
    export_sets=[("Messung Beschleunigung", [("Zeit (s)", "ta"), ("a_x (m/s²)", "ax"), ("a_y (m/s²)", "ay"),
                                             ("a_z (m/s²)", "az"), ("a nach innen (m/s²)", "ain")]),
                 ("Messung Drehrate", [("Zeit (s)", "tg"), ("ω_z (°/s)", "gz")]),
                 ("a über ω²", [("ω² (1/s²)", "w2_sc"), ("a nach innen (m/s²)", "ain_sc")])],
    background=[
        ("Zweck", """Auf dem gleichmäßig drehenden Teller zeigt die gemessene Beschleunigung zur Drehachse, obwohl
         sich das Tempo nicht ändert. Sie wächst mit dem Quadrat der Drehrate (a = ω²·r). Damit werden zwei
         Vorstellungen angesprochen: die Zentrifugalkraft als reale, nach außen wirkende Kraft und „Beschleunigung
         ist nur Tempoänderung“."""),
        ("Fehlvorstellung", """„Bei Kreisbewegungen wirkt die Zentrifugalkraft“ nach außen – eine der hartnäckigsten
         Vorstellungen (Schecker u. a. 2018, S. 78–79; Handout). „Beschleunigung ist Tempoänderung“, eine
         Richtungsänderung gilt nicht als Beschleunigung (S. 66)."""),
        ("Physik", """Der Sensor misst die Kraft der Unterlage (Haftreibung, Wand der Salatschleuder) pro Masse.
         Diese zeigt zur Drehachse und hält den mini auf der Kreisbahn: a = ω²·r. Bei r = 10 cm und 300 °/s
         (5,2 rad/s) sind das etwa 2,7 m/s². Das „Gefühl, nach außen gedrückt zu werden“, ist die Trägheit im
         mitrotierenden Bezugssystem."""),
        ("Auswertung", """Die Achsen-Auswahl legt fest, welche Komponente (x oder y, mit Vorzeichen) als „nach innen“
         gilt. Für das Diagramm a über ω² werden die Werte je Datenpaket gemittelt. Der Radius aus der Messung wird
         nur angezeigt, wenn ω² über 1/s² liegt."""),
        ("Hinweise", """Achsenrichtung und Vorzeichen hängen von der Montage ab – vorher auf einem Teller testen und
         die Achsen auf dem Gehäuse markieren. Sensor liegt nicht im Mittelpunkt des Gehäuses; den Radius zur
         Sensormitte messen. Drehebene waagerecht halten, sonst überlagert die Schwerkraft das Signal (Fahrradfelge
         ungeeignet). Beschleunigungs- und Drehratenpakete kommen getrennt an; die Zuordnung je Paket ist eine
         Näherung (prüfen)."""),
    ],
))
# Dummy-Container fuer verworfene Drehraten-Komponenten
EXPS[-1].containers.append(c("gx_dump", 1))

# ---------------------------------------------------------------------------
# E12 Loslassen
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="loslassen", title="Was passiert beim Loslassen?",
    description="Vortest, Experiment mit dem phyphox:mini (Beschleunigungssensor an einer Schnur im Kreis "
                "geschleudert und losgelassen) und Nachtest zur Vorstellung „Die Kreisbewegung prägt sich dem "
                "Körper ein“.",
    items=[
        MC("bahn", "Ein Ball an einer Schnur wird waagerecht im Kreis geschleudert und dann losgelassen. Welchen "
                   "Weg nimmt er direkt danach (Sicht von oben)?",
           [("er fliegt auf einer gekrümmten Bahn weiter", "Bewegungsform prägt sich ein"),
            ("er fliegt geradeaus weiter, in die Richtung, in die er sich gerade bewegt hat", "R"),
            ("er fliegt gerade nach außen, von der Mitte weg", "Zentrifugalkraft")]),
        MC("hammer", "Ein Hammerwerfer lässt den Hammer los. Welche Kraft wirkt unmittelbar danach in "
                     "waagerechter Richtung auf den Hammer (ohne Luft)?",
           [("noch die Kreiskraft, die langsam abklingt", "Bewegungsform prägt sich ein"),
            ("keine", "R"), ("eine Kraft nach außen", "Zentrifugalkraft")]),
        LK("kreis", "Ein Körper, der im Kreis bewegt wurde, behält die Kreisbewegung noch kurz bei.",
           "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("schleuder", "Wassertropfen fliegen aus einer sich drehenden Salatschleuder. Wie fliegen sie vom Korb "
                        "weg (Sicht von oben)?",
           [("in Spiralen weiter um die Mitte", "Bewegungsform prägt sich ein"),
            ("geradeaus, in Richtung der Bewegung am Rand", "R"), ("gerade nach außen", "Zentrifugalkraft")],
           sicher=False),
        MC("erklaerung", "Was zeigte der Sensor direkt nach dem Loslassen?",
           [("eine Kraft, die langsam abklingt", "Bewegungsform prägt sich ein"),
            ("sofort etwa 0 – ohne Kraft gibt es keine Kurve mehr", "R"),
            ("eine Kraft nach außen", "Zentrifugalkraft")], sicher=False),
    ],
    prediction=("Was fühlt der Sensor direkt nach dem Loslassen?",
                [("noch eine Weile die Kreis-Kraft, die langsam abklingt", "Bewegungsform prägt sich ein"),
                 ("sofort nichts mehr (etwa 0)", "R"), ("zuerst eine Kraft nach außen", "Zentrifugalkraft")]),
    containers=acc_containers() + [c("a_max"), c("t_p1"), c("t_p2"), c("dt_los"), c("dt_s"),
                                   c("n_all"), c("ta_first"), c("ta_last")],
    inputs=ble_block([lsm_cfg(0x01, 0x05, 0x01, 0x00, 15)], acc_out(), mtu=247),
    analysis=acc_analysis() + [
        MAX("a_abs", "a_max"), F("[1]-[2]", ["t_p2", "t_p1"], "dt_los"),
        COUNT("ta", "n_all"), FIRST("ta", "ta_first"), LAST("ta", "ta_last"),
        F("([2]-[1])/([3]-1)", ["ta_first", "ta_last", "n_all"], "dt_s")],
    intro=[I(SENSOR_INTRO),
           I("Du brauchst einen kleinen, festen Beutel für den mini, etwa 50 cm Schnur und eine große freie "
             "Fläche mit weicher Landung (Wiese, Turnmatte). Niemand darf im Umkreis stehen!")],
    body=[
        G("Betrag der gemessenen Beschleunigung", [("ta", "a_abs")], ly="|a|", uy="m/s²", scaleMinY="fixed",
          minY=0, partialUpdate=False, pickLabel="Loslassen untersuchen",
          picks=[("x", "Letzter Punkt mit Schnurkraft", "t_p1"), ("x", "Erster Punkt mit etwa 0", "t_p2")]),
        V("Größter Wert", "a_max", "m/s²", prec=1),
        S(), H("Schritt 2 – Schleudern und loslassen"),
        I("Tippe auf „Neuer Versuch“. Schleudere den mini im Beutel waagerecht über dem Kopf im Kreis (etwa "
          "2 Umdrehungen pro Sekunde) und lass die Schnur los."),
        B("Neuer Versuch", empties=ACC_CLEAR),
        S(), H("Schritt 3 – Wie schnell verschwindet die Kraft?"),
        I("Tippe auf das Diagramm und dann auf „Loslassen untersuchen“. Wähle den letzten Punkt, an dem die "
          "Schnur noch zieht, und den ersten Punkt mit etwa 0."),
        V("Zeit zwischen Schnurkraft und 0", "dt_los", "ms", factor=1000, prec=0, size=1.5),
        V("Abstand zweier Messpunkte", "dt_s", "ms", factor=1000, prec=1),
        S(), I("Wenn die Kraft sofort verschwindet: Was bedeutet das für die Bahn? Ohne Kraft zur Mitte gibt es "
               "keine Kurve. Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("a_max", "Größter Wert (m/s2)"), ("dt_los", "Zeit bis 0 (s)"), ("dt_s", "Abtastabstand (s)")],
    export_sets=[("Messung", [("Zeit (s)", "ta"), ("a_x (m/s²)", "ax"), ("a_y (m/s²)", "ay"), ("a_z (m/s²)", "az"),
                              ("|a| (m/s²)", "a_abs")]),
                 ("Auswahl", [("letzter Punkt Schnur (s)", "t_p1"), ("erster Punkt 0 (s)", "t_p2")])],
    background=[
        ("Zweck", """Solange die Schnur zieht, misst der Sensor einen großen Wert; im Moment des Loslassens springt
         der Betrag auf etwa 0, ohne Abklingen. Gemessen wird nicht die Bahn, sondern das Fehlen einer Kraft – der
         Erklärtext und die Nachtestfragen stellen die Verbindung zur geraden Bahn her."""),
        ("Fehlvorstellung", """„Die Bewegungsform prägt sich dem bewegten Objekt ein“; ein losgelassener, im Kreis
         geschleuderter Ball fliege auf einer gekrümmten Bahn weiter (Schecker u. a. 2018, S. 69; Aufgabe nach dem
         Force Concept Inventory)."""),
        ("Physik", """Die Schnurkraft liefert die Zentripetalkraft m·ω²·r. Bei 2 Umdrehungen pro Sekunde und
         r = 0,5 m sind das etwa 79 m/s² (8 g). Nach dem Loslassen wirkt waagerecht keine Kraft mehr, der Körper
         bewegt sich tangential geradeaus weiter (und fällt durch die Schwerkraft)."""),
        ("Neue phyphox-Funktion", """Mit der Datenauswahl (Data Picker, ab phyphox 1.2.1) wählen die Lernenden den
         letzten Punkt mit Schnurkraft und den ersten mit 0. Die Zeit dazwischen liegt im Bereich eines
         Messpunktabstands (rund 5 ms bei 208 Hz)."""),
        ("Hinweise", """Sicherheitsrisiko beim Schleudern: nur im Freien oder in der Turnhalle, Abstand zu anderen,
         weiche Landung. Der Beutel darf beim Loslassen nicht an der Schnur hängen bleiben (Schnur fest am Beutel,
         Ende loslassen). Die Bildfrage aus dem Konzeptpapier ist hier in Worten formuliert; ein Bild ließe sich mit
         dem image-Element (res-Ordner) ergänzen."""),
    ],
))

# ---------------------------------------------------------------------------
# E13 Fallzeit
# ---------------------------------------------------------------------------
fall_slots = [("l1", "ohne Münzen, Versuch 1"), ("l2", "ohne Münzen, Versuch 2"), ("l3", "ohne Münzen, Versuch 3"),
              ("s1", "mit Münzen, Versuch 1"), ("s2", "mit Münzen, Versuch 2"), ("s3", "mit Münzen, Versuch 3")]
EXPS.append(Exp(
    key="fallzeit", title="Fällt Schweres schneller?",
    description="Vortest, Experiment mit dem phyphox:mini (Fallzeit mit und ohne Zusatzmasse aus dem "
                "Beschleunigungssensor) und Nachtest zur Vorstellung „Je schwerer, desto schneller fällt ein "
                "Körper“.",
    items=[
        MC("kugeln", "Eine Metallkugel und eine gleich große, halb so schwere Kugel werden gleichzeitig vom Tisch "
                     "fallen gelassen. Welche ist zuerst unten?",
           [("die schwere, deutlich früher", "je schwerer, desto schneller"), ("beide etwa gleichzeitig", "R"),
            ("die leichte", "unklare Vorstellung")]),
        MC("pendel", "Ein Pendel bekommt ein doppelt so schweres Gewicht (gleiche Fadenlänge). Es schwingt "
                     "dann …",
           [("schneller", "je schwerer, desto schneller"), ("gleich schnell", "R"), ("langsamer", "schwer = träge/langsam")]),
        LK("schwer", "Schwere Dinge fallen schneller als leichte.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("mond", "Auf dem Mond (ohne Luft) lässt ein Astronaut einen Hammer und eine Feder gleichzeitig aus "
                   "gleicher Höhe fallen.",
           [("Der Hammer ist zuerst unten.", "je schwerer, desto schneller"), ("Beide kommen gleichzeitig an.", "R"),
            ("Die Feder ist zuerst unten.", "unklare Vorstellung")], sicher=False),
        MC("erklaerung", "Warum fielen beide gleich lang?",
           [("Die Münzen waren zu leicht, um einen Unterschied zu machen.", "Wegerklären"),
            ("Auf den schwereren wirkt eine größere Schwerkraft, er ist aber auch entsprechend schwerer in Bewegung zu bringen.", "R"),
            ("Die Messung ist zu ungenau.", "Wegerklären")], sicher=False),
    ],
    prediction=("Der mini fällt einmal allein und einmal mit aufgeklebten Münzen (etwa doppelte Masse) aus 1 m "
                "Höhe. Welche Fallzeit ist kürzer?",
                [("mit Münzen deutlich kürzer", "je schwerer, desto schneller"), ("beide etwa gleich", "R"),
                 ("mit Münzen länger", "unklare Vorstellung")]),
    containers=acc_containers() + FREE_FALL_CONT + [c(f"f_{k}") for k, _ in fall_slots] + [
        c("f_leicht"), c("f_schwer"), c("f_diff"), c("m_leicht", 1, init=5, group="_"),
        c("m_schwer", 1, init=10, group="_"), c("t_theo")],
    inputs=ble_block([lsm_cfg(0x01, 0x06, 0x01, 0x00, 15)], acc_out(), mtu=247),
    analysis=acc_analysis() + free_fall_analysis(2.5) + [
        F("([1]+[2]+[3])/3", ["f_l1", "f_l2", "f_l3"], "f_leicht"),
        F("([1]+[2]+[3])/3", ["f_s1", "f_s2", "f_s3"], "f_schwer"),
        F("[1]-[2]", ["f_schwer", "f_leicht"], "f_diff"),
        F("sqrt(2*1/9.81)", [], "t_theo")],
    intro=[I(SENSOR_INTRO + " Im freien Fall zeigt er deshalb etwa 0 – daraus bestimmt phyphox die Fallzeit."),
           I("Du brauchst ein dickes Kissen, ein Maßband und einige Münzen, die du fest mit Klebeband am mini "
             "befestigst (etwa so schwer wie der mini selbst).")],
    body=[
        G("Betrag der gemessenen Beschleunigung", [("ta", "a_abs")], ly="|a|", uy="m/s²", scaleMinY="fixed",
          scaleMaxY="fixed", minY=0, maxY=30, partialUpdate=False),
        V("Fallzeit dieses Versuchs", "t_free", "s", prec=3, size=1.5),
        S(), H("Schritt 2 – Fallen lassen"),
        I("Tippe vor jedem Fall auf „Neuer Fall“. Halte den mini ruhig 1 m über dem Kissen und lass ihn los, "
          "ohne ihn anzustoßen. Speichere die Fallzeit danach im passenden Feld."),
        B("Neuer Fall", empties=ACC_CLEAR),
        I("Ohne Münzen:", bold=True)] + [
        B(f"Speichern: {lab}", [("t_free", f"f_{k}")], dyn=f"f_{k}",
          maps=[(0.001, None, f"✓ {lab} gespeichert (erneut tippen ersetzt)")]) for k, lab in fall_slots[:3]] + [
        I("Klebe jetzt die Münzen fest an den mini. Mit Münzen:", bold=True)] + [
        B(f"Speichern: {lab}", [("t_free", f"f_{k}")], dyn=f"f_{k}",
          maps=[(0.001, None, f"✓ {lab} gespeichert (erneut tippen ersetzt)")]) for k, lab in fall_slots[3:]] + [
        S(), H("Schritt 3 – Vergleich"),
        V("Mittlere Fallzeit ohne Münzen", "f_leicht", "s", prec=3),
        V("Mittlere Fallzeit mit Münzen", "f_schwer", "s", prec=3),
        V("Unterschied (mit − ohne)", "f_diff", "ms", factor=1000, prec=0, size=1.5),
        V("Zum Vergleich: berechnet für 1 m", "t_theo", "s", prec=3),
        E("Masse ohne Münzen (optional)", "m_leicht", "g", default=5, signed=False),
        E("Masse mit Münzen (optional)", "m_schwer", "g", default=10, signed=False),
        S(), I("Ist der Unterschied größer als die Schwankung zwischen den drei Versuchen? Weiter zum Reiter "
               "„3 Nachtest“."),
    ],
    results=[("f_leicht", "Fallzeit ohne Münzen (s)"), ("f_schwer", "Fallzeit mit Münzen (s)"),
             ("f_diff", "Unterschied (s)"), ("m_leicht", "Masse leicht (g)"), ("m_schwer", "Masse schwer (g)")]
            + [(f"f_{k}", f"Fallzeit {lab} (s)") for k, lab in fall_slots],
    export_sets=[("Letzter Fall", [("Zeit (s)", "ta"), ("|a| (m/s²)", "a_abs")])],
    background=[
        ("Zweck", """Die Lernenden messen die Fallzeit mit und ohne Zusatzmasse je dreimal und vergleichen. Die
         Fallzeit wird automatisch aus dem Sensor bestimmt (Dauer der Phase mit |a| nahe 0), sodass sie viel
         genauer ist als mit der Stoppuhr. Ersatzvorstellung: Größere Masse heißt größere Schwerkraft, aber auch
         größere Trägheit – beide heben sich auf."""),
        ("Fehlvorstellung", """„Je schwerer, desto schneller (Fallbewegung)“ (Handout Schecker)."""),
        ("Physik", """Ohne Luftwiderstand gilt t = √(2h/g), unabhängig von der Masse. Für 1 m sind das 0,45 s.
         Bei einem kompakten Körper wie dem mini ist der Luftwiderstand auf 1 m vernachlässigbar (unter 1 ms)."""),
        ("Auswertung", """Fallzeit = Anzahl der Messwerte mit |a| unter 2,5 m/s² mal Abtastabstand (aus den
         Zeitstempeln, 416 Hz, also etwa 2,4 ms Auflösung). Deshalb vor jedem Fall „Neuer Fall“ tippen. Die
         Speicher-Knöpfe zeigen ein Häkchen, wenn ein Wert gespeichert ist (neue Button-Beschriftung über
         dynamicLabel). Schwankungen kommen vor allem von der Fallhöhe."""),
        ("Hinweise", """Stoßbelastung beim Aufprall: immer auf ein dickes Kissen. Münzen fest verkleben, sie dürfen
         sich im Fall nicht lösen. Die Pendel-Variante aus dem Konzeptpapier ist hier nicht umgesetzt (wäre mit der
         Drehrate möglich)."""),
    ],
))

# ---------------------------------------------------------------------------
# E14 Stoss (zwei Geraete)
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="stoss", title="Wer übt beim Stoß die größere Kraft aus?",
    description="Vortest, Experiment mit zwei phyphox:mini auf zwei Wagen unterschiedlicher Masse (Spitzen der "
                "Beschleunigung beim Stoß, Kräfte F = m·a) und Nachtest zur Vorstellung „Je schwerer, desto "
                "stärker“.",
    items=[
        MC("lkw", "Ein LKW und ein PKW stoßen mit gleichem Tempo frontal zusammen. Die Kraft des LKW auf den PKW "
                  "ist …",
           [("größer als die Kraft des PKW auf den LKW", "je schwerer, desto stärker"),
            ("gleich groß wie die Kraft des PKW auf den LKW", "R"),
            ("kleiner als die Kraft des PKW auf den LKW", "unklare Vorstellung")]),
        MC("mond", "Die Erde zieht den Mond an. Der Mond zieht die Erde …",
           [("schwächer an", "je schwerer, desto stärker"), ("gleich stark an", "R"), ("gar nicht an", "nur der größere Körper wirkt")]),
        LK("schwer", "Der schwerere Körper übt beim Stoß die größere Kraft aus.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("inliner", "Ein Erwachsener und ein Kind stehen auf Inlinern und stoßen sich mit den Händen "
                      "voneinander ab. Wer übt die größere Kraft auf den anderen aus?",
           [("der Erwachsene", "je schwerer, desto stärker"), ("beide gleich", "R"), ("das Kind", "unklare Vorstellung")],
           sicher=False),
        MC("erklaerung", "Warum wurde der leichtere Wagen beim Stoß stärker beschleunigt?",
           [("Er bekam die größere Kraft ab.", "je schwerer, desto stärker"),
            ("Beide bekamen gleich viel Kraft, aber er hat weniger Masse.", "R"),
            ("Der schwere Wagen hat seine Kraft beim Stoß verbraucht.", "Kraft als Vorrat")], sicher=False),
    ],
    prediction=("Wagen A ist leicht, Wagen B doppelt so schwer. Auf welchen Wagen wirkt beim Stoß die größere "
                "Kraft?",
                [("auf den leichten Wagen A", "je schwerer, desto stärker"), ("auf beide gleich", "R"),
                 ("auf den schweren Wagen B", "unklare Vorstellung")]),
    containers=acc_containers("A_") + acc_containers("B_") + [
        c("A_ah", 0), c("B_ah", 0), c("A_peak"), c("B_peak"),
        c("m_A", 1, init=250, group="_"), c("m_B", 1, init=500, group="_"),
        c("F_A"), c("F_B"), c("F_ratio"), c("a_ratio"), c("m_ratio")],
    inputs="\n".join([
        ble_block([lsm_cfg(0x01, 0x06, 0x01, 0x00, 15)], acc_out("A_"), dev_id="Wagen A (leicht)", mtu=247),
        ble_block([lsm_cfg(0x01, 0x06, 0x01, 0x00, 15)], acc_out("B_"), dev_id="Wagen B (schwer)", mtu=247)]),
    analysis=[F("sqrt([1_]^2+[2_]^2)", ["A_ax_raw", "A_ay_raw"], "A_ah", append=True),
              F("sqrt([1_]^2+[2_]^2)", ["B_ax_raw", "B_ay_raw"], "B_ah", append=True)]
             + acc_analysis("A_") + acc_analysis("B_") + [
        MAX("A_ah", "A_peak"), MAX("B_ah", "B_peak"),
        F("[1]/1000*[2]", ["m_A", "A_peak"], "F_A"), F("[1]/1000*[2]", ["m_B", "B_peak"], "F_B"),
        F("[1]/[2]", ["F_A", "F_B"], "F_ratio"), F("[1]/[2]", ["A_peak", "B_peak"], "a_ratio"),
        F("[1]/[2]", ["m_B", "m_A"], "m_ratio")],
    intro=[I(SENSOR_INTRO),
           I("Du brauchst zwei phyphox:mini und zwei Wagen auf einer glatten Bahn. Wagen B soll etwa doppelt so "
             "schwer sein wie Wagen A (Zusatzgewicht). An einem Wagen ein weicher Puffer (Schaumstoff oder Feder). "
             "Klebe auf jeden Wagen einen mini flach auf. Beim Verbinden fragt phyphox nach zwei Geräten: zuerst "
             "der mini auf Wagen A, dann der auf Wagen B.")],
    body=[
        G("Waagerechte Beschleunigung", [("A_ta", "A_ah", "orange"), ("B_ta", "B_ah", "blue")],
          ly="a waagerecht", uy="m/s²", partialUpdate=False),
        I("Orange: Wagen A (leicht) · Blau: Wagen B (schwer)", size=0.85),
        S(), H("Schritt 2 – Massen eingeben"),
        E("Masse Wagen A mit mini", "m_A", "g", default=250, signed=False),
        E("Masse Wagen B mit mini", "m_B", "g", default=500, signed=False),
        S(), H("Schritt 3 – Stoß"),
        I("Wagen B steht still. Schiebe Wagen A an und lass ihn los. Tippe, sobald A frei rollt (vor dem Stoß):"),
        B("Jetzt kommt der Stoß", empties=["A_ta", "A_ax", "A_ay", "A_az", "A_a_abs", "A_ah",
                                           "B_ta", "B_ax", "B_ay", "B_az", "B_a_abs", "B_ah"]),
        V("Größte Beschleunigung Wagen A", "A_peak", "m/s²", prec=2),
        V("Größte Beschleunigung Wagen B", "B_peak", "m/s²", prec=2),
        S(), H("Schritt 4 – Kräfte vergleichen"),
        I("Kraft = Masse · Beschleunigung"),
        V("Kraft auf Wagen A", "F_A", "N", prec=2, size=1.3),
        V("Kraft auf Wagen B", "F_B", "N", prec=2, size=1.3),
        V("Verhältnis der Kräfte A : B", "F_ratio", prec=2),
        V("Verhältnis der Beschleunigungen A : B", "a_ratio", prec=2),
        V("Verhältnis der Massen B : A", "m_ratio", prec=2),
        S(), I("Wiederhole den Stoß ein paarmal, auch mit vertauschten Rollen. Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("A_peak", "Spitze a Wagen A (m/s2)"), ("B_peak", "Spitze a Wagen B (m/s2)"), ("m_A", "Masse A (g)"),
             ("m_B", "Masse B (g)"), ("F_ratio", "Verhältnis F_A/F_B")],
    export_sets=[("Wagen A", [("Zeit (s)", "A_ta"), ("a waagerecht (m/s²)", "A_ah")]),
                 ("Wagen B", [("Zeit (s)", "B_ta"), ("a waagerecht (m/s²)", "B_ah")])],
    background=[
        ("Zweck", """Zwei Wagen mit Massenverhältnis 1 : 2 stoßen zusammen. Die Spitzenbeschleunigungen verhalten
         sich umgekehrt wie die Massen, Masse mal Beschleunigung ist bei beiden gleich: actio = reactio. Die
         Ersatzvorstellung trennt Kraft (gleich) und Wirkung der Kraft (abhängig von der Masse)."""),
        ("Fehlvorstellung", """„Je größer/schwerer, desto stärker“; beim Zusammenstoß übe der LKW die größere Kraft
         auf den PKW aus (Schecker u. a. 2018, S. 73; Handout). Verwandt: „Die stärkere Kraft gewinnt“ (S. 75).
         Aufgabe LKW/PKW nach dem Force and Motion Conceptual Evaluation."""),
        ("Physik", """Drittes Newtonsches Gesetz: F_AB = −F_BA zu jedem Zeitpunkt. Damit m_A·a_A = m_B·a_B, also
         a_A/a_B = m_B/m_A."""),
        ("Auswertung", """Verglichen werden die Spitzenwerte der waagerechten Beschleunigung √(a_x² + a_y²) seit dem
         Knopf „Jetzt kommt der Stoß“. Die Zeitbasen der beiden Geräte sind nicht synchron, die Kurven können
         gegeneinander verschoben sein – das ist für die Spitzenwerte egal. Bei 416 Hz und einem weichen Puffer
         (Stoßdauer 20–50 ms) wird die Spitze gut erfasst."""),
        ("Hinweise", """Aufwendigstes Experiment: zwei Module, zwei Bluetooth-Verbindungen (in der Datei als
         „Wagen A (leicht)“ und „Wagen B (schwer)“). Die mini müssen flach liegen, sonst geht ein Teil der
         Schwerkraft in die waagerechte Komponente. Harter Stoß ohne Puffer erzeugt sehr kurze Spitzen, die
         unterabgetastet werden. Reibung und Schwingungen der Wagen verfälschen die Spitzen etwas; mehrfach
         wiederholen."""),
    ],
))

# ---------------------------------------------------------------------------
# E15 Laut gleich hoch (nur Smartphone)
# ---------------------------------------------------------------------------
EXPS.append(Exp(
    key="laut_hoch", title="Laut gleich hoch?",
    description="Vortest, Experiment mit dem Mikrofon des Smartphones (Frequenz und Lautstärke eines Tons) und "
                "Nachtest zur Vorstellung „Laute Töne sind hohe Töne“. Kein phyphox:mini nötig.",
    start_hint="Tippe oben rechts auf ▶, damit das Mikrofon misst, und beantworte dann die Fragen.",
    items=[
        MC("gitarre", "Du schlägst dieselbe Gitarrensaite stärker an. Der Ton wird …",
           [("lauter und höher", "laut = hoch"), ("nur lauter", "R"), ("nur höher", "laut = hoch")]),
        MC("tuba", "Kann ein tiefer Ton (zum Beispiel von einer Tuba) lauter sein als ein hoher Ton (zum Beispiel "
                   "von einer Flöte)?",
           [("nein, tiefe Töne sind immer leiser", "laut = hoch"), ("ja", "R"), ("nur, wenn man sehr nah dran ist", "unklare Vorstellung")]),
        LK("laut", "Laute Töne sind hohe Töne.", "Zustimmung (4–5) = Fehlvorstellung"),
    ],
    post_items=[
        MC("radio", "Du drehst das Radio lauter. Die Töne des Liedes werden …",
           [("höher", "laut = hoch"), ("nicht höher oder tiefer, nur lauter", "R"), ("tiefer", "unklare Vorstellung")],
           sicher=False),
        MC("erklaerung", "Was änderte sich an der Schwingung, als du den Ton lauter gemacht hast?",
           [("Die Frequenz stieg.", "laut = hoch"), ("Nur die Amplitude (der Ausschlag) wurde größer.", "R"),
            ("Frequenz und Amplitude stiegen beide.", "laut = hoch")], sicher=False),
    ],
    prediction=("Du erzeugst denselben Ton erst leise und dann laut. Was passiert mit der Frequenz?",
                [("sie steigt", "laut = hoch"), ("sie bleibt gleich", "R"), ("sie sinkt", "unklare Vorstellung")]),
    containers=[c("rec", 4800), c("rate", 1, init=48000), c("rec_t", 4800), c("ac_y", 0), c("ac_x", 0),
                c("ac_maxX", 1, init=0.025, static=True), c("t_neg"), c("acf_x", 0), c("acf_y", 0),
                c("ac_peak"), c("period"), c("ac0"), c("quality"), c("f_now"), c("f_vis"),
                c("rec_sq", 4800), c("ms"), c("L_now"), c("osc_t", 0), c("osc_y", 0),
                c("timer_t"), c("t_hist", 0), c("f_hist", 0), c("L_hist", 0), c("f_good"),
                c("f_leise"), c("L_leise"), c("f_laut"), c("L_laut"), c("f_anders"), c("L_anders"),
                c("df_laut"), c("dL_laut"), c("df_anders")],
    inputs='<audio rate="48000">\n    <output component="out">rec</output>\n    <output component="rate">rate</output>\n</audio>',
    analysis=[
        '<ramp>\n    <input as="start" type="value">0</input>\n    <input as="stop" keep="true">rec_t_stop</input>'
        '\n    <input as="length" type="value">4800</input>\n    <output as="out">rec_t</output>\n</ramp>',
        '<autocorrelation>\n    <input as="x" keep="true">rec_t</input>\n    <input as="y" keep="true">rec</input>'
        '\n    <input as="minX" type="value">0</input>\n    <input as="maxX" keep="true">ac_maxX</input>'
        '\n    <output as="y">ac_y</output>\n    <output as="x">ac_x</output>\n</autocorrelation>',
        FIRST("ac_y", "ac0"),
        '<threshold falling="true">\n    <input as="x" keep="true">ac_x</input>\n    <input as="y" keep="true">ac_y</input>'
        '\n    <input as="threshold" type="value">0</input>\n    <output as="position">t_neg</output>\n</threshold>',
        RANGE([("ac_x", "t_neg", None), ("ac_y", None, None)], ["acf_x", "acf_y"]),
        MAX("acf_y", "ac_peak", x="acf_x", pos="period"),
        F("1/[1]", ["period"], "f_now"),
        F("[1]/[2]", ["ac_peak", "ac0"], "quality"),
        F("[1]-0.6", ["quality"], "f_vis"),
        F("[1_]^2", ["rec"], "rec_sq"), AVG("rec_sq", "ms"),
        F("4.3429*log([1])", ["ms"], "L_now"),
        '<subrange>\n    <input as="from" type="value">0</input>\n    <input as="length" type="value">480</input>'
        '\n    <input keep="true">rec</input>\n    <output>osc_y</output>\n</subrange>',
        '<timer>\n    <output as="out">timer_t</output>\n</timer>',
        '<if greater="true">\n    <input as="a" keep="true">quality</input>\n    <input as="b" type="value">0.6</input>'
        '\n    <input as="true" keep="true">f_now</input>\n    <input as="false" type="value">NaN</input>'
        '\n    <output as="result">f_good</output>\n</if>',
        APP("timer_t", "t_hist", keep=True, append=True), APP("f_good", "f_hist", keep=True, append=True),
        APP("L_now", "L_hist", keep=True, append=True),
        F("[1]-[2]", ["f_laut", "f_leise"], "df_laut"), F("[1]-[2]", ["L_laut", "L_leise"], "dL_laut"),
        F("[1]-[2]", ["f_anders", "f_leise"], "df_anders")],
    analysis_attrs=' sleep="0.1"',
    intro=[I("Du brauchst eine Tonquelle mit gleichbleibendem Ton: Stimmgabel, eine angeblasene Flasche, ein "
             "Instrument oder einen Tongenerator auf einem zweiten Gerät (z. B. phyphox „Tongenerator“). Halte das "
             "Smartphone ruhig, etwa 30 cm entfernt.")],
    body=[
        G("Schwingung (10 ms Ausschnitt)", [("osc_t", "osc_y")], lx="Zeit", ux="s", ly="Ausschlag", uy="",
          partialUpdate=False, scaleMinY="fixed", scaleMaxY="fixed", minY=-1, maxY=1),
        V("Frequenz", "f_now", "Hz", prec=0, size=1.8, visibility="f_vis"),
        I("Kein gleichmäßiger Ton erkannt", italic=True, visibility="f_vis_neg"),
        V("Lautstärke (relativ)", "L_now", "dB", prec=1),
        G("Frequenz über die Zeit", [("t_hist", "f_hist")], ly="Frequenz", uy="Hz", style="dots"),
        G("Lautstärke über die Zeit", [("t_hist", "L_hist")], ly="Lautstärke", uy="dB"),
        S(), H("Schritt 2 – Leise"),
        I("Erzeuge den Ton leise und halte ihn gleichmäßig. Tippe:"),
        B("Leisen Ton festhalten", [("f_now", "f_leise"), ("L_now", "L_leise")]),
        V("Leise: Frequenz", "f_leise", "Hz", prec=0), V("Leise: Lautstärke", "L_leise", "dB", prec=1),
        S(), H("Schritt 3 – Laut"),
        I("Erzeuge denselben Ton jetzt laut (stärker anschlagen, kräftiger blasen, Lautstärke hochdrehen). Tippe:"),
        B("Lauten Ton festhalten", [("f_now", "f_laut"), ("L_now", "L_laut")]),
        V("Laut: Frequenz", "f_laut", "Hz", prec=0), V("Laut: Lautstärke", "L_laut", "dB", prec=1),
        V("Änderung der Frequenz", "df_laut", "Hz", prec=0, size=1.3),
        V("Änderung der Lautstärke", "dL_laut", "dB", prec=1, size=1.3),
        S(), H("Schritt 4 – Anderer Ton, gleich laut"),
        I("Erzeuge einen höheren oder tieferen Ton ungefähr so laut wie eben. Tippe:"),
        B("Anderen Ton festhalten", [("f_now", "f_anders"), ("L_now", "L_anders")]),
        V("Anderer Ton: Frequenz", "f_anders", "Hz", prec=0),
        V("Änderung der Frequenz gegenüber leise", "df_anders", "Hz", prec=0),
        S(), I("Was hat sich beim lauten Ton geändert, was beim anderen Ton? Schau dir dazu auch die Schwingung "
               "oben an: Ausschlag oder Abstand der Wellenberge? Weiter zum Reiter „3 Nachtest“."),
    ],
    results=[("f_leise", "Frequenz leise (Hz)"), ("f_laut", "Frequenz laut (Hz)"), ("dL_laut", "Lautstärkeänderung (dB)"),
             ("f_anders", "Frequenz anderer Ton (Hz)")],
    export_sets=[("Verlauf", [("Zeit (s)", "t_hist"), ("Frequenz (Hz)", "f_hist"), ("Lautstärke (dB)", "L_hist")]),
                 ("Marker", [("f leise (Hz)", "f_leise"), ("L leise (dB)", "L_leise"), ("f laut (Hz)", "f_laut"),
                             ("L laut (dB)", "L_laut"), ("f anders (Hz)", "f_anders"), ("L anders (dB)", "L_anders")])],
    background=[
        ("Zweck", """Tonhöhe (Frequenz) und Lautstärke (Amplitude) werden getrennt gemessen: Derselbe Ton laut und
         leise hat dieselbe Frequenz, ein anderer Ton bei gleicher Lautstärke eine andere. Das Schwingungsbild mit
         fester Achse zeigt den Unterschied direkt: größerer Ausschlag vs. engere Wellenberge."""),
        ("Fehlvorstellung", """Tonhöhe und Lautstärke werden nicht getrennt; laute Töne gelten auch als hohe Töne
         (Schecker u. a. 2018, S. 253)."""),
        ("Physik", """Die Frequenz bestimmt die Tonhöhe, die Amplitude die Lautstärke. Beim stärkeren Anschlagen einer
         Saite ändert sich die Frequenz praktisch nicht (minimal durch größere Spannung). Beim Anblasen einer Flasche
         kann zu kräftiges Blasen in einen Oberton springen – dann bewusst besprechen."""),
        ("Auswertung", """Die Frequenz wird wie im phyphox-Experiment „Audio-Autokorrelation“ bestimmt: erstes Maximum
         der Autokorrelation nach dem ersten Nulldurchgang (Bereich bis 25 ms, also ab 40 Hz). Sie wird nur
         angezeigt, wenn das Maximum mindestens 60 % des Nullwerts erreicht (sauberer Ton). Die Lautstärke ist der
         Effektivwert in dB relativ zum Vollausschlag des Mikrofons (nicht kalibriert, nur Unterschiede
         aussagekräftig)."""),
        ("Hinweise", """Kein phyphox:mini nötig, eher für Grundschule und Unterstufe. Leise Umgebung wählen. Sehr laute
         Töne können das Mikrofon übersteuern (flache Wellenberge im Schwingungsbild)."""),
    ],
))
# Zusaetzliche Container/Analyse fuer E15: Rampe bis (4800-1)/rate, Hinweis wenn kein Ton
_e15 = EXPS[-1]
_e15.containers += [c("rec_t_stop"), c("f_vis_neg")]
_e15.analysis.insert(0, F("4799/[1]", ["rate"], "rec_t_stop"))
_e15.analysis.append(F("-[1]", ["f_vis"], "f_vis_neg"))
_e15.analysis.append('<subrange>\n    <input as="from" type="value">0</input>\n    <input as="length" type="value">480</input>'
                     '\n    <input keep="true">rec_t</input>\n    <output>osc_t</output>\n</subrange>')


# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ohne-hintergrund", action="store_true", help="ohne die View '0 Hintergrund'")
    ap.add_argument("--nur", nargs="*", help="nur diese Experimente (Kurznamen)")
    ap.add_argument("--ziel", default=".", help="Zielordner (Standard: aktueller Ordner)")
    args = ap.parse_args()
    os.makedirs(args.ziel, exist_ok=True)
    for e in EXPS:
        if args.nur and e.key not in args.nur:
            continue
        path = os.path.join(args.ziel, e.key + ".phyphox")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(build(e, with_background=not args.ohne_hintergrund))
        print("geschrieben:", path)


if __name__ == "__main__":
    main()
