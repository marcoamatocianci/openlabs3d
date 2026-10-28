# OpenLabs3D

OpenLabs3D connects laboratories with 3D-printing hosts. The HTML/CSS/JavaScript site is served by Caddy; FastAPI handles accounts, host applications, catalogue, moderation, order requests, printing jobs and protected image access. SQLite, photographs and Caddy certificates are stored in Docker volumes. No cloud backend is required.

Published products can be added to a browser-local basket and submitted as persistent order requests. The server validates current availability and prices, stores order snapshots and creates one printing job per line. No payment is collected and shipping is not integrated: buyer and host must arrange both separately. Product suitability, medical use and sterility are not verified. The original sample catalogue, sample basket and custom-request prototype remain separate browser-local demonstrations; they do not create server orders. Existing browser-local demo submissions are not migrated automatically.

## Requisiti e avvio su Ubuntu Linux

Installare Docker Engine e il plugin Docker Compose seguendo le istruzioni ufficiali per Ubuntu. Verificare `docker --version` e `docker compose version`; l'utente deve poter usare Docker. Occorrono accesso a Internet per scaricare le immagini e le dipendenze durante la prima build, e spazio libero per dati e backup.

Dalla directory del progetto:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Aprire **http://localhost:8080**. Registrarsi da **Account**, quindi usare **My listings** per creare una bozza, aggiungere fotografie e inviarla alla revisione. Ogni utente registrato può creare inserzioni, indipendentemente dal ruolo buyer/host. Il catalogo pubblico contiene solo inserzioni approvate; i prodotti dimostrativi sono mostrati separatamente. La documentazione API è disponibile su `/api/docs`.

Creare il primo amministratore in modo interattivo, senza inserire la password nella cronologia della shell:

```bash
docker compose exec backend python -m app.create_admin
```

Se compare un errore di codifica, verificare che il terminale usi UTF-8 (ad esempio con `locale`) e digitare nuovamente i valori, evitando caratteri incollati non validi.

Inserire email, nome e una password di almeno 12 caratteri. Il comando crea un nuovo account e non promuove o sovrascrive account esistenti. Dopo l'accesso, **Moderation** permette di esaminare, approvare, rifiutare e archiviare inserzioni. Un amministratore non può approvare la propria inserzione community; può creare e pubblicare progetti ufficiali. Le modifiche alle inserzioni pubblicate, incluse le foto, le riportano in revisione e le nascondono al pubblico fino a nuova approvazione.

Da **Administration** l'amministratore può consultare richieste di partecipazione, prodotti, ordini, utenti, categorie, impostazioni e attività. I candidati host inviano il profilo da **For printing hosts**; dopo l'approvazione vedono i lavori compatibili con i materiali indicati nel profilo. L'abbinamento automatico controlla solo il materiale: l'host deve verificare dimensioni, capacità e area di servizio prima di accettare. Dopo l'assegnazione riceve il contatto e l'indirizzo forniti dal compratore e può avanzare il lavoro da accettato a stampa, pronto e completato. L'amministratore può riaprire un lavoro accettato prima della stampa o cancellare un ordine non ancora in produzione.

Da **Account → Delete account** un utente può eliminare il proprio account confermando la password. Da **Administration → Users** un amministratore può eliminare anche altri account, inclusi gli amministratori, confermando la propria password. L'eliminazione rimuove l'account, la candidatura host e tutte le sessioni; le attività precedenti restano senza il collegamento all'utente. Gli account con inserzioni, ordini o lavori di stampa non possono essere eliminati finché tali record esistono, per conservare i collegamenti ai dati. È possibile eliminare anche l'ultimo amministratore: per crearne uno nuovo usare il comando `app.create_admin` indicato sopra. I backup già creati non vengono modificati.

## Configurazione e HTTPS in produzione

Modificare `.env` con il proprio dominio pubblico, ad esempio:

```dotenv
SITE_DOMAIN=openlabs3d.example.com
APP_ENV=production
MAX_UPLOAD_SIZE_MB=5
MAX_IMAGES_PER_LISTING=5
```

`DATABASE_URL` e `UPLOAD_DIR` documentano i percorsi predefiniti nel container; Compose li imposta esplicitamente affinché database e immagini condividano il volume persistente. Non sono necessari segreti statici per le sessioni: i token sono casuali e solo i relativi hash sono memorizzati nel database. Per eventuali segreti aggiuntivi generare valori con `openssl rand -hex 32` e non inserirli nel repository.

Puntare il DNS del dominio all'IP pubblico del server e aprire le porte TCP 80 e 443 (e UDP 443 per HTTP/3). Usare:

```bash
docker compose -f compose.yaml -f compose.production.yaml up -d --build
docker compose -f compose.yaml -f compose.production.yaml ps
```

Caddy ottiene e rinnova automaticamente i certificati, reindirizza HTTP a HTTPS e conserva certificati e configurazione nei volumi `caddy_data` e `caddy_config`. La configurazione di produzione forza cookie Secure. L'istanza FastAPI non pubblica porte sull'host. Il volume `app_data` contiene SQLite e immagini; non esporlo tramite il web server. Le normali ricostruzioni non eliminano i volumi; non usare `docker compose down -v` se si vogliono conservare i dati.

## Sviluppo e migrazioni

Il container avvia `alembic upgrade head` prima del server. Per applicare le migrazioni manualmente:

```bash
docker compose exec backend alembic upgrade head
```

In locale, creare un ambiente virtuale Python, installare `backend/requirements.txt`, impostare `DATABASE_URL` e `UPLOAD_DIR` su percorsi scrivibili, eseguire `alembic upgrade head` dalla directory `backend`, quindi avviare `uvicorn app.main:app --reload`. Caddy o un altro reverse proxy deve servire il frontend e inoltrare `/api/*` alla porta di Uvicorn. Per i test:

