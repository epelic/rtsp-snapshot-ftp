# RTSP Snapshot FTP

[Italiano](README.md) · [English](README.en.md) · **Deutsch**

<p align="center">
  <img src="assets/camera-icon.png" alt="RTSP-Snapshot-FTP-Symbol" width="180">
</p>

Eine Windows-Anwendung, die einen RTSP-Stream mit niedriger Bildrate anzeigt, ein transparentes PNG-Logo sowie Datum und Uhrzeit einblendet und regelmäßig ein JPEG-Bild per FTP hochlädt.

## Vorschau

![Hauptfenster der Anwendung](assets/app-screenshot.png)

## Funktionen

- Änderbare RTSP-URL (Standard: `rtsp://192.168.0.110/11`)
- Konfigurierbare Vorschau mit niedriger Bildrate
- Transparentes PNG-Logo, das skaliert und direkt in der Vorschau verschoben werden kann
- Datums-/Uhrzeit-Einblendung mit konfigurierbarem Format, Schriftart, Größe, Farben, Kontur und Schatten
- Zeitgesteuerte automatische sowie manuelle Uploads
- Getrennte RTSP- und FTP-Verbindungstests
- Konfigurierbare JPEG-Qualität
- Dauerhafte Einstellungen in `%APPDATA%\RTSPSnapshotFTP\settings.json`
- Optionaler automatischer Start mit Windows
- Export der Konfiguration als JSON, wahlweise mit oder ohne FTP-Passwort
- Detailliertes Protokoll für FTP-Verbindung, Anmeldung und Übertragung
- Beim Schließen mit X wird die Anwendung in den Infobereich minimiert; Video und Uploads bleiben aktiv
- Datei-Menü zum Speichern, Exportieren und Importieren der Einstellungen sowie zum Beenden
- Automatischer Start des Dienstes mit den gespeicherten FTP-Einstellungen
- RTSP über TCP, kontinuierliches Lesen zur Puffervermeidung und automatische Wiederverbindung
- Vollbildvorschau per Doppelklick; erneuter Doppelklick oder Esc zum Zurückkehren
- Infofenster mit Version, Freewaves-Copyright und Projektlink
- Das FTP-Passwort wird unverschlüsselt in der lokalen Einstellungsdatei gespeichert

## Entwicklungsumgebung

Erfordert 64-Bit-Python 3.11.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\rtsp_ftp_app.py
```

## Eigenständige EXE erstellen

In PowerShell im Projektverzeichnis ausführen:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

Das Ergebnis ist `dist\RTSP-Snapshot-FTP.exe`. Die EXE enthält Python, OpenCV, Pillow und das FFmpeg-Backend von OpenCV. Auf dem Zielcomputer mit Windows 10/11 müssen Python und FFmpeg nicht installiert sein.

## Windows-Installer erstellen

NSIS einmalig auf dem Build-Computer installieren und anschließend ausführen:

```powershell
.\build-installer.ps1
```

Der fertige Installer wird als `outputs\RTSP-Snapshot-FTP-Setup.exe` erstellt. Er installiert die Anwendung für den aktuellen Benutzer, legt Verknüpfungen auf dem Desktop und im Startmenü an und registriert die standardmäßige Windows-Deinstallation. Auf dem Zielcomputer sind keine zusätzlichen Abhängigkeiten erforderlich.

## Verwendung

1. RTSP-URL eingeben.
2. PNG-Datei und Schriftart auswählen und die Einblendungen in der Vorschau an die gewünschte Position ziehen.
3. FTP-Verbindungsdaten eingeben und **Test FTP** auswählen.
4. Upload-Intervall und JPEG-Qualität einstellen und die Einstellungen speichern. Bei späteren Starts wird der Dienst automatisch gestartet; **Start** bleibt für einen manuellen Neustart verfügbar.

Für eine möglichst zuverlässige Verbindung sollte die Kamera einen H.264-Substream mit moderater Auflösung und Bitrate bereitstellen. Herkömmliches FTP verschlüsselt weder Zugangsdaten noch Inhalte und sollte nur in einem vertrauenswürdigen Netzwerk verwendet werden.
