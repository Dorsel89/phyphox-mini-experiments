# Erdrotation mit dem LSM6DSR messen

Kurzbeschreibung zu `Earth_Rotation_LSM6DSR.phyphox`.

## 1. Worum es geht

Die Erde dreht sich einmal pro Sterntag (86164,1 s) um sich selbst:

```
Ω = 360° / 86164,1 s = 0,0041781 °/s = 15,041 °/h = 7,2921·10⁻⁵ rad/s
```

Ein Gyroskop, das ruhig auf dem Tisch liegt, misst davon nur die **lotrechte
Komponente**. Die hängt vom Breitengrad φ ab:

```
Ω_vertikal = Ω · sin(φ)
```

Am Äquator ist sie null, am Pol maximal. Bei φ = 51° sind es 0,00325 °/s.

## 2. Warum der Messbereich alles entscheidet

Der LSM6DSR liefert 16-Bit-Rohwerte. Die Auflösung pro Bit hängt am gewählten
Messbereich:

| Messbereich | Auflösung | Erdrotation entspricht |
|---|---|---|
| **125 °/s** | **4,375 mdps/LSB** | **0,96 LSB** |
| 250 °/s | 8,75 mdps/LSB | 0,48 LSB |
| 2000 °/s | 70 mdps/LSB | 0,06 LSB |
| 4000 °/s | 140 mdps/LSB | 0,03 LSB |

Die gesamte Erdrotation ist also **ungefähr ein einziges Sensorbit** — und das
auch nur im empfindlichsten Bereich. Deshalb `range_gyr = 0x02` (125 °/s). Mit
dem in den anderen phyphox:mini-Experimenten üblichen 4000-°/s-Bereich wäre das Signal
32-mal kleiner als ein Bit und grundsätzlich nicht messbar.

Dass ein Einzelwert das Signal nicht auflöst, ist unkritisch: Das Eigenrauschen
des Sensors beträgt bei 104 Hz rund 27 mdps pro Sample, also etwa 6 LSB. Dieses
Rauschen wirkt als Dither, wodurch der Mittelwert vieler Samples deutlich feiner
auflöst als ein einzelnes Bit.

## 3. Warum nicht die maximale Datenrate

Die Datei nutzt bewusst **104 Hz**, nicht 6667 Hz. Der Grund: Beim Mitteln von
weißem Rauschen über die Zeit T gilt

```
σ_Mittelwert ≈ Rauschdichte / √(2·T)
```

Darin kommt die **Abtastrate nicht vor**. Eine höhere Rate liefert zwar mehr
Samples, aber jedes einzelne ist entsprechend breitbandiger und damit
verrauschter. Beide Effekte heben sich exakt auf. Für einen Mittelwert über
45 s ist das Ergebnis bei 104 Hz und bei 6667 Hz identisch.

Die hohe Rate bringt also nichts, kostet aber:

- **BLE-Last.** Wie viel, hängt stark am Format. `IMU_lsm6dsr_int.phyphox`
  (nur Beschleunigungssensor, int16, 40 Samples pro Paket) kommt bei 6667 Hz auf
  167 Notifications/s à 244 Byte, also rund 41 kB/s — das läuft nachweislich
  problemlos. Dieses Experiment nutzt dagegen float mit 15 Samples pro Paket und
  zwei Sensoren gleichzeitig: bei 6667 Hz wären das 889 Notifications/s à
  240 Byte und rund 213 kB/s, gut das Fünffache. Ob die Verbindung das trägt,
  ist offen — getestet ist es nicht. Wichtig dabei: Die Firmware prüft den
  Rückgabewert von `bt_gatt_notify()` nicht. Ein überlaufender Sendepuffer
  verwirft Pakete **stillschweigend**, Verluste melden sich also nicht als
  Fehler, sondern fallen nur über die Stichprobenzahl in der Ergebnisansicht auf.
