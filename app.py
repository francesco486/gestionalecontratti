import streamlit as st
import sqlite3
import os
from datetime import datetime, timedelta, date

# Configurazione pagina
st.set_page_config(page_title="Gestionale Contratti", page_icon="📄", layout="wide")

# Directory per salvare gli allegati
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Elenco dei Rami Aziendali e Sottocategorie
RAMI_AZIENDALI = [
    "Ufficio Tecnico",
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

# Inizializzazione Database SQLite
def init_db():
    conn = sqlite3.connect("database.sqlite")
    cursor = conn.cursor()
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
    
    # Migrazioni automatiche per database esistenti
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

    conn.commit()
    conn.close()

init_db()

# --- GESTIONE SESSIONE LOGIN ---
if "autenticato" not in st.session_state:
    st.session_state["autenticato"] = False

# --- SCHERMATA DI LOGIN ---
if not st.session_state["autenticato"]:
    st.title("🔑 Accesso Gestionale")
    
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="admin@azienda.it")
        password = st.text_input("Password", type="password", placeholder="admin")
        submit = st.form_submit_button("Accedi")
        
        if submit:
            if email == "admin@azienda.it" and password == "admin":
                st.session_state["autenticato"] = True
                st.rerun()
            else:
                st.error("Credenziali errate!")

# --- DASHBOARD PRINCIPALE ---
else:
    col_head1, col_head2 = st.columns([4, 1])
    with col_head1:
        st.title("📄 Gestionale Contratti Aziendali")
    with col_head2:
        if st.button("🚪 Esci"):
            st.session_state["autenticato"] = False
            st.rerun()

    st.markdown("---")

    # Layout a due colonne
    col_left, col_right = st.columns([1, 2.2])

    # --- FORM NUOVO CONTRATTO ---
    with col_left:
        st.subheader("➕ Nuovo Contratto")
        
        # Selezione Ramo dinamica
        ramo_selezionato = st.selectbox("Ramo Aziendale", RAMI_AZIENDALI)
        
        # Mostra la sottocategoria solo se il ramo è Ufficio Tecnico
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
            note = st.text_area("Note (opzionale)", placeholder="Eventuali annotazioni, particolarità o dettagli aggiuntivi...")
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

    # --- ARCHIVIO DIVISO PER RAMI E SOTTOCATEGORIE ---
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

        # Calcolo totali economici attivi vs passivi
        tot_attivi = sum(r[7] for r in tutti_attivi_rows if r[4] and "Attivo" in r[4])
        tot_passivi = sum(r[7] for r in tutti_attivi_rows if r[4] and "Passivo" in r[4])
        saldo = tot_attivi - tot_passivi

        # Indicatori di sintesi finanziaria
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("🟢 Totale Entrate (Attivi)", f"€ {tot_attivi:,.2f}")
        col_m2.metric("🔴 Totale Uscite (Passivi)", f"€ {tot_passivi:,.2f}")
        col_m3.metric("📊 Saldo Netto", f"€ {saldo:,.2f}")

        st.markdown("---")

        # Banner di notifica scadenze
        if rows_scaduti or rows_in_scadenza:
            msg = []
            if rows_scaduti:
                msg.append(f"🚨 **{len(rows_scaduti)}** contratt{'o' if len(rows_scaduti)==1 else 'i'} **SCADUTI**")
            if rows_in_scadenza:
                msg.append(f"⚠️ **{len(rows_in_scadenza)}** contratt{'o' if len(rows_in_scadenza)==1 else 'i'} **in scadenza entro 2 mesi**")
            st.warning(" | ".join(msg))

        nomi_tabs = ["📂 Tutti Attivi", "⏰ Scadenze"] + [f"🏢 {r}" for r in RAMI_AZIENDALI] + ["📦 Non più in vigore"]
        tabs = st.tabs(nomi_tabs)
        
        def mostra_contratti(rows, key_prefix=""):
            """Funzione per renderizzare i contratti con chiavi widget univoche per scheda"""
            if not rows:
                st.info("Nessun contratto presente in questa sezione.")
                return
            
            for r in rows:
                c_id, c_cliente, c_titolo, c_oggetto, c_tipo, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_subcat, c_file, c_note = r
                
                is_tacito = (c_subcat == "Contratti con il rinnovo tacito")
                is_scaduto = (c_scadenza < oggi_str if c_scadenza else False)

                # Gestione etichetta tipo contratto
                is_attivo = ("Attivo" in c_tipo) if c_tipo else False
                badge_tipo = "🟢 Attivo" if is_attivo else "🔴 Passivo"

                # Gestione etichetta intestazione
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
                                label="📁 Scarica Allegato",
                                data=f,
                                file_name=os.path.basename(c_file),
                                key=f"{key_prefix}_dl_{c_id}"
                            )
                    
                    st.markdown("---")
                    col_b1, col_b2 = st.columns(2)
                    
                    # Pulsante Sposta / Ripristina
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
                                
                    # Pulsante Elimina
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
            """Helper per creare rapidamente le sotto-schede Tutti / Attivi / Passivi"""
            sub_tabs = st.tabs(["📂 Tutti", "🟢 Solamente Attivi", "🔴 Solamente Passivi"])
            with sub_tabs[0]:
                mostra_contratti(rows, key_prefix=f"{prefix}_all")
            with sub_tabs[1]:
                mostra_contratti([r for r in rows if "Attivo" in r[4]], key_prefix=f"{prefix}_att")
            with sub_tabs[2]:
                mostra_contratti([r for r in rows if "Passivo" in r[4]], key_prefix=f"{prefix}_pass")

        # Tab 1: Tutti i contratti attivi
        with tabs[0]:
            filtro_tipo_tabs(tutti_attivi_rows, "tab_all")

        # Tab 2: Sezione Scadenze
        with tabs[1]:
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

        # Tab 3: Ufficio Tecnico con Sotto-Tab per Sottocategorie
        with tabs[2]:
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

        # Tab 4-8: Gli altri rami aziendali attivi
        for i, ramo_nome in enumerate(RAMI_AZIENDALI[1:]):
            with tabs[i + 3]:
                cursor.execute(
                    f"{SQL_SELECT} WHERE ramo = ? ORDER BY data_scadenza ASC",
                    (ramo_nome,)
                )
                filtro_tipo_tabs(cursor.fetchall(), f"branch_{i}")

        # Tab 9: Non più in vigore con filtri per tipo contratto generali e annuali
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
