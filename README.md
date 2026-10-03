# MyPV ELWA 2 Modbus (unofficial)

🇩🇪 Deutsch · [🇬🇧 English](README.en.md)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gojux&repository=mypv_elwa2_modbus&category=integration)

Eine **inoffizielle** Home Assistant Integration für den [my-PV AC ELWA 2](https://www.my-pv.com/), die direkt per **Modbus TCP** mit dem Gerät kommuniziert – ganz ohne Umweg über die Web-API des Geräts.

> ⚠️ Diese Integration steht in keiner Verbindung zu my-PV GmbH und wird nicht von my-PV unterstützt oder gepflegt. Nutzung auf eigenes Risiko, insbesondere beim Schreiben von Registern (siehe [Hinweis zur Schreibhäufigkeit](#wichtiger-hinweis-schreibhäufigkeit-von-registern)).

## Warum diese Integration?

Es gibt bereits eine [offizielle Home Assistant Integration von my-PV](https://github.com/my-PV/home-assistant-integration). Diese Integration wurde trotzdem entwickelt, weil:

- **Modbus ist deutlich schneller als HTTP/JSON.** Die offizielle Integration spricht die Web-API des Geräts an und pollt alle 5 Sekunden per HTTP/JSON. Diese Integration liest alle relevanten Register in **einem einzigen Modbus-Request** (Register 1000–1086) und kann dadurch spürbar häufiger und mit geringerer Latenz und weniger Overhead aktualisieren.
- **Der offiziellen App/Integration fehlen Funktionen, die hier ergänzt werden:**
  - Ein **Energy-Sensor** (kWh), der aus der Leistungsmessung lokal aufintegriert wird und Neustarts übersteht – die offizielle Integration bietet nur eine Momentanleistung, aber keine Energiezählung, die z. B. im Home Assistant Energie-Dashboard genutzt werden kann.
  - Eine **beschreibbare Power-Entity (Number)**, mit der sich die Ausgangsleistung direkt in Watt vorgeben lässt – die offizielle App/Integration erlaubt nur das Setzen einer Zieltemperatur, nicht das direkte Schreiben der Leistung. Das ist z. B. für die direkte Ansteuerung durch ein Energiemanagementsystem nützlich.

## Unterstützte Geräte

Getestet und entwickelt für den **my-PV AC ELWA 2**. Andere my-PV-Geräte (AC THOR, ELWA-E, …) verwenden teilweise andere Registeradressen und werden von dieser Integration aktuell nicht unterstützt.

## Voraussetzungen

- Home Assistant **2026.5** oder neuer.
- AC ELWA 2 im gleichen Netzwerk wie Home Assistant.
- **Modbus TCP muss am Gerät aktiviert sein:** Im Webinterface des Geräts unter *Einstellungen → Schnittstellen → Modbus* aktivieren. Standardport ist `502`, Standard-Unit-ID ist `1`.

## Installation

### Über HACS (empfohlen)

1. Den HACS-Button oben anklicken (alternativ in HACS → *Custom repositories* dieses Repository als Typ *Integration* hinzufügen).
2. „MyPV ELWA 2 Modbus (unofficial)" installieren.
3. Home Assistant neu starten.

### Manuell

1. Den Ordner `custom_components/mypv_elwa2_modbus` in das `config/custom_components/`-Verzeichnis deiner Home-Assistant-Installation kopieren.
2. Home Assistant neu starten.

## Einrichtung (Config Flow)

1. *Einstellungen → Geräte & Dienste → Integration hinzufügen*.
2. „MyPV ELWA 2 Modbus (unofficial)" auswählen.
3. Host/IP-Adresse, Port (Standard `502`) und Modbus-Unit-ID (Standard `1`) eingeben.

Über die Optionen der Integration lassen sich zusätzlich das **Abfrageintervall** (Standard 5 s), eine **Fallback-Maximalleistung** für die Power-Number-Entity sowie – optional – eine **Netzeinspeisung-Entity** für die [automatische Steuerung](#automatische-netzeinspeisung-steuerung) einstellen. Liefert deine Netzeinspeisung-Entity die umgekehrte Vorzeichenkonvention, aktivierst du dort außerdem **„Vorzeichen der Netzeinspeisung-Entity umkehren“**.

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
| Number | **Power** ⭐ | Ausgangsleistung direkt in Watt vorgeben – **nicht Teil der offiziellen Integration** |
| Number | Target temperature | Ziel-/Boost-Temperatur vorgeben (analog zur Wassertemperatur-Einstellung der offiziellen App) |
| Number | **Auto control reserve** ⭐ | Überschuss (W), der bei automatischer Steuerung immer unangetastet bleiben soll (Standard 100 W) |
| Number | **Auto control max. power** ⭐ | Obergrenze (W), bis zu der die automatische Steuerung regeln darf |
| Number | **Auto control rate limit** ⭐ | Mindestabstand (s) zwischen zwei Schreibvorgängen der automatischen Steuerung (Standard 1 s) |
| Number | **Auto control smoothing** ⭐ | Glättungszeitraum (s) für den Netzeinspeisung-Sensor, `0`–`300`, Standard 5 s (`0` = aus) |
| Switch | **Device enabled** ⭐ | Gerät selbst aktivieren/deaktivieren (Register 1081, siehe unten) – **nicht Teil der offiziellen Integration** |
| Switch | **Auto control** ⭐ | Automatische Netzeinspeisung-Steuerung aktivieren/deaktivieren – **nicht Teil der offiziellen Integration** |
| Water Heater | ELWA 2 | Ist-Temperatur (T1), Soll-Temperatur sowie Ein (`electric`) / Aus – wie in der offiziellen App |

⭐ = zusätzliche Funktionalität, die über den Funktionsumfang der offiziellen my-PV App/Integration hinausgeht.

### Optimistisches Caching: Power-Number- und Water-Heater-Entity

Leistungs-Sollwert und Ein/Aus-Status würden bei einer rein Live-Register-basierten Anzeige leicht "hin- und herspringen" – z. B. weil der `Status`-Code bei schwankendem PV-Überschuss normal zwischen „Heat"/„Boost heat" und „Standby" pendelt, oder weil kurz nach einem Schreibvorgang die Live-Ablesung noch nicht den gerade gesetzten Wert zeigt. Diese Integration vermeidet das durch zwei Mechanismen:

**1. Power-Number-Entity zeigt den kommandierten, nicht den live gemessenen Wert.** Solange wir selbst einen Sollwert aktiv steuern, zeigt die Entity genau diesen Wert (`coordinator.power_setpoint`) statt der Live-Ablesung von Register `1000`. Ist die ELWA aus, wird `0` angezeigt. Heizt das Gerät autonom (siehe Punkt 2), zeigt die Entity die Live-Ablesung, da in diesem Fall kein eigener Sollwert aktiv ist.

**2. Der Ein/Aus-Status der Water-Heater-Entity ist ein "Latch"**, kein direktes Abbild des Status-Registers:

- **Ein** (`electric`) wird gesetzt durch: eine explizite Aktion in Home Assistant (Water-Heater „Ein" oder Power-Number > 0 W), **oder** automatisch erkannt, wenn das Gerät von „Aus" auf einen heizenden Status wechselt (Status-Code „Heat" oder „Boost heat") – z. B. wenn die geräteeigene automatische PV-Überschuss-Regelung von selbst zu heizen beginnt, ohne dass Home Assistant etwas geschrieben hätte.
- **Aus** wird **nur** gesetzt durch: eine explizite Aktion in Home Assistant (Water-Heater „Aus"), **oder** automatisch erkannt, wenn das Gerät „kein Steuersignal" (`no_control`) oder „deaktiviert" (`device_disabled`) meldet.
- Ein normales Pendeln zwischen „Heat" und „Standby" während laufendem Betrieb ändert den Ein/Aus-Status **nicht** – dadurch entsteht kein Flackern.

**Die Kopplung zwischen Power-Number und Water-Heater-Entity ist bewusst einseitig:** Water-Heater „Aus" setzt die Power-Number-Anzeige auf `0` (da sie ohne aktiven Sollwert auf den Aus-Zustand zurückfällt). Umgekehrt schaltet ein manuelles Setzen der Power-Number auf `0` den Water-Heater **nicht** aus – es reduziert nur die Leistung auf `0 W`, während „Ein" bestehen bleibt, genauso wie ein von der automatischen Steuerung berechneter Wert von `0 W` (siehe [Automatische Netzeinspeisung-Steuerung](#automatische-netzeinspeisung-steuerung)). Ein positiver Wert an der Power-Number schaltet den Water-Heater dagegen weiterhin ein, falls er noch aus war.

**Kein Dauerschreiben mehr im Aus-Zustand:** Solange „Ein", schreibt die Integration den Leistungs-Sollwert wie bisher bei jedem Abfragezyklus erneut in Register `1000` (Heartbeat, s.u.) – das gilt auch, wenn der Sollwert dabei `0 W` ist. Solange „Aus", wird beim Übergang genau **einmal** `0` geschrieben und danach – bis zur nächsten expliziten Aktion – **nicht** mehr weiter auf Register `1000` geschrieben, damit Home Assistant eine eventuelle automatische PV-Überschuss-Regelung des Geräts nicht fortlaufend überschreibt.

Ein- und Ausschalten erfolgt dabei weiterhin über dasselbe **Power-Register (`1000`)**, das auch die Power-Number-Entity nutzt (Ein: zuletzt gesetzter Leistungswert bzw. Fallback auf die Maximalleistung; Aus über die Water-Heater-Entity: `0`; die Power-Number auf `0` schaltet dagegen nicht aus) – analog zur `Enable()`-Implementierung in [evcc](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go). Bewusst **nicht** verwendet wird das Gerät-eigene Register `1012` („Boost activate", physischer Boost-Backup-Knopf bzw. `/control.html?boost=1`), da dieses den PV-Überschuss ignoriert und mit voller Leistung heizt.

### Wiederherstellung nach einem Home-Assistant-Neustart

Sowohl der **zuletzt gesetzte Leistungswert** (jeder über Power-Number oder Water-Heater gesetzte Wert > 0 W) als auch der **Ein/Aus-Status** werden in Home Assistants lokalem Storage (`.storage/`) abgelegt und beim Start wiederhergestellt. Ein Neustart während des Betriebs führt also nicht dazu, dass die Water-Heater-Entity fälschlich auf „Aus" zurückfällt, selbst wenn das Gerät im Moment des Neustarts gerade im (normalen) Standby zwischen zwei Heizphasen ist. Das Ausschalten überschreibt den gemerkten Leistungswert bewusst nicht.

## Automatische Netzeinspeisung-Steuerung

Statt die Leistung über eine eigene Automation zu berechnen und zu setzen, kann die Integration selbst auf Änderungen eines Netzeinspeisung-Sensors reagieren und die Leistung direkt berechnen und schreiben – ereignisgesteuert, nicht erst beim nächsten Abfragezyklus.

### Einrichtung

1. In den **Optionen** der Integration die **Netzeinspeisung-Entity** auswählen (ein Sensor in Watt). Standard-Vorzeichenkonvention: positiv = Überschuss/Einspeisung, negativ = Bezug. Nutzt dein Sensor die umgekehrte Konvention, aktiviere **„Vorzeichen der Netzeinspeisung-Entity umkehren"**.
2. Über die neue **„Auto control"-Switch-Entity** die automatische Steuerung aktivieren.

Solange „Auto control" aktiv ist, werden manuelle Änderungen an der Power-Number-Entity **ignoriert** – sie zeigt stattdessen fortlaufend den von der automatischen Steuerung berechneten Wert an.

### Berechnung

Bei jeder Änderung der Netzeinspeisung-Entity wird berechnet:

```
Netzeinspeisung_glatt = min( gleitender_Durchschnitt(Netzeinspeisung_roh, Glättungszeitraum), Netzeinspeisung_roh )
neue_Leistung          = aktuelle_Leistung + Netzeinspeisung_glatt − Reserve
```

Die Vorzeichen-Umkehr (falls aktiviert) wird **vor** dieser Berechnung angewendet, sodass Glättung, Minimalwert-Bildung und die Leistungsformel durchgängig mit derselben Vorzeichenkonvention arbeiten.

- **Auto control smoothing** (Number-Entity, Standard 5 s, `0` = deaktiviert): Zeitraum für einen gleitenden Durchschnitt über die rohen Netzeinspeisung-Werte. Damit kurze Sprünge nach oben (z. B. eine vorbeiziehende Wolkenlücke) nicht sofort zu unnötigem Nachregeln führen, wird nicht der Durchschnitt direkt verwendet, sondern das **Minimum aus Durchschnitt und aktuellem Rohwert** – vorzeichenrichtig verglichen, also z. B. `-10` kleiner als `-5`, nicht nach Betrag. Ein plötzlicher **Einbruch** des Überschusses (oder ein Umschwung in Netzbezug) schlägt dadurch trotz Glättung **sofort** durch, da in diesem Fall der (noch nicht angepasste) Durchschnitt höher als der aktuelle Rohwert wäre und deshalb nicht verwendet wird.
- **Reserve** (Number-Entity „Auto control reserve", Standard 100 W): der Überschuss, der immer unangetastet bleiben soll – ein Sicherheitsabstand gegen Netzbezug durch Mess- oder Regelverzögerung.
- **Auto control max. power**: harte Obergrenze für den berechneten Wert (zusätzlich zur ggf. vom Gerät gemeldeten Leistungsgrenze).
- **Auto control rate limit** (Standard 1 s): Mindestabstand zwischen zwei Schreibvorgängen, falls die Netzeinspeisung-Entity sehr häufig aktualisiert. Die Glättung läuft davon unabhängig bei jeder Sensor-Aktualisierung weiter, auch wenn ein einzelner Durchlauf wegen des Rate-Limits nicht zu einem Schreibvorgang führt.

Das ist ein einfacher proportionaler Regler mit Reserve/Totzone: Bei Überschuss über der Reserve wird die Leistung erhöht, bei Überschuss unter der Reserve (oder Netzbezug) verringert – der Regelkreis pendelt sich so ein, dass genau die konfigurierte Reserve an Überschuss ins Netz fließt.

### Zusammenspiel mit Wasser-Heater und manueller Steuerung

- **Der „Auto control"-Schalter ist eine dauerhafte Einstellung, unabhängig vom Ein/Aus-Zustand des Wasser-Heaters.** Ist die Wasser-Heater-Entity „Aus" (egal ob explizit ausgeschaltet oder automatisch als „Aus" erkannt, z. B. bei `no_control`/`device_disabled`), **pausiert** lediglich die Funktion – es wird nichts mehr an die ELWA geschrieben. Der Schalter selbst bleibt dabei eingeschaltet.
- Wird der Wasser-Heater danach wieder „Ein" geschaltet, **läuft die automatische Steuerung von selbst wieder an**, sofern „Auto control" weiterhin aktiviert ist – ein erneutes Betätigen des Schalters ist nicht nötig.
- Ein von der automatischen Steuerung berechneter Wert von `0 W` schaltet den Wasser-Heater **nicht** aus – „kein Überschuss gerade" ist ein normaler, vorübergehender Zustand, in dem die automatische Steuerung weiterläuft und auf zurückkehrenden Überschuss wartet.
- Eigene Automationen, die bisher die Leistung berechnet und gesetzt haben, sollten deaktiviert werden, sobald „Auto control" verwendet wird, um Doppelsteuerung zu vermeiden.

Register `1000` ist laut offizieller Dokumentation explizit von der Einschränkung „max. 1× täglich schreiben" ausgenommen, das beschriebene Heartbeat- bzw. einmalige Schreiben ist also unbedenklich.

### Register 1081 – Device state

Das offizielle my-PV-Dokument listet Register `1081` als `R/W`, Wertebereich `0, 1`, ohne weitere Beschreibung. Aus dem im selben Dokument definierten Status-Code `21` „Device disabled (devmode = 0)" lässt sich ableiten, dass Register 1081 den `devmode`-Schalter des Geräts spiegelt: **`0` = Gerät deaktiviert, `1` = Gerät aktiviert.**

Diese Integration bildet das als **Switch-Entity „Device enabled"** ab, mit der sich das Gerät selbst ein- und ausschalten lässt – das ist ein anderes Konzept als das Ein/Aus der Water-Heater-Entity: Diese fordert nur einen Leistungswert über Register `1000` an, während das Gerät selbst aktiviert bleibt; der Switch hier deaktiviert das Gerät vollständig, so wie es auch über das Webinterface des Geräts möglich wäre.

**Wichtig zur Schreibhäufigkeit:** Register `1081` gehört *nicht* zu den explizit für häufiges Schreiben freigegebenen Registern (siehe nächster Abschnitt) – anders als das Power-Register wird es deshalb **nie automatisch** bei jedem Abfragezyklus neu geschrieben, sondern ausschließlich beim expliziten Umschalten des Switches. Verwende diesen Switch nur für gelegentliche, manuelle Schaltvorgänge – binde ihn **nicht** in Automatisierungen ein, die ihn häufig (mehrfach täglich) umschalten würden, um den Flash-Speicher des Geräts nicht unnötig zu verschleißen.

### Firmware-Version, Hardware-Version, MAC-Adresse

Die **Firmware-Version** lässt sich über Modbus auslesen und wird deshalb sowohl als Sensor als auch direkt im Geräteinformation-Bereich des Gerätedatensatzes angezeigt:

- **Controller-Firmware**: zusammengesetzt aus Hauptversion (Register `1016`) und Unterversion (Register `1028`), dargestellt als `e<Haupt>.<Unter>` (z. B. `e4.18`). Das offizielle Dokument beschreibt für beide Register nur das Rohformat „u16 (exxxxxyy)"; die genaue Zusammensetzung zu einem einzelnen Versionsstring ist nicht abschließend spezifiziert – diese Darstellung ist eine gut lesbare, aber nicht von my-PV wörtlich bestätigte Interpretation.
- **Power-Stage-Firmware** (Register `1017`, Format `ep%03d`) und **Co-Controller-Firmware** (Register `1086`, Format `ec%03d`): Diese beiden Formate sind dagegen zuverlässig bestätigt, da sie exakt den Werten entsprechen, die das Gerät selbst über seine HTTP-Statusseite (`data.jsn`) als `psversion`/`coversion` ausgibt (z. B. `ep001`, `ec005`).

**Hardware-Version und MAC-Adresse lassen sich nicht per Modbus auslesen.** Die offizielle Registertabelle des AC ELWA 2 definiert kein Hardware-/Board-Revisionsregister. Eine MAC-Adresse fehlt ebenfalls – selbst das im selben Dokument beschriebene UDP-Discovery-Protokoll liefert in seiner Antwort nur IP-Adresse, Seriennummer, Firmware-Version und ELWA-Nummer, aber keine MAC-Adresse. Beides wäre nur über das Webinterface des Geräts (HTTP) zu ermitteln, was außerhalb des Modbus-Ansatzes dieser Integration liegt.

### Wichtiger Hinweis: Schreibhäufigkeit von Registern

Laut offizieller my-PV-Dokumentation dürfen **alle schreibbaren Register höchstens einmal pro Tag beschrieben werden**, um den nichtflüchtigen Speicher des Geräts nicht vorzeitig zu verschleißen – **mit Ausnahme** der Register `1000` (Power), `1009`–`1012` (Uhrzeit/Boost activate) und `1078`–`1080`. Das betrifft insbesondere:

- Register `1002` (Zieltemperatur, `Number`- und `Water Heater`-Entity dieser Integration): Vermeide Automatisierungen, die diesen Wert mehrfach täglich ändern.
- Register `1081` (Device state, `Switch`-Entity „Device enabled"): wird nur beim expliziten Umschalten geschrieben, nie automatisch bei jedem Abfragezyklus – trotzdem nicht für häufig laufende Automatisierungen verwenden.
- Register `1014` (max. Leistung) wird von dieser Integration deshalb bewusst nur **gelesen**, nicht geschrieben.

## Bekannte Einschränkungen

- Getestet wurde primär gegen den AC ELWA 2 mit aktueller Firmware. Rückmeldungen zu abweichenden Firmware-Ständen sind willkommen.
- Register 1081 ist offiziell nur mit Wertebereich, aber ohne textuelle Bedeutung dokumentiert; die Zuordnung 0=deaktiviert/1=aktiviert ist eine plausible, aber nicht von my-PV wörtlich bestätigte Ableitung (siehe oben).

## Warum nicht das neue HA-Modbus-Backend (2026.9)?

Home Assistant 2026.9 hat ein neues, Config-Flow-basiertes Modbus-Backend eingeführt (Bibliothek [`modbus-connection`](https://home-assistant-libs.github.io/modbus-connection/), intern jetzt [`tmodbus`](https://github.com/wlcrs/tmodbus) statt `pymodbus`) – siehe den [Release-Blogpost](https://www.home-assistant.io/blog/2026/09/02/release-20269/#modernizing-modbus) und den [Entwickler-Blogpost „Modernizing Modbus"](https://developers.home-assistant.io/blog/2026/07/05/modernizing-modbus). Es löst zwei Probleme:

1. Nutzer richten Geräte per UI-Config-Flow ein, statt Registerkarten händisch in YAML zu pflegen.
2. Mehrere Integrationen, die sich einen **physischen Bus** teilen (z. B. ein RS-485-Bus oder ein TCP-Gateway mit mehreren Geräten unterschiedlicher Hersteller), bekommen dafür eine gemeinsam genutzte Verbindung ("Unit"), statt sich gegenseitig zu blockieren.

Für diese Integration bringt das aktuell keinen Mehrwert:

- **Punkt 1 haben wir bereits** – diese Integration nutzt von Anfang an einen Config-Flow, keine YAML-Registerkarten.
- **Punkt 2 trifft praktisch nicht zu** – die AC ELWA 2 hat eine eigene IP-Adresse und einen eigenen Modbus-TCP-Server. Es gibt keinen anderen Consumer, mit dem sich eine Verbindung teilen ließe.
- Das neue Backend ist zum jetzigen Zeitpunkt erst etwa einen Monat alt; `modbus-connection` und das vorgeschlagene Vorlagen-Muster (eigenständige Device-Library + vendorisierte HACS-Integration) sind ein "Let's get building"-Aufruf, kein etabliertes Muster.
- Eine Portierung würde die Mindest-HA-Version deutlich anheben (aktuell `2026.5.0`) und eine Aufteilung in eine eigenständige Device-Library + Integration erfordern – unverhältnismäßig für eine kleine inoffizielle Integration ohne den eigentlichen Nutzen (geteilte Verbindungen).

Diese Integration bleibt daher vorerst bei `pymodbus`. Geplant ist, ein paar weitere Home-Assistant-Releases abzuwarten und einen Wechsel auf das neue Backend rund um den Jahreswechsel 2026/2027 zu prüfen – sofern das Ökosystem bis dahin reifer ist und sich ein konkreter Nutzen ergibt (z. B. Wunsch nach Aufnahme in HA Core).

## Quellen & Danksagung

- **[my-PV: AC ELWA 2 – Documentation of Controls (PDF, Version 241205)](https://download.my-pv.com/acelwa2/AC_ELWA_2_Documentation-Controls_EN241205.pdf)** – offizielle, autoritative Modbus-Registertabelle inkl. Status-Codes, Grundlage für die aktuelle Registerbelegung dieser Integration.
- [evcc-io/evcc – charger/mypv.go](https://github.com/evcc-io/evcc/blob/master/charger/mypv.go) – produktiv erprobte Modbus-Registeransteuerung des AC ELWA 2, zum Abgleich verwendet.
- [Modbuscloud – my-PV AC ELWA 2](https://www.modbuscloud.com/de/vorlagen/my-pv-ac-elwa-2-1821) – Community-Registervorlage, zum Abgleich verwendet.
- [my-PV/home-assistant-integration](https://github.com/my-PV/home-assistant-integration) – offizielle Integration, als Vorbild für den abgedeckten Funktionsumfang (Sensoren, Zieltemperatur).

## Lizenz

MIT, siehe [LICENSE](LICENSE). Diese Integration ist ein eigenständiges Community-Projekt und nicht mit my-PV GmbH assoziiert; „my-PV" und „AC ELWA" sind Marken ihrer jeweiligen Inhaber.