- **Aliasing.** Die interne Bandbreite des Sensors wächst mit der Abtastrate.
  Bei niedriger Rate filtert der Sensor Gebäude- und Tischvibrationen besser weg,
  bevor sie sich in das Messband falten können.
- **Stromverbrauch.**

Bei 104 Hz sind es 6,9 Notifications/s je Sensor und rund 3,3 kB/s — völlig
unkritisch.

Wenn du trotzdem mehr Samples willst: Im `<config>` genügt es, das zweite Byte
zu ändern (`0x05` = 208 Hz, `0x06` = 416 Hz und so weiter). Am Ergebnis sollte
sich nichts ändern — falls doch, wäre das ein interessanter Befund und ein
Hinweis darauf, dass das Rauschen eben nicht weiß ist.

## 4. Das Messverfahren: ABBA-Umkehr

Das eigentliche Problem ist nicht das Rauschen, sondern der **Nullpunktfehler**.
Der liegt beim LSM6DSR typisch im Bereich von 1 °/s, also rund das 250-fache des
gesuchten Signals. Ihn wegzukalibrieren ist aussichtslos, weil er mit der
Temperatur driftet.

Der Trick: Beim Umdrehen des phyphox:mini wechselt das **Erdsignal** das Vorzeichen, der
**Sensor-Offset** nicht, weil er eine Eigenschaft des Bauteils ist und fest im
Gehäusekoordinatensystem sitzt.

```
Lage A (flach):      ω_A = +Ω_vertikal + b
Lage B (kopfüber):   ω_B = −Ω_vertikal + b
                     ω_A − ω_B = 2 · Ω_vertikal      ← b fällt heraus
```

Gemessen wird in der Reihenfolge **A – B – B – A**, praktisch also: flach (45 s),
umdrehen, kopfüber (90 s), zurückdrehen, flach (45 s). Diese Symmetrie ist kein
Zufall. Der zeitliche Schwerpunkt der A-Fenster liegt genau auf dem der
B-Fenster, wodurch zusätzlich zum konstanten Offset auch eine **lineare Drift**
herausfällt — und thermische Drift ist über wenige Minuten in guter Näherung
linear.

```
Δω = (A1 + A2)/2 − B = 2 · Ω · sin(φ)
Ω  = |Δω| / (2·|sin φ|)
```

## 5. Verarbeitungskette in der Datei

```
BLE cddf1000 ──┬─ offset 0,  repeating 16 ──→ gyr_t   (Zeit)
   (Gyroskop)  ├─ offset 4,  repeating 16 ──→ gyr_x
               ├─ offset 8,  repeating 16 ──→ gyr_y
               └─ offset 12, repeating 16 ──→ gyr_z

BLE cddf1001 ──── genauso ──→ acc_t, acc_x, acc_y, acc_z
```

Jede Notification enthält 15 Frames à 16 Byte. `repeating="16"` bedeutet: Der
Konverter liest ab `offset` und springt dann in 16-Byte-Schritten weiter.

Danach, einmal pro Sekunde (`<analysis sleep="1">`):

1. **Fenstergrenzen** `b1…b6` aus Fensterlänge und Umdrehpause berechnen.
2. **Phase und Countdown** aus der Experimentzeit (`timer`) ableiten.
3. **`rangefilter`** schneidet die drei Messfenster aus dem Datenstrom. Der
   Zeitstempel ist der erste Eingang mit `min`/`max`, die drei Achsen laufen als
   weitere Eingänge mit — es kommen also nur Samples innerhalb des Fensters
   durch.
4. **`average`** je Fenster und Achse → neun Mittelwerte.
5. **`count`** je Fenster, um Paketverluste sichtbar zu machen.
6. **ABBA-Differenz** je Achse: `(A1 + A2)/2 − B`.
7. **Projektion auf die Lotrechte** (siehe unten).
8. **Skalierung** mit `1/(2·sin φ)` und Umrechnung in °/h und Tageslänge.

