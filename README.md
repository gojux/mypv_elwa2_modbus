# MyPV ELWA 2 Modbus (unofficial)

Eine **inoffizielle** Home Assistant Integration für den [my-PV AC ELWA 2](https://www.my-pv.com/), die direkt per **Modbus TCP** mit dem Gerät kommuniziert – ganz ohne Umweg über die Web-API des Geräts.

> ⚠️ Diese Integration steht in keiner Verbindung zu my-PV GmbH und wird nicht von my-PV unterstützt oder gepflegt. Nutzung auf eigenes Risiko, insbesondere beim Schreiben von Registern (siehe [Hinweis zur Schreibhäufigkeit](#wichtiger-hinweis-schreibhäufigkeit-von-registern)).

## Warum diese Integration?

Es gibt bereits eine [offizielle Home Assistant Integration von my-PV](https://github.com/my-PV/home-assistant-integration). Diese Integration wurde trotzdem entwickelt, weil:

- **Modbus ist deutlich schneller als HTTP/JSON.** Die offizielle Integration spricht die Web-API des Geräts an und pollt alle 5 Sekunden per HTTP/JSON. Diese Integration liest alle relevanten Register in **einem einzigen Modbus-Request** (Register 1000–1081) und kann dadurch spürbar häufiger und mit geringerer Latenz und weniger Overhead aktualisieren.
- **Der offiziellen App/Integration fehlen Funktionen, die hier ergänzt werden:**
  - Ein **Energy-Sensor** (kWh), der aus der Leistungsmessung lokal aufintegriert wird und Neustarts übersteht – die offizielle Integration bietet nur eine Momentanleistung, aber keine Energiezählung, die z. B. im Home Assistant Energie-Dashboard genutzt werden kann.
  - Eine **beschreibbare Power-Entity (Number)**, mit der sich die Ausgangsleistung direkt in Watt vorgeben lässt – die offizielle App/Integration erlaubt nur das Setzen einer Zieltemperatur, nicht das direkte Schreiben der Leistung. Das ist z. B. für die direkte Ansteuerung durch ein Energiemanagementsystem nützlich.

## Unterstützte Geräte

Getestet und entwickelt für den **my-PV AC ELWA 2**. Andere my-PV-Geräte (AC THOR, ELWA-E, …) verwenden teilweise andere Registeradressen und werden von dieser Integration aktuell nicht unterstützt.

## Voraussetzungen

- Home Assistant **2024.11** oder neuer (wird für den „Neu konfigurieren"-Dialog benötigt).
- AC ELWA 2 im gleichen Netzwerk wie Home Assistant.
- **Modbus TCP muss am Gerät aktiviert sein:** Im Webinterface des Geräts unter *Einstellungen → Schnittstellen → Modbus* aktivieren. Standardport ist `502`, Standard-Unit-ID ist `1`.

## Installation

### Über HACS (empfohlen)

1. HACS öffnen → *Custom repositories* → dieses Repository als Typ *Integration* hinzufügen.
2. „MyPV ELWA 2 Modbus (unofficial)" installieren.
3. Home Assistant neu starten.

### Manuell

1. Den Ordner `custom_components/mypv_elwa2_modbus` in das `config/custom_components/`-Verzeichnis deiner Home-Assistant-Installation kopieren.
2. Home Assistant neu starten.

## Einrichtung (Config Flow)

1. *Einstellungen → Geräte & Dienste → Integration hinzufügen*.
2. „MyPV ELWA 2 Modbus (unofficial)" auswählen.
3. Host/IP-Adresse, Port (Standard `502`) und Modbus-Unit-ID (Standard `1`) eingeben.

Über die Optionen der Integration lassen sich zusätzlich das **Abfrageintervall** (Standard 5 s) und eine **Fallback-Maximalleistung** für die Power-Number-Entity einstellen.

### IP-Adresse/Port später ändern (Reconfigure)

Hat sich die IP-Adresse oder der Port des Geräts geändert (z. B. weil kein DHCP-Reservation eingerichtet ist), lässt sich das eingerichtete Gerät jederzeit anpassen, ohne es neu einzurichten:

1. *Einstellungen → Geräte & Dienste → MyPV ELWA 2 Modbus (unofficial)*.
2. Beim betreffenden Gerät über das Menü (⋮) **„Neu konfigurieren"** wählen.
3. Neue Host/IP-Adresse, Port bzw. Unit-ID eingeben.

Die Integration liest dabei die **Seriennummer** des Geräts (Register 1018–1025) aus und verwendet sie – nicht die IP-Adresse – als eindeutige Geräte-ID. Ein Wechsel der IP-Adresse ändert dadurch weder die `entity_id`s noch verwirft er Verlauf/Anpassungen der bestehenden Entities. Zeigt die neue Adresse auf ein Gerät mit **abweichender** Seriennummer, bricht der Vorgang sicherheitshalber mit einer Fehlermeldung ab, statt die Entities versehentlich an ein anderes Gerät zu hängen.

## Entitäten

| Plattform | Entität | Beschreibung |
|---|---|---|
| Sensor | Power | Aktuelle Ausgangsleistung (W) |
| Sensor | **Energy** ⭐ | Lokal aufintegrierte Energiemenge (kWh), neustartfest gespeichert – **nicht Teil der offiziellen Integration** |
| Sensor | Temperature / Temperature 2 | Interner (T1) und externer (T2) Temperaturfühler (°C) |
| Sensor | Voltage | Netzspannung (V, diagnostisch) |
| Sensor | Status | Detaillierter Gerätestatus (Heizt / Standby / Boost-Heizung / Fehlercodes …) |
| Sensor | Operation state | Betriebszustand gemäß Display-Icon (Standby / PV-Überschuss / Boost-Backup / Zieltemperatur erreicht / kein Steuersignal / blockiert) |
| Sensor | Operation mode | Konfigurierter Modus (Modus 1: nur ELWA bis 3,5 kW / Modus 3: ELWA + AUX-Relais bis 6,5 kW; diagnostisch, standardmäßig deaktiviert) |
| Sensor | Max. configured power / Max. power currently possible | Leistungsgrenzen (diagnostisch, standardmäßig deaktiviert) |
| Sensor | Serial number | Seriennummer des Geräts (diagnostisch); wird auch als eindeutige Geräte-ID für den Reconfigure-Flow verwendet und zusätzlich direkt im Geräteinformation-Bereich des Gerätedatensatzes angezeigt |
| Sensor | Firmware version | Controller-Firmware-Version (diagnostisch); wird zusätzlich direkt im Geräteinformation-Bereich des Gerätedatensatzes angezeigt |
| Sensor | Firmware version (power stage) / (co-controller) | Firmware-Versionen der Power-Stage- bzw. Co-Controller-Baugruppe (diagnostisch, standardmäßig deaktiviert) |
| Binary Sensor | Heating active | Gerät heizt aktuell aktiv (Status = Heat/Boost heat) |
| Binary Sensor | AUX relay active / SELV relay active | Relaisstatus (diagnostisch) |
| Binary Sensor | Device enabled | Gerät ist nicht deaktiviert (Register 1081, diagnostisch, siehe unten) |
| Number | **Power** ⭐ | Ausgangsleistung direkt in Watt vorgeben – **nicht Teil der offiziellen Integration** |
| Number | Target temperature | Ziel-/Boost-Temperatur vorgeben (analog zur Wassertemperatur-Einstellung der offiziellen App) |
| Water Heater | ELWA 2 | Ist-Temperatur (T1), Soll-Temperatur sowie Ein (`electric`) / Aus – wie in der offiziellen App |

⭐ = zusätzliche Funktionalität, die über den Funktionsumfang der offiziellen my-PV App/Integration hinausgeht.

### Hinweis zur Power-Number-Entity

Der AC ELWA 2 kann einen per Modbus gesetzten Leistungs-Sollwert nach einiger Zeit automatisch wieder verwerfen (Watchdog-Verhalten, siehe Register `1004`, „Power timeout"). Diese Integration schreibt einen aktiv gesetzten Sollwert deshalb bei jedem Abfragezyklus erneut, solange kein neuer Wert gesetzt wird – vergleichbar mit dem Heartbeat-Mechanismus, den z. B. [evcc](https://github.com/evcc-io/evcc) für dasselbe Gerät verwendet. Register `1000` ist laut offizieller Dokumentation explizit von der Einschränkung „max. 1x täglich schreiben" ausgenommen, häufiges Schreiben ist also unbedenklich.

### Hinweis zur Water-Heater-Entity und zum Ein-/Ausschalten

Die AC ELWA 2 besitzt kein eigenes Ein/Aus-Register über Modbus. Ein- und Ausschalten erfolgt deshalb – wie bei der Power-Number-Entity – über das **Power-Register (`1000`)**:

- **Ein** (`electric`): Es wird der **zuletzt gesetzte Leistungswert** (siehe unten) in Register `1000` geschrieben. Wurde noch nie ein Wert gesetzt (z. B. beim allerersten Einschalten nach der Einrichtung), wird ersatzweise die am Gerät konfigurierte maximale Leistung (Register `1014`, Fallback: die in den Optionen hinterlegte Maximalleistung) verwendet.
- **Aus**: Es wird `0` in Register `1000` geschrieben.
- Der angezeigte Betriebszustand (`electric`/`off`) wird aus dem **Status-Register (`1003`)** abgeleitet (aktiv bei den offiziellen Status-Codes „Heat" und „Boost heat").

Diese Logik entspricht der `Enable()`-Implementierung in [evcc](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go). Bewusst **nicht** verwendet wird das Gerät-eigene Register `1012` („Boost activate", der physische Boost-Backup-Knopf bzw. `/control.html?boost=1`): Dieses schaltet das Gerät in einen Modus, der elektrisch mit voller Leistung heizt und dabei **PV-Überschuss ignoriert** – das widerspricht dem Zweck einer normalen Ein/Aus-Steuerung. Das Schreiben in Register `1000` fügt sich dagegen in dieselbe Steuerungslogik ein wie die Power-Number-Entity und ein eventuell übergeordnetes Energiemanagementsystem, das PV-Überschuss weiterhin berücksichtigen kann.

### Wiederherstellung des zuletzt gesetzten Leistungswerts

Jeder über die Power-Number-Entity oder die Water-Heater-Entity gesetzte Leistungswert > 0 W wird als „zuletzt gesetzter Wert" gemerkt und in Home Assistants lokalem Storage (`.storage/`) abgelegt. Wird die ELWA über die Water-Heater-Entity aus- und anschließend wieder eingeschaltet, wird genau dieser Wert erneut geschrieben – auch dann, wenn Home Assistant zwischenzeitlich neu gestartet wurde. Das Ausschalten (Wert `0`) überschreibt den gemerkten Wert bewusst nicht.

### Register 1081 – Device state

Das offizielle my-PV-Dokument listet Register `1081` als `R/W`, Wertebereich `0, 1`, ohne weitere Beschreibung. Aus dem im selben Dokument definierten Status-Code `21` „Device disabled (devmode = 0)" lässt sich ableiten, dass Register 1081 den `devmode`-Schalter des Geräts spiegelt: **`0` = Gerät deaktiviert, `1` = Gerät aktiviert.** Diese Integration bildet das als **rein lesenden**, diagnostischen Binary Sensor „Device enabled" ab.

Bewusst **kein Schreibzugriff**: Register 1081 gehört *nicht* zu den explizit für häufiges Schreiben freigegebenen Registern (siehe nächster Abschnitt) – ein automatisiertes/wiederholtes Umschalten würde gegen die Herstellervorgabe verstoßen und den Flash-Speicher des Geräts unnötig verschleißen.

### Firmware-Version, Hardware-Version, MAC-Adresse

Die **Firmware-Version** lässt sich über Modbus auslesen und wird deshalb sowohl als Sensor als auch direkt im Geräteinformation-Bereich des Gerätedatensatzes angezeigt:

- **Controller-Firmware**: zusammengesetzt aus Hauptversion (Register `1016`) und Unterversion (Register `1028`), dargestellt als `e<Haupt>.<Unter>` (z. B. `e4.18`). Das offizielle Dokument beschreibt für beide Register nur das Rohformat „u16 (exxxxxyy)"; die genaue Zusammensetzung zu einem einzelnen Versionsstring ist nicht abschließend spezifiziert – diese Darstellung ist eine gut lesbare, aber nicht von my-PV wörtlich bestätigte Interpretation.
- **Power-Stage-Firmware** (Register `1017`, Format `ep%03d`) und **Co-Controller-Firmware** (Register `1086`, Format `ec%03d`): Diese beiden Formate sind dagegen zuverlässig bestätigt, da sie exakt den Werten entsprechen, die das Gerät selbst über seine HTTP-Statusseite (`data.jsn`) als `psversion`/`coversion` ausgibt (z. B. `ep001`, `ec005`).

**Hardware-Version und MAC-Adresse lassen sich nicht per Modbus auslesen.** Die offizielle Registertabelle des AC ELWA 2 definiert kein Hardware-/Board-Revisionsregister. Eine MAC-Adresse fehlt ebenfalls – selbst das im selben Dokument beschriebene UDP-Discovery-Protokoll liefert in seiner Antwort nur IP-Adresse, Seriennummer, Firmware-Version und ELWA-Nummer, aber keine MAC-Adresse. Beides wäre nur über das Webinterface des Geräts (HTTP) zu ermitteln, was außerhalb des Modbus-Ansatzes dieser Integration liegt.

### ⚠️ Wichtiger Hinweis: Schreibhäufigkeit von Registern

Laut offizieller my-PV-Dokumentation dürfen **alle schreibbaren Register höchstens einmal pro Tag beschrieben werden**, um den nichtflüchtigen Speicher des Geräts nicht vorzeitig zu verschleißen – **mit Ausnahme** der Register `1000` (Power), `1009`–`1012` (Uhrzeit/Boost activate) und `1078`–`1080`. Das betrifft insbesondere:

- Register `1002` (Zieltemperatur, `Number`- und `Water Heater`-Entity dieser Integration): Vermeide Automatisierungen, die diesen Wert mehrfach täglich ändern.
- Register `1014` (max. Leistung) und `1081` (Device state) werden von dieser Integration deshalb bewusst nur **gelesen**, nicht geschrieben.

## Bekannte Einschränkungen

- Getestet wurde primär gegen den AC ELWA 2 mit aktueller Firmware. Rückmeldungen zu abweichenden Firmware-Ständen sind willkommen.
- Register 1081 ist offiziell nur mit Wertebereich, aber ohne textuelle Bedeutung dokumentiert; die Zuordnung 0=deaktiviert/1=aktiviert ist eine plausible, aber nicht von my-PV wörtlich bestätigte Ableitung (siehe oben).

## Quellen & Danksagung

- **[my-PV: AC ELWA 2 – Documentation of Controls (PDF, Version 241205)](https://download.my-pv.com/acelwa2/AC_ELWA_2_Documentation-Controls_EN241205.pdf)** – offizielle, autoritative Modbus-Registertabelle inkl. Status-Codes, Grundlage für die aktuelle Registerbelegung dieser Integration.
- [evcc-io/evcc – charger/mypv.go](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go) – produktiv erprobte Modbus-Registeransteuerung des AC ELWA 2, zum Abgleich verwendet.
- [Modbuscloud – my-PV AC ELWA 2](https://www.modbuscloud.com/de/vorlagen/my-pv-ac-elwa-2-1821) – Community-Registervorlage, zum Abgleich verwendet.
- [my-PV/home-assistant-integration](https://github.com/my-PV/home-assistant-integration) – offizielle Integration, als Vorbild für den abgedeckten Funktionsumfang (Sensoren, Zieltemperatur).

## Lizenz

MIT, siehe [LICENSE](LICENSE). Diese Integration ist ein eigenständiges Community-Projekt und nicht mit my-PV GmbH assoziiert; „my-PV" und „AC ELWA" sind Marken ihrer jeweiligen Inhaber.
