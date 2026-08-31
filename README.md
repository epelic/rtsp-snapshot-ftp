# RTSP Snapshot FTP

**Italiano** · [English](README.en.md) · [Deutsch](README.de.md)

<p align="center">
  <img src="assets/camera-icon.png" alt="Icona RTSP Snapshot FTP" width="180">
</p>

Applicazione Windows che visualizza a basso framerate un flusso RTSP, applica un logo PNG e data/ora, quindi carica periodicamente un JPEG via FTP.

## Anteprima

![Schermata principale dell'applicazione](assets/app-screenshot.png)

## Funzioni

- URL RTSP modificabile (predefinito `rtsp://192.168.0.110/11`)
- anteprima configurabile a basso framerate
- logo PNG trasparente, ridimensionabile e trascinabile nell'anteprima
- data/ora con formato, font, dimensione, colori, contorno e ombra configurabili
- upload automatico temporizzato o manuale
- test separati RTSP e FTP
- qualità JPEG configurabile
- impostazioni persistenti in `%APPDATA%\RTSPSnapshotFTP\settings.json`
- avvio automatico opzionale con Windows
- esportazione della configurazione JSON, con scelta se includere la password FTP
- log dettagliato di connessione, autenticazione e trasferimento FTP
- chiusura con la X nell'area di notifica, mantenendo attivi video e upload
- menu File per salvare, esportare, caricare impostazioni e uscire realmente
- avvio automatico del servizio con le impostazioni FTP salvate
- trasporto RTSP/TCP, lettura continua anti-buffer e riconnessione automatica
- anteprima a schermo intero con doppio clic; doppio clic o Esc per tornare
- finestra Info con versione, copyright Freewaves e collegamento al progetto
- password salvata localmente nel file impostazioni (non cifrata)

## Avvio per sviluppo

Richiede Python 3.11 a 64 bit.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\rtsp_ftp_app.py
```

## Creazione EXE standalone

Da PowerShell, nella cartella del progetto:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

Il risultato sarà `dist\RTSP-Snapshot-FTP.exe`. L'EXE include Python, OpenCV, Pillow e il backend FFmpeg di OpenCV: sul PC Windows 10/11 finale non occorre installare Python o FFmpeg.

## Creazione installer Windows

Installare una sola volta NSIS sul PC usato per compilare, poi eseguire:

```powershell
.\build-installer.ps1
```

Il file `outputs\RTSP-Snapshot-FTP-Setup.exe` è l'installer finale per gli utenti. Installa l'applicazione per l'utente corrente, crea i collegamenti Desktop/Menu Start e aggiunge la disinstallazione standard di Windows. Sul PC finale non è necessaria alcuna dipendenza.

## Uso

1. Inserire l'URL RTSP.
2. Scegliere il PNG e il font. Trascinare gli overlay nell'anteprima.
3. Inserire i parametri FTP e premere **Test FTP**.
4. Impostare intervallo e qualità JPEG, quindi salvare le impostazioni. Ai successivi avvii il servizio partirà automaticamente; **Start** resta disponibile per il riavvio manuale.

Per maggiore affidabilità, configurare sulla telecamera un sottoflusso H.264 a risoluzione e bitrate moderati. FTP classico non cifra credenziali o contenuto; usarlo solo su rete fidata.