### Die Projektion

Ich weiß nicht, wie die Platine im Gehäuse verbaut ist, also welche Achse beim
flachen Hinlegen nach oben zeigt. Statt dich raten zu lassen, ermittelt das
Experiment die Lotrechte aus dem **Beschleunigungssensor** während Fenster A1:

```
n̂ = a / |a|                         (Einheitsvektor nach oben)
Δω_proj = (Δω_x·a_x + Δω_y·a_y + Δω_z·a_z) / |a|
```

Wichtig ist, dass für **beide** Lagen auf dieselbe körperfeste Richtung
projiziert wird (die aus A1). Würde man in Lage B die dort gemessene Lotrechte
verwenden, fiele das Signal heraus und man erhielte stattdessen den Offset.

Zwei angenehme Nebeneffekte: Der phyphox:mini muss nicht exakt waagerecht liegen, und ein
etwaiger konstanter Skalenfehler des Beschleunigungssensors kürzt sich in `n̂`
heraus. Weil die Vorzeichenkonvention des Beschleunigungssensors nicht
garantiert ist, wird am Ende der Betrag genommen — die Erdrotationsrate ist
definitionsgemäß positiv.

Zur Kontrolle zeigt die Ansicht „Result" zusätzlich die Umkehrdifferenz **je
Achse**. Dort muss genau eine Achse das volle Signal zeigen und die beiden
anderen nahe null liegen.

## 6. Erwartete Genauigkeit

Mit der Rauschdichte des LSM6DSR von rund 3,8 mdps/√Hz und den
Standardeinstellungen (45 s Fenster):

| Größe | Wert |
|---|---|
| Signal Δω bei φ = 51° | 6,49 mdps |
| Rauschen σ auf Δω | ≈ 0,40 mdps |
| Signal-Rausch-Verhältnis | ≈ 16 |
| Erwartete Streuung | **5 bis 8 %** |

Längere Fenster verbessern das mit √T, sammeln aber mehr thermische Drift an.
Der Bereich 30 bis 90 s ist ein sinnvoller Kompromiss. Realistisch ist, dass du
den Wert auf etwa 10 % triffst und mehrere Durchläufe brauchst, um zu sehen, wie
stabil das Ergebnis wirklich ist.

## 7. Praktische Hinweise

- **Vibrationsfreier Untergrund.** Kein Tisch, an dem jemand sitzt oder sich
  aufstützt. Der Boden ist besser als ein Schreibtisch.
- **Nur während Phase 3 und 5 umdrehen.** In den Messfenstern darf der phyphox:mini nicht
  berührt werden.
- **Der Messbereich von 125 °/s wird beim Umdrehen von Hand übersteuert.** Das
  ist unkritisch, weil die Umdrehphasen aus den Mittelwerten herausgeschnitten
  werden — aber eben nur dann, wenn du in der richtigen Phase drehst.
- **Temperatur konstant halten.** Den phyphox:mini vorher einige Minuten liegen lassen,
  nicht in der Hand aufwärmen, keine direkte Sonne, keine Heizung.
- **Breitengrad vor dem Start eintragen** (Ansicht „Settings"). Südhalbkugel:
  negativer Wert.
- **Stichprobenzahl prüfen.** Die Ansicht „Result" zeigt die Samples pro Fenster.
  Erwartet werden Fensterlänge × 104. Deutlich weniger bedeutet Paketverluste,
  und dann ist das Ergebnis nicht belastbar.

## 8. Verwandte Umsetzung

Dieselbe Methode mit Smartphone-Gyroskopen:
<https://garycahill1978.github.io/earth-rotation-phyphox/> — dort mit 15-s-Fenstern
und dem Ergebnis, dass es stark vom jeweiligen Sensor abhängt, ob sich das Signal
überhaupt auflösen lässt. Als Referenz wird ein Murata SCH16T-K01 mit
0,004993 ± 0,000141 °/s genannt.