```bash
cd backend
pip install -r requirements.txt pytest httpx
python -m pytest -q
```

La documentazione interattiva dell'API descrive i campi e i codici HTTP. Le immagini vengono ricodificate e ridimensionate, con metadati rimossi; bozze e inserzioni non pubblicate sono accessibili solo al proprietario e agli amministratori.

Le migrazioni sono additive e vengono eseguite all'avvio del backend. Prima di aggiornare un'installazione con dati reali, effettuare e verificare un backup del volume `app_data`. Il carrello è locale al browser, mentre richieste, prezzi al momento dell'ordine, lavori, candidature e attività amministrative sono in SQLite. Non esistono pagamenti, fatturazione, notifiche o integrazioni con corrieri.

Per il test completo dell'interfaccia usare **solo un'istanza isolata** con database e volumi separati e un amministratore di test. Installare Selenium e avere Firefox e geckodriver disponibili. Lo script crea utenti, prodotti e ordini di test; non eseguirlo su dati reali:

```bash
pip install selenium Pillow
export OPENLABS3D_QA_ISOLATED=yes
export OPENLABS3D_QA_URL=http://127.0.0.1:18080
export OPENLABS3D_QA_ADMIN_EMAIL=qa-admin@example.org
read -rs OPENLABS3D_QA_ADMIN_PASSWORD
export OPENLABS3D_QA_ADMIN_PASSWORD
python tests/browser_workflow.py
unset OPENLABS3D_QA_ADMIN_PASSWORD
```

Creare prima l'amministratore di test con il comando `python -m app.create_admin` nel backend isolato. Lo script salva screenshot della homepage in `/tmp` e non elimina i dati di test. I test backend usano un database temporaneo separato.

Nel catalogo, ricerca, categoria, materiale e prezzo massimo vengono applicati prima della paginazione delle inserzioni pubblicate. Il filtro di larghezza interpreta il primo numero del campo dimensioni come larghezza in millimetri: le dimensioni che non iniziano con un numero vengono escluse quando il filtro è attivo. Inserire, per esempio, `128 × 86 × 32 mm`. I filtri del catalogo dimostrativo operano separatamente sui dati salvati nel browser.

Per sviluppo assistito da MCP, GitHub può essere usato in sola lettura per consultare problemi e cronologia, Context7 per verificare la documentazione delle dipendenze e Playwright per verificare l'interfaccia. I file locali rimangono la fonte di verità; eseguire i test di registrazione e moderazione su un'istanza isolata con un database e un volume dedicati. I server MCP e il browser devono essere disponibili e configurati dall'ambiente di sviluppo; non sono necessari per eseguire l'applicazione.

## Backup e ripristino

Effettuare backup periodici e conservare una copia fuori dal server. Per ottenere un insieme coerente di database e immagini, interrompere l'applicazione durante il backup. Il comando usa l'API SQLite backup, non una copia a caldo del file SQLite. Dalla directory del progetto (per produzione aggiungere `-f compose.yaml -f compose.production.yaml` a ogni comando `docker compose`):

```bash
mkdir -p backups
docker compose stop caddy backend
docker compose run --rm --no-deps --user root -v "$PWD/backups:/backup" --entrypoint python backend backup.py /backup/openlabs3d-$(date +%Y%m%d-%H%M%S).tar.gz
docker compose up -d
```

Il file potrebbe appartenere a root. Copiarlo in un luogo sicuro: contiene dati personali e immagini. La cartella `backups` non fa parte del volume dell'applicazione. Verificare regolarmente il ripristino su un'installazione isolata.

Per ripristinare, fermare l'applicazione, salvare prima un backup dei dati correnti e sostituire `ARCHIVIO.tar.gz` con il nome effettivo di un archivio attendibile. Il ripristino **sostituisce** database e immagini esistenti:

```bash
docker compose stop caddy backend
docker compose run --rm --no-deps --user root -v "$PWD/backups:/backup:ro" --entrypoint sh backend -c 'rm -rf /app/data/uploads /app/data/openlabs3d.db /app/data/openlabs3d.db-wal /app/data/openlabs3d.db-shm && tar -xzf /backup/ARCHIVIO.tar.gz -C /app/data && chown -R 10001:10001 /app/data'
docker compose up -d
```

Per trasferire l'applicazione su un altro server Linux, copiare repository, `.env` e archivio con un canale sicuro, installare Docker e Compose sul nuovo server, eseguire prima la build e poi la procedura di ripristino. Aggiornare DNS e `SITE_DOMAIN` se necessario. Caddy emetterà un nuovo certificato; i suoi volumi non sono necessari per ripristinare account e inserzioni.

## Risoluzione dei problemi

- `docker compose logs backend` e `docker compose logs caddy` mostrano errori di avvio, migrazione e certificato.
- Per HTTPS verificare DNS pubblico, accessibilità delle porte 80/443 e correttezza di `SITE_DOMAIN`.
- Una risposta 503 dal database indica contesa di scrittura; riprovare. SQLite usa WAL, foreign key e timeout di attesa.
- Se il login non funziona, controllare email e password; i tentativi sono limitati temporaneamente. Il limite è in memoria e si applica per istanza backend.
- Se la porta 8080 è occupata, cambiare la mappatura di sviluppo in `compose.yaml`.
- Il reset password via email, pagamenti, spedizioni integrate e notifiche non sono implementati. Proteggere l'accesso al server e ai backup; il sistema non include un servizio email.
