import streamlit as st
import sqlite3
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, date

# Configurazione pagina
st.set_page_config(page_title="Gestionale Contratti", page_icon="📄", layout="wide")

# Directory per salvare gli allegati
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Elenco dei Rami Aziendali
RAMI_AZIENDALI = [
    "Ufficio Tecnico",
    "Servizio di Pesa",
    "Ferroviario",
    "Amministrazione",
    "ICT",
    "Convenzioni",
    "Consulenza QS"
]

SOTTOCATEGORIE_UFFICIO_TECNICO = [
    "Selezioni",
    "Contratti senza rinnovo tacito",
    "Contratti con il rinnovo tacito",
    "Contratti una tantum"
]

TIPI_CONTRATTO = [
    "Attivo (Entrata / Cliente)",
    "Passivo (Uscita / Fornitore)"
]

# --- INIZIALIZZAZIONE DATABASE SQLITE ---
def init_db():
    conn = sqlite3.connect("database.sqlite")
    cursor = conn.cursor()
    
    # Tabella Contratti
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contratti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            titolo TEXT NOT NULL,
            oggetto TEXT DEFAULT '',
            tipo_contratto TEXT DEFAULT 'Passivo (Uscita / Fornitore)',
            data_inizio TEXT NOT NULL,
            data_scadenza TEXT NOT NULL,
            importo REAL,
            soggetto_istat TEXT DEFAULT 'No',
            ramo TEXT DEFAULT 'Ufficio Tecnico',
            sottocategoria TEXT DEFAULT '',
            file_path TEXT,
            note TEXT DEFAULT ''
        )
    ''')
    
    # Migrazioni automatiche tabella contratti
    for col, col_type in [("soggetto_istat", "TEXT DEFAULT 'No'"), 
                          ("ramo", "TEXT DEFAULT 'Ufficio Tecnico'"), 
                          ("sottocategoria", "TEXT DEFAULT ''"),
                          ("oggetto", "TEXT DEFAULT ''"),
                          ("tipo_contratto", "TEXT DEFAULT 'Passivo (Uscita / Fornitore)'"),
                          ("note", "TEXT DEFAULT ''")]:
        try:
            cursor.execute(f"ALTER TABLE contratti ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Tabella Utenti
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    
    # Utente admin di default se non esiste
    cursor.execute("SELECT COUNT(*) FROM utenti")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO utenti (username, email, password) VALUES (?, ?, ?)",
                       ("Amministratore", "admin@azienda.it", "admin"))

    # Tabella Impostazioni Email SMTP
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS impostazioni_mail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            smtp_server TEXT DEFAULT '',
            smtp_port INTEGER DEFAULT 587,
            smtp_user TEXT DEFAULT '',
            smtp_password TEXT DEFAULT '',
            email_mittente TEXT DEFAULT '',
            email_destinatario TEXT DEFAULT '',
            usa_tls INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM impostazioni_mail")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO impostazioni_mail (smtp_server, smtp_port, smtp_user, smtp_password, email_mittente, email_destinatario, usa_tls)
            VALUES ('smtp.gmail.com', 587, '', '', 'admin@azienda.it', 'admin@azienda.it', 1)
        ''')

    # Tabella Registro Notifiche Inviate (per evitare spam ripetuto)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifiche_inviate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash_invio TEXT UNIQUE,
            data_invio TEXT
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# --- HELPER DATABASE UTENTI & MAIL ---
def get_utente_admin():
    conn = sqlite3.connect("database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT username, email, password FROM utenti LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row if row else ("Amministratore", "admin@azienda.it", "admin")

def get_config_mail():
    conn = sqlite3.connect("database.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT smtp_server, smtp_port, smtp_user, smtp_password, email_mittente, email_destinatario, usa_tls FROM impostazioni_mail LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "smtp_server": row[0],
            "smtp_port": row[1],
            "smtp_user": row[2],
            "smtp_password": row[3],
            "email_mittente": row[4],
            "email_destinatario": row[5],
            "usa_tls": bool(row[6])
        }
    return None

# --- FUNZIONE INVIO EMAIL UNICA / DIGEST ---
def invia_email_digest_scadenze(contratti_in_scadenza, forza_invio=False):
    """Invia un'UNICA email contenente tutti i contratti in scadenza raggruppati"""
    cfg = get_config_mail()
    if not cfg or not cfg["smtp_server"] or not cfg["email_destinatario"]:
        return False, "⚠️ Configurazione SMTP o email destinatario non impostata."

    if not contratti_in_scadenza:
        return False, "Nessun contratto in scadenza trovato."

    # Raggruppamento per data di scadenza
    scadenze_dict = {}
    for c in contratti_in_scadenza:
        c_scad = c[6]
        if c_scad not in scadenze_dict:
            scadenze_dict[c_scad] = []
        scadenze_dict[c_scad].append(c)

    # Identificativo univoco per evitare re-invii continui nella stessa giornata
    oggi_str = date.today().strftime("%Y-%m-%d")
    ids_contratti = "-".join(sorted([str(c[0]) for c in contratti_in_scadenza]))
    hash_invio = f"{oggi_str}_{ids_contratti}"

    if not forza_invio:
        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM notifiche_inviate WHERE hash_invio = ?", (hash_invio,))
        già_inviato = cursor.fetchone()
        conn.close()
        if già_inviato:
            return True, "Email di notifica già inviata in precedenza per questo gruppo di scadenze."

    # Costruzione corpo email HTML
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #d9534f;">🚨 Report Contratti in Scadenza - {oggi_str}</h2>
        <p>Gentile Utente,</p>
        <p>Di seguito è riportato l'elenco riepilogativo di tutti i <b>{len(contratti_in_scadenza)} contratti</b> in scadenza imminente o già scaduti:</p>
        <hr style="border: 0; border-top: 1px solid #ccc;"/>
    """

    for dt_scad in sorted(scadenze_dict.keys()):
        lista = scadenze_dict[dt_scad]
        html_body += f"<h3 style='background-color: #f8f9fa; padding: 8px; border-left: 4px solid #0275d8;'>📅 Data Scadenza: {dt_scad} ({len(lista)} contratti)</h3>"
        html_body += "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; width: 100%; text-align: left;'>"
        html_body += "<tr style='background-color: #eee;'><th>Ramo</th><th>Cliente / Fornitore</th><th>Titolo Contratto</th><th>Tipo</th><th>Importo (€)</th><th>Oggetto</th></tr>"
        
        for c in lista:
            badge_t = "Attivo" if ("Attivo" in c[4]) else "Passivo"
            html_body += f"""
            <tr>
                <td><b>{c[9]}</b></td>
                <td>{c[1]}</td>
                <td>{c[2]}</td>
                <td>{badge_t}</td>
                <td>€ {c[7]:,.2f}</td>
                <td>{c[3]}</td>
            </tr>
            """
        html_body += "</table><br/>"

    html_body += """
        <hr style="border: 0; border-top: 1px solid #ccc;"/>
        <p style="font-size: 12px; color: #777;">Email generata automaticamente dal Gestionale Contratti Aziendali.</p>
      </body>
    </html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 Alert Scadenze Contratti ({len(contratti_in_scadenza)} in scadenza)"
        msg["From"] = cfg["email_mittente"]
        msg["To"] = cfg["email_destinatario"]
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        server = smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"]), timeout=15)
        if cfg["usa_tls"]:
            server.starttls()
        if cfg["smtp_user"] and cfg["smtp_password"]:
            server.login(cfg["smtp_user"], cfg["smtp_password"])

        server.sendmail(cfg["email_mittente"], [cfg["email_destinatario"]], msg.as_string())
        server.quit()

        # Registra l'invio
        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO notifiche_inviate (hash_invio, data_invio) VALUES (?, ?)", (hash_invio, oggi_str))
        conn.commit()
        conn.close()

        return True, "✅ Email riassuntiva delle scadenze inviata con successo!"
    except Exception as e:
        return False, f"❌ Errore durante l'invio dell'email: {e}"


# --- GESTIONE SESSIONE LOGIN ---
if "autenticato" not in st.session_state:
    st.session_state["autenticato"] = False

current_user = get_utente_admin()

# --- SCHERMATA DI LOGIN ---
if not st.session_state["autenticato"]:
    st.title("🔑 Accesso Gestionale")
    
    with st.form("login_form"):
        email_in = st.text_input("Email", placeholder="admin@azienda.it")
        password_in = st.text_input("Password", type="password", placeholder="Password")
        submit = st.form_submit_button("Accedi")
        
        if submit:
            if email_in.strip().lower() == current_user[1].lower() and password_in == current_user[2]:
                st.session_state["autenticato"] = True
                st.rerun()
            else:
                st.error("Credenziali errate!")

# --- APLICAZIONE PRINCIPALE LOGGATA ---
else:
    # Sidebar di Navigazione
    st.sidebar.title(f"👤 {current_user[0]}")
    st.sidebar.caption(f"Email: {current_user[1]}")
    
    pagina = st.sidebar.radio(
        "Menu Principale",
        ["📊 Gestionale Contratti", "⚙️ Pannello Amministratore"]
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout / Esci"):
        st.session_state["autenticato"] = False
        st.rerun()

    # --- PAGINA 1: GESTIONALE CONTRATTI ---
    if pagina == "📊 Gestionale Contratti":
        col_head1, col_head2 = st.columns([4, 1])
        with col_head1:
            st.title("📄 Gestionale Contratti Aziendali")

        st.markdown("---")

        # Layout a due colonne
        col_left, col_right = st.columns([1, 2.2])

        # --- FORM NUOVO CONTRATTO ---
        with col_left:
            st.subheader("➕ Nuovo Contratto")
            
            ramo_selezionato = st.selectbox("Ramo Aziendale", RAMI_AZIENDALI)
            
            sottocategoria_selezionata = ""
            if ramo_selezionato == "Ufficio Tecnico":
                sottocategoria_selezionata = st.selectbox("Sottocategoria Ufficio Tecnico", SOTTOCATEGORIE_UFFICIO_TECNICO)

            with st.form("form_contratto", clear_on_submit=True):
                tipo_contratto_sel = st.selectbox("Tipo Contratto *", TIPI_CONTRATTO)
                cliente = st.text_input("Nome Cliente / Fornitore *")
                titolo = st.text_input("Titolo Contratto *")
                oggetto = st.text_area("Oggetto del Contratto *", placeholder="Descrizione dell'oggetto del contratto...")
                
                data_inizio = st.date_input("Data Inizio", datetime.now())
                data_scadenza = st.date_input("Data Scadenza / Termine Iniziale", datetime.now())
                importo = st.number_input("Importo (€)", min_value=0.0, step=100.0)
                
                soggetto_istat = st.checkbox("Soggetto ad adeguamento ISTAT")
                note = st.text_area("Note (opzionale)", placeholder="Eventuali annotazioni, particolarità o dettagli...")
                file_allegato = st.file_uploader("Allegato (PDF/DOC)", type=["pdf", "doc", "docx"])
                
                salva = st.form_submit_button("Salva Contratto")
                
                if salva:
                    if cliente.strip() and titolo.strip() and oggetto.strip():
                        try:
                            path_salvato = None
                            if file_allegato is not None:
                                path_salvato = os.path.join(UPLOAD_DIR, file_allegato.name)
                                with open(path_salvato, "wb") as f:
                                    f.write(file_allegato.getbuffer())
                            
                            istat_val = "Sì" if soggetto_istat else "No"
                            
                            conn = sqlite3.connect("database.sqlite")
                            cursor = conn.cursor()
                            cursor.execute('''
                                INSERT INTO contratti (cliente, titolo, oggetto, tipo_contratto, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path, note)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (cliente.strip(), titolo.strip(), oggetto.strip(), tipo_contratto_sel, str(data_inizio), str(data_scadenza), importo, istat_val, ramo_selezionato, sottocategoria_selezionata, path_salvato, note.strip()))
                            conn.commit()
                            conn.close()
                            
                            st.success("✅ Contratto salvato con successo!")
                            st.toast("✅ Contratto aggiunto all'archivio!", icon="🎉")
                        except Exception as e:
                            st.error(f"❌ Errore durante il salvataggio: {e}")
                    else:
                        st.error("⚠️ Compila i campi obbligatori: 'Nome Cliente', 'Titolo Contratto' e 'Oggetto del Contratto'.")

        # --- ARCHIVIO DIVISO PER RAMI E SEARCH ---
        with col_right:
            st.subheader("📋 Archivio Contratti")
            
            oggi = date.today()
            oggi_str = oggi.strftime("%Y-%m-%d")
            limite_60_giorni_str = (oggi + timedelta(days=60)).strftime("%Y-%m-%d")

            conn = sqlite3.connect("database.sqlite")
            cursor = conn.cursor()

            SQL_SELECT = "SELECT id, cliente, titolo, oggetto, tipo_contratto, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path, note FROM contratti"

            # Recupera contratti attivi
            cursor.execute(f"{SQL_SELECT} WHERE ramo != 'Non più in vigore' ORDER BY data_scadenza ASC")
            tutti_attivi_rows = cursor.fetchall()

            # Calcolo scadenze
            rows_scaduti = [r for r in tutti_attivi_rows if r[6] and r[6] < oggi_str and r[10] != "Contratti con il rinnovo tacito"]
            rows_in_scadenza = [r for r in tutti_attivi_rows if r[6] and oggi_str <= r[6] <= limite_60_giorni_str and r[10] != "Contratti con il rinnovo tacito"]
            rows_rinnovo_tacito = [r for r in tutti_attivi_rows if r[10] == "Contratti con il rinnovo tacito" and r[6] and r[6] < oggi_str]

            # Trigger automatico email di notifica scadenze (se presenti e non ancora inviate)
            tutti_in_scadenza_oppure_scaduti = rows_scaduti + rows_in_scadenza
            if tutti_in_scadenza_oppure_scaduti:
                ok_mail, msg_mail = invia_email_digest_scadenze(tutti_in_scadenza_oppure_scaduti, forza_invio=False)

            # --- CONTATORI STATO CONTRATTI ---
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("🚨 Contratti Scaduti", f"{len(rows_scaduti)}")
            col_m2.metric("⚠️ In Scadenza (entro 2 mesi)", f"{len(rows_in_scadenza)}")
            col_m3.metric("📋 Totale Contratti Attivi", f"{len(tutti_attivi_rows)}")

            st.markdown("---")

            # Banner di notifica scadenze
            if rows_scaduti or rows_in_scadenza:
                msg = []
                if rows_scaduti:
                    msg.append(f"🚨 **{len(rows_scaduti)}** contratt{'o' if len(rows_scaduti)==1 else 'i'} **SCADUTI**")
                if rows_in_scadenza:
                    msg.append(f"⚠️ **{len(rows_in_scadenza)}** contratt{'o' if len(rows_in_scadenza)==1 else 'i'} **in scadenza entro 2 mesi**")
                st.warning(" | ".join(msg))

            # Schede archivio
            nomi_tabs = ["🔍 Ricerca", "📂 Tutti Attivi", "⏰ Scadenze"] + [f"🏢 {r}" for r in RAMI_AZIENDALI] + ["📦 Non più in vigore"]
            tabs = st.tabs(nomi_tabs)
            
            def mostra_contratti(rows, key_prefix=""):
                """Funzione per renderizzare i contratti con supporto a modifica, eliminazione e archiviazione"""
                if not rows:
                    st.info("Nessun contratto presente in questa sezione.")
                    return
                
                for r in rows:
                    c_id, c_cliente, c_titolo, c_oggetto, c_tipo, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_subcat, c_file, c_note = r
                    
                    is_tacito = (c_subcat == "Contratti con il rinnovo tacito")
                    is_scaduto = (c_scadenza < oggi_str if c_scadenza else False)

                    is_attivo = ("Attivo" in c_tipo) if c_tipo else False
                    badge_tipo = "🟢 Attivo" if is_attivo else "🔴 Passivo"

                    if is_tacito and is_scaduto:
                        scad_label = "Rinnovato tacitamente"
                    elif is_tacito:
                        scad_label = f"Prossimo rinnovo: {c_scadenza}"
                    else:
                        scad_label = f"Scadenza: {c_scadenza}"

                    header_text = f"📌 [{badge_tipo}] **[{c_ramo}]** {c_cliente} - {c_titolo} ({scad_label})"
                    if c_subcat and c_ramo == "Ufficio Tecnico":
                        header_text = f"📌 [{badge_tipo}] **[{c_ramo} / {c_subcat}]** {c_cliente} - {c_titolo} ({scad_label})"
                    
                    with st.expander(header_text):
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.write(f"**Tipo Contratto:** {badge_tipo} ({'Entrata / Cliente' if is_attivo else 'Uscita / Fornitore'})")
                            st.write(f"**Cliente/Fornitore:** {c_cliente}")
                            st.write(f"**Titolo:** {c_titolo}")
                            st.write(f"**Ramo:** {c_ramo}")
                            if c_subcat and c_ramo == "Ufficio Tecnico":
                                st.write(f"**Sottocategoria:** {c_subcat}")
                        
                        with col_info2:
                            st.write(f"**Importo:** € {c_importo:,.2f}")
                            if is_tacito:
                                if is_scaduto:
                                    st.success(f"🔄 **Rinnovo Tacito:** Il contratto si è rinnovato tacitamente dopo il {c_scadenza} ed è tuttora attivo.")
                                else:
                                    st.info(f"🔄 **Rinnovo Tacito:** Data di scadenza/rinnovo iniziale: {c_scadenza}.")
                            else:
                                st.write(f"**Validità:** dal {c_inizio} al {c_scadenza}")
                                
                            st.write(f"**Soggetto a ISTAT:** {c_istat if c_istat else 'No'}")

                        st.write(f"**Oggetto del Contratto:** {c_oggetto if c_oggetto else 'Non specificato'}")
                        
                        if c_note:
                            st.info(f"📝 **Note:** {c_note}")
                        
                        if c_file and os.path.exists(c_file):
                            with open(c_file, "rb") as f:
                                st.download_button(
                                    label="📁 Scarica Allegato Attuale",
                                    data=f,
                                    file_name=os.path.basename(c_file),
                                    key=f"{key_prefix}_dl_{c_id}"
                                )
                        
                        st.markdown("---")
                        
                        # Modifica Contratto
                        modifica_attiva = st.toggle("✏️ Modifica Contratto", key=f"{key_prefix}_toggle_mod_{c_id}")
                        
                        if modifica_attiva:
                            st.markdown("#### ✏️ Modifica Dati del Contratto")
                            
                            try:
                                dt_ini_val = datetime.strptime(c_inizio, "%Y-%m-%d").date() if c_inizio else date.today()
                            except Exception:
                                dt_ini_val = date.today()

                            try:
                                dt_scad_val = datetime.strptime(c_scadenza, "%Y-%m-%d").date() if c_scadenza else date.today()
                            except Exception:
                                dt_scad_val = date.today()

                            ramo_idx = RAMI_AZIENDALI.index(c_ramo) if c_ramo in RAMI_AZIENDALI else 0
                            tipo_idx = 1 if (c_tipo and "Passivo" in c_tipo) else 0
                            subcat_idx = SOTTOCATEGORIE_UFFICIO_TECNICO.index(c_subcat) if (c_subcat and c_subcat in SOTTOCATEGORIE_UFFICIO_TECNICO) else 0

                            with st.form(f"form_edit_{key_prefix}_{c_id}"):
                                edit_ramo = st.selectbox("Ramo Aziendale", RAMI_AZIENDALI, index=ramo_idx, key=f"{key_prefix}_e_ramo_{c_id}")
                                
                                edit_subcat = ""
                                if edit_ramo == "Ufficio Tecnico":
                                    edit_subcat = st.selectbox("Sottocategoria Ufficio Tecnico", SOTTOCATEGORIE_UFFICIO_TECNICO, index=subcat_idx, key=f"{key_prefix}_e_subcat_{c_id}")

                                edit_tipo = st.selectbox("Tipo Contratto *", TIPI_CONTRATTO, index=tipo_idx, key=f"{key_prefix}_e_tipo_{c_id}")
                                edit_cliente = st.text_input("Nome Cliente / Fornitore *", value=c_cliente, key=f"{key_prefix}_e_cli_{c_id}")
                                edit_titolo = st.text_input("Titolo Contratto *", value=c_titolo, key=f"{key_prefix}_e_tit_{c_id}")
                                edit_oggetto = st.text_area("Oggetto del Contratto *", value=c_oggetto, key=f"{key_prefix}_e_ogg_{c_id}")
                                
                                col_e_d1, col_e_d2 = st.columns(2)
                                with col_e_d1:
                                    edit_inizio = st.date_input("Data Inizio", value=dt_ini_val, key=f"{key_prefix}_e_dt_i_{c_id}")
                                with col_e_d2:
                                    edit_scadenza = st.date_input("Data Scadenza", value=dt_scad_val, key=f"{key_prefix}_e_dt_s_{c_id}")

                                edit_importo = st.number_input("Importo (€)", value=float(c_importo) if c_importo else 0.0, step=100.0, key=f"{key_prefix}_e_imp_{c_id}")
                                edit_istat = st.checkbox("Soggetto ad adeguamento ISTAT", value=(c_istat == "Sì"), key=f"{key_prefix}_e_istat_{c_id}")
                                edit_note = st.text_area("Note (opzionale)", value=c_note if c_note else "", key=f"{key_prefix}_e_note_{c_id}")
                                
                                st.write(f"**Allegato attuale:** {os.path.basename(c_file) if c_file else 'Nessun file allegato'}")
                                edit_file = st.file_uploader("Sostituisci o carica un nuovo Allegato (PDF/DOC)", type=["pdf", "doc", "docx"], key=f"{key_prefix}_e_file_{c_id}")

                                salva_modifiche = st.form_submit_button("💾 Salva Modifiche")

                                if salva_modifiche:
                                    if edit_cliente.strip() and edit_titolo.strip() and edit_oggetto.strip():
                                        try:
                                            nuovo_path_file = c_file
                                            if edit_file is not None:
                                                nuovo_path_file = os.path.join(UPLOAD_DIR, edit_file.name)
                                                with open(nuovo_path_file, "wb") as f:
                                                    f.write(edit_file.getbuffer())

                                            istat_val = "Sì" if edit_istat else "No"

                                            conn = sqlite3.connect("database.sqlite")
                                            cursor = conn.cursor()
                                            cursor.execute('''
                                                UPDATE contratti 
                                                SET cliente = ?, titolo = ?, oggetto = ?, tipo_contratto = ?, data_inizio = ?, data_scadenza = ?, importo = ?, soggetto_istat = ?, ramo = ?, sottocategoria = ?, file_path = ?, note = ?
                                                WHERE id = ?
                                            ''', (edit_cliente.strip(), edit_titolo.strip(), edit_oggetto.strip(), edit_tipo, str(edit_inizio), str(edit_scadenza), edit_importo, istat_val, edit_ramo, edit_subcat, nuovo_path_file, edit_note.strip(), c_id))
                                            
                                            conn.commit()
                                            conn.close()

                                            st.toast("✅ Contratto aggiornato con successo!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Errore durante l'aggiornamento: {e}")
                                    else:
                                        st.error("⚠️ Compila i campi obbligatori: 'Nome Cliente', 'Titolo Contratto' e 'Oggetto del Contratto'.")

                        st.markdown("---")
                        col_b1, col_b2 = st.columns(2)
                        
                        # Sposta / Ripristina
                        with col_b1:
                            if c_ramo != "Non più in vigore":
                                if st.button("📦 Sposta in 'Non più in vigore'", key=f"{key_prefix}_arch_{c_id}"):
                                    conn = sqlite3.connect("database.sqlite")
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE contratti SET ramo = 'Non più in vigore' WHERE id = ?", (c_id,))
                                    conn.commit()
                                    conn.close()
                                    st.toast("Contratto spostato in 'Non più in vigore'!")
                                    st.rerun()
                            else:
                                ramo_ripristino = st.selectbox("Ripristina in:", RAMI_AZIENDALI, key=f"{key_prefix}_sel_rest_{c_id}")
                                if st.button("↩️ Ripristina Contratto", key=f"{key_prefix}_rest_{c_id}"):
                                    conn = sqlite3.connect("database.sqlite")
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE contratti SET ramo = ? WHERE id = ?", (ramo_ripristino, c_id))
                                    conn.commit()
                                    conn.close()
                                    st.toast(f"Contratto ripristinato in '{ramo_ripristino}'!")
                                    st.rerun()
                                    
                        # Elimina
                        with col_b2:
                            if st.button("🗑️ Elimina Contratto", key=f"{key_prefix}_del_{c_id}"):
                                conn = sqlite3.connect("database.sqlite")
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM contratti WHERE id = ?", (c_id,))
                                conn.commit()
                                conn.close()
                                
                                if c_file and os.path.exists(c_file):
                                    try:
                                        os.remove(c_file)
                                    except Exception:
                                        pass
                                        
                                st.toast("Contratto eliminato con successo!")
                                st.rerun()

            def filtro_tipo_tabs(rows, prefix):
                sub_tabs = st.tabs(["📂 Tutti", "🟢 Solamente Attivi", "🔴 Solamente Passivi"])
                with sub_tabs[0]:
                    mostra_contratti(rows, key_prefix=f"{prefix}_all")
                with sub_tabs[1]:
                    mostra_contratti([r for r in rows if "Attivo" in r[4]], key_prefix=f"{prefix}_att")
                with sub_tabs[2]:
                    mostra_contratti([r for r in rows if "Passivo" in r[4]], key_prefix=f"{prefix}_pass")

            # Tab 0: Ricerca Avanzata
            with tabs[0]:
                st.markdown("### 🔎 Ricerca Veloce nell'Archivio")
                
                col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
                with col_s1:
                    query_ricerca = st.text_input("Cerca per Cliente/Fornitore, Titolo, Oggetto o Note...", placeholder="Es. Mario Rossi, Manutenzione, Pesa...")
                with col_s2:
                    filtro_ramo = st.selectbox("Filtra per Ramo", ["Tutti i Rami"] + RAMI_AZIENDALI + ["Non più in vigore"])
                with col_s3:
                    filtro_tipo = st.selectbox("Filtra per Tipo", ["Tutti i Tipi", "🟢 Solamente Attivi", "🔴 Solamente Passivi"])
                
                include_archiviati = st.checkbox("Includi anche i contratti 'Non più in vigore'", value=True)

                cursor.execute(f"{SQL_SELECT} ORDER BY data_scadenza ASC")
                tutti_i_contratti = cursor.fetchall()
                
                risultati = []
                q = query_ricerca.lower().strip()
                
                for row in tutti_i_contratti:
                    c_id, c_cliente, c_titolo, c_oggetto, c_tipo, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_subcat, c_file, c_note = row
                    
                    text_match = (not q) or (
                        q in c_cliente.lower() or 
                        q in c_titolo.lower() or 
                        q in (c_oggetto or "").lower() or 
                        q in (c_note or "").lower()
                    )
                    ramo_match = (filtro_ramo == "Tutti i Rami") or (c_ramo == filtro_ramo)
                    tipo_match = True
                    if filtro_tipo == "🟢 Solamente Attivi":
                        tipo_match = ("Attivo" in (c_tipo or ""))
                    elif filtro_tipo == "🔴 Solamente Passivi":
                        tipo_match = ("Passivo" in (c_tipo or ""))
                    arch_match = True if include_archiviati else (c_ramo != "Non più in vigore")

                    if text_match and ramo_match and tipo_match and arch_match:
                        risultati.append(row)

                st.caption(f"Trovati **{len(risultati)}** contratti corrispondenti ai criteri di ricerca.")
                st.markdown("---")
                mostra_contratti(risultati, key_prefix="search_results")

            # Tab 1: Tutti i contratti attivi
            with tabs[1]:
                filtro_tipo_tabs(tutti_attivi_rows, "tab_all")

            # Tab 2: Sezione Scadenze
            with tabs[2]:
                sub_tabs_scadenze = st.tabs(["⚠️ In Scadenza (entro 2 mesi)", "🚨 Scaduti", "🔄 Rinnovati Tacitamente"])
                
                with sub_tabs_scadenze[0]:
                    st.caption("Contratti attivi (senza rinnovo tacito) con scadenza prevista nei prossimi 60 giorni.")
                    filtro_tipo_tabs(rows_in_scadenza, "scad_exp")
                    
                with sub_tabs_scadenze[1]:
                    st.caption("Contratti attivi (senza rinnovo tacito) la cui data di scadenza è già trascorsa.")
                    filtro_tipo_tabs(rows_scaduti, "scad_over")

                with sub_tabs_scadenze[2]:
                    st.caption("Contratti con rinnovo tacito che hanno superato il termine iniziale e sono tuttora attivi.")
                    filtro_tipo_tabs(rows_rinnovo_tacito, "scad_tacito")

            # Tab 3: Ufficio Tecnico
            with tabs[3]:
                sub_tabs = st.tabs(["📂 Tutti Ufficio Tecnico"] + [f"🏷️ {s}" for s in SOTTOCATEGORIE_UFFICIO_TECNICO])
                
                with sub_tabs[0]:
                    cursor.execute(f"{SQL_SELECT} WHERE ramo = 'Ufficio Tecnico' ORDER BY data_scadenza ASC")
                    filtro_tipo_tabs(cursor.fetchall(), "ut_all")
                
                for j, sub_cat in enumerate(SOTTOCATEGORIE_UFFICIO_TECNICO):
                    with sub_tabs[j + 1]:
                        cursor.execute(
                            f"{SQL_SELECT} WHERE ramo = 'Ufficio Tecnico' AND sottocategoria = ? ORDER BY data_scadenza ASC",
                            (sub_cat,)
                        )
                        filtro_tipo_tabs(cursor.fetchall(), f"ut_sub_{j}")

            # Tab dal 4 in poi: Altri rami
            for i, ramo_nome in enumerate(RAMI_AZIENDALI[1:]):
                with tabs[i + 4]:
                    cursor.execute(
                        f"{SQL_SELECT} WHERE ramo = ? ORDER BY data_scadenza ASC",
                        (ramo_nome,)
                    )
                    filtro_tipo_tabs(cursor.fetchall(), f"branch_{i}")

            # Ultimo Tab: Non più in vigore
            with tabs[-1]:
                cursor.execute(
                    f"{SQL_SELECT} WHERE ramo = 'Non più in vigore' ORDER BY data_scadenza DESC"
                )
                archived_rows = cursor.fetchall()
                
                if not archived_rows:
                    st.info("Nessun contratto presente nella sezione 'Non più in vigore'.")
                else:
                    anni_presenti = sorted(list(set([r[6][:4] for r in archived_rows if r[6] and len(r[6]) >= 4])), reverse=True)
                    sub_tabs_anni = st.tabs(["📂 Tutti Archiviati"] + [f"📅 Anno {anno}" for anno in anni_presenti])
                    
                    with sub_tabs_anni[0]:
                        filtro_tipo_tabs(archived_rows, "arch_all")
                    
                    for idx, anno in enumerate(anni_presenti):
                        with sub_tabs_anni[idx + 1]:
                            rows_anno = [r for r in archived_rows if r[6].startswith(anno)]
                            filtro_tipo_tabs(rows_anno, f"arch_anno_{anno}")
                    
            conn.close()

    # --- PAGINA 2: PANNELLO AMMINISTRATORE ---
    elif pagina == "⚙️ Pannello Amministratore":
        st.title("⚙️ Pannello Amministratore")
        st.markdown("Gestisci la tua utenza e configura le impostazioni di invio mail per gli alert scadenze.")
        st.markdown("---")

        tab_admin1, tab_admin2 = st.tabs(["👤 Profilo Utenza", "✉️ Configurazione Mail & Alert"])

        # TAB 1: GESTIONE UTENZA
        with tab_admin1:
            st.subheader("👤 Modifica Utenza Amministratore")
            
            usr_attuale, email_attuale, pass_attuale = get_utente_admin()

            with st.form("form_profilo_admin"):
                nuovo_username = st.text_input("Nome Utente / Visualizzato", value=usr_attuale)
                nuova_email = st.text_input("Email di Login", value=email_attuale)
                nuova_password = st.text_input("Nuova Password", value=pass_attuale, type="password")
                
                salva_profilo = st.form_submit_button("💾 Aggiorna Utenza")

                if salva_profilo:
                    if nuovo_username.strip() and nuova_email.strip() and nuova_password.strip():
                        try:
                            conn = sqlite3.connect("database.sqlite")
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE utenti 
                                SET username = ?, email = ?, password = ?
                                WHERE id = (SELECT id FROM utenti LIMIT 1)
                            """, (nuovo_username.strip(), nuova_email.strip().lower(), nuova_password.strip()))
                            conn.commit()
                            conn.close()
                            
                            st.success("✅ Dati utente aggiornati con successo! Usa le nuove credenziali al prossimo login.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Errore durante l'aggiornamento dell'utenza: {e}")
                    else:
                        st.error("⚠️ Tutti i campi dell'utenza sono obbligatori.")

        # TAB 2: CONFIGURAZIONE MAIL SMTP & TEST
        with tab_admin2:
            st.subheader("✉️ Parametri Server Mail (SMTP)")
            
            cfg_mail = get_config_mail() or {}

            with st.form("form_config_mail"):
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    smtp_server = st.text_input("Server SMTP", value=cfg_mail.get("smtp_server", "smtp.gmail.com"), placeholder="es. smtp.gmail.com o smtp.office365.com")
                    smtp_port = st.number_input("Porta SMTP", value=int(cfg_mail.get("smtp_port", 587)), step=1)
                    usa_tls = st.checkbox("Utilizza SSL/TLS (Consigliato)", value=cfg_mail.get("usa_tls", True))
                
                with col_m2:
                    smtp_user = st.text_input("Username SMTP / Login Mail", value=cfg_mail.get("smtp_user", ""))
                    smtp_password = st.text_input("Password SMTP / Password App", value=cfg_mail.get("smtp_password", ""), type="password")

                st.markdown("---")
                st.subheader("📬 Indirizzi Email Mittente e Destinatario")
                
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    email_mittente = st.text_input("Email Mittente", value=cfg_mail.get("email_mittente", "admin@azienda.it"))
                with col_e2:
                    email_destinatario = st.text_input("Email Destinatario Alert", value=cfg_mail.get("email_destinatario", "admin@azienda.it"))

                salva_mail_cfg = st.form_submit_button("💾 Salva Configurazione Mail")

                if salva_mail_cfg:
                    try:
                        conn = sqlite3.connect("database.sqlite")
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE impostazioni_mail 
                            SET smtp_server = ?, smtp_port = ?, smtp_user = ?, smtp_password = ?, email_mittente = ?, email_destinatario = ?, usa_tls = ?
                            WHERE id = (SELECT id FROM impostazioni_mail LIMIT 1)
                        """, (smtp_server.strip(), int(smtp_port), smtp_user.strip(), smtp_password.strip(), email_mittente.strip(), email_destinatario.strip(), 1 if usa_tls else 0))
                        conn.commit()
                        conn.close()
                        
                        st.success("✅ Configurazione mail salvata con successo!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Errore durante il salvataggio della configurazione mail: {e}")

            st.markdown("---")
            st.subheader("🧪 Test e Invio Manuale Alert")

            col_test1, col_test2 = st.columns(2)

            # Pulsante Test Invio
            with col_test1:
                if st.button("📧 Invia Email di Prova"):
                    cfg = get_config_mail()
                    try:
                        msg = MIMEMultipart()
                        msg["Subject"] = "🧪 Test Configurazione Mail Gestionale Contratti"
                        msg["From"] = cfg["email_mittente"]
                        msg["To"] = cfg["email_destinatario"]
                        msg.attach(MIMEText("Se stai ricevendo questa mail, la configurazione del server SMTP è corretta!", "plain", "utf-8"))

                        server = smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"]), timeout=10)
                        if cfg["usa_tls"]:
                            server.starttls()
                        if cfg["smtp_user"] and cfg["smtp_password"]:
                            server.login(cfg["smtp_user"], cfg["smtp_password"])

                        server.sendmail(cfg["email_mittente"], [cfg["email_destinatario"]], msg.as_string())
                        server.quit()

                        st.success("✅ Email di prova inviata con successo!")
                    except Exception as ex:
                        st.error(f"❌ Errore durante l'invio dell'email di prova: {ex}")

            # Pulsante Invio Manuale Digest Scadenze
            with col_test2:
                if st.button("🚨 Invia Ora Email Unica Scadenze"):
                    oggi = date.today()
                    oggi_str = oggi.strftime("%Y-%m-%d")
                    limite_60_giorni_str = (oggi + timedelta(days=60)).strftime("%Y-%m-%d")

                    conn = sqlite3.connect("database.sqlite")
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, cliente, titolo, oggetto, tipo_contratto, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path, note 
                        FROM contratti 
                        WHERE ramo != 'Non più in vigore' AND data_scadenza <= ? AND sottocategoria != 'Contratti con il rinnovo tacito'
                        ORDER BY data_scadenza ASC
                    """, (limite_60_giorni_str,))
                    scadenze = cursor.fetchall()
                    conn.close()

                    if scadenze:
                        ok, res = invia_email_digest_scadenze(scadenze, forza_invio=True)
                        if ok:
                            st.success(res)
                        else:
                            st.error(res)
                    else:
                        st.info("Nessun contratto in scadenza trovato al momento.")
