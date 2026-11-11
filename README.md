# TwgIBMiControl

Monitoraggio NIS2 per IBM i (AS/400): dashboard web, allarmi via email, storico
allarmi e report PDF mensile per ogni sistema.

## Cosa controlla (ogni pochi minuti, soglie modificabili)

**Spazio e dischi**
- Occupazione ASP di sistema e storage temporaneo
- Unità disco guaste, non pronte, in ricostruzione
- Protezione RAID / mirror ridotta (unità attive ma non protette)
- Dischi fuori dal RAID, con slot e numero di serie

**Lavori e sottosistemi**
- Lavori in attesa di risposta (MSGW)
- Code lavori bloccate e lavori in coda
- Sottosistemi attivi (QSYS, QBATCH, QINTER, QCMN...)
- Utilizzo medio della CPU

**Salvataggi**
- Backup non fatto: ore dall'ultimo salvataggio concluso
- Salvataggio ancora in corso
- Librerie rimaste fuori dal backup

**QSYSOPR, stampe, sicurezza**
- Messaggi gravi in QSYSOPR
- Richieste di assistenza hardware (CPPEA*: disco, alimentatore, ventola)
- Accumulo e spazio occupato dagli spool, coda per coda
- QSECURITY, QAUDCTL, QMAXSIGN, QPWDMINLEN

Quando qualcosa non va viene inviata un'email; gli allarmi sono registrati in
`alarms_history.jsonl` (tracciabilità) e un report PDF mensile viene generato
in `reports/` (evidenze NIS2).

## Requisiti

- Python 3.10+
- `pip install flask pyyaml fpdf2`
- Per la connessione reale all'AS/400: driver ODBC **IBM i Access** e
  `pip install pyodbc` (profilo utente con lettura sulle viste QSYS2)

## Avvio

Demo (nessun AS/400 richiesto, dati di esempio):

```bash
python app.py
```

Produzione: in `config.yaml` imposta `demo_mode: false`, i dati di
connessione in `as400:` e i parametri SMTP in `email:`.

La dashboard è su `http://127.0.0.1:5000` (Stato / Allarmi / Configurazione).

## Note sulle query

I controlli usano le viste di sistema SQL di IBM i: `QSYS2.ASP_STATUS`,
`QSYS2.DISK_STATUS`, `QSYS2.ACTIVE_JOB_INFO()`, `QSYS2.JOB_QUEUE_INFO`,
`QSYS2.OUTPUT_QUEUE_INFO()`, `QSYS2.SYSTEM_VALUE_INFO` e la coda messaggi
QSYSOPR. La vista `SAVELIB_STATUS` usata per i salvataggi è indicativa:
adattala al tuo strumento di backup (BRMS, prodotto di backup o programmi CL)
come descritto in `checks.py`.
