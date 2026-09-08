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
            cliente = st.text_input("Nome Cliente / Fornitore *")
            titolo = st.text_input("Titolo Contratto *")
            oggetto = st.text_area("Oggetto del Contratto *", placeholder="Descrizione dell'oggetto del contratto...")
            
            data_inizio = st.date_input("Data Inizio", datetime.now())
            data_scadenza = st.date_input("Data Scadenza", datetime.now())
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
                            INSERT INTO contratti (cliente, titolo, oggetto, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path, note)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (cliente.strip(), titolo.strip(), oggetto.strip(), str(data_inizio), str(data_scadenza), importo, istat_val, ramo_selezionato, sottocategoria_selezionata, path_salvato, note.strip()))
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
        
        # Calcolo scadenze e contratti scaduti
        oggi = date.today()
        oggi_str = oggi.strftime("%Y-%m-%d")
        limite_60_giorni_str = (oggi + timedelta(days=60)).strftime("%Y-%m-%d")

        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()

        SQL_SELECT = "SELECT id, cliente, titolo, oggetto, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path, note FROM contratti"

        # Recupera contratti attivi per calcolare le scadenze
        cursor.execute(f"{SQL_SELECT} WHERE ramo != 'Non più in vigore' ORDER BY data_scadenza ASC")
        tutti_attivi_rows = cursor.fetchall()

        rows_scaduti = [r for r in tutti_attivi_rows if r[5] and r[5] < oggi_str]
        rows_in_scadenza = [r for r in tutti_attivi_rows if r[5] and oggi_str <= r[5] <= limite_60_giorni_str]

        # Banner di notifica visivo in cima
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
                c_id, c_cliente, c_titolo, c_oggetto, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_subcat, c_file, c_note = r
                
                header_text = f"📌 **[{c_ramo}]** {c_cliente} - {c_titolo} (Scadenza: {c_scadenza})"
                if c_subcat and c_ramo == "Ufficio Tecnico":
                    header_text = f"📌 **[{c_ramo} / {c_subcat}]** {c_cliente} - {c_titolo} (Scadenza: {c_scadenza})"
                
                with st.expander(header_text):
                    st.write(f"**Cliente/Fornitore:** {c_cliente}")
                    st.write(f"**Titolo:** {c_titolo}")
                    st.write(f"**Ramo:** {c_ramo}")
                    if c_subcat and c_ramo == "Ufficio Tecnico":
                        st.write(f"**Sottocategoria:** {c_subcat}")
                    
                    st.write(f"**Oggetto del Contratto:** {c_oggetto if c_oggetto else 'Non specificato'}")
                    st.write(f"**Importo:** € {c_importo:,.2f}")
                    st.write(f"**Validità:** dal {c_inizio} al {c_scadenza}")
                    st.write(f"**Soggetto a ISTAT:** {c_istat if c_istat else 'No'}")
                    
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

        # Tab 1: Tutti i contratti attivi
        with tabs[0]:
            mostra_contratti(tutti_attivi_rows, key_prefix="all")

        # Tab 2: Sezione Scadenze (In scadenza entro 2 mesi / Scaduti)
        with tabs[1]:
            sub_tabs_scadenze = st.tabs(["⚠️ In Scadenza (entro 2 mesi)", "🚨 Scaduti"])
            
            with sub_tabs_scadenze[0]:
                st.caption("Contratti attivi con scadenza prevista nei prossimi 60 giorni.")
                mostra_contratti(rows_in_scadenza, key_prefix="scad_exp")
                
            with sub_tabs_scadenze[1]:
                st.caption("Contratti attivi la cui data di scadenza è già trascorsa.")
                mostra_contratti(rows_scaduti, key_prefix="scad_over")

        # Tab 3: Ufficio Tecnico con Sotto-Tab per Sottocategorie
        with tabs[2]:
            sub_tabs = st.tabs(["📂 Tutti Ufficio Tecnico"] + [f"🏷️ {s}" for s in SOTTOCATEGORIE_UFFICIO_TECNICO])
            
            with sub_tabs[0]:
                cursor.execute(f"{SQL_SELECT} WHERE ramo = 'Ufficio Tecnico' ORDER BY data_scadenza ASC")
                mostra_contratti(cursor.fetchall(), key_prefix="ut_all")
            
            for j, sub_cat in enumerate(SOTTOCATEGORIE_UFFICIO_TECNICO):
                with sub_tabs[j + 1]:
                    cursor.execute(
                        f"{SQL_SELECT} WHERE ramo = 'Ufficio Tecnico' AND sottocategoria = ? ORDER BY data_scadenza ASC",
                        (sub_cat,)
                    )
                    mostra_contratti(cursor.fetchall(), key_prefix=f"ut_sub_{j}")

        # Tab 4-8: Gli altri rami aziendali attivi
        for i, ramo_nome in enumerate(RAMI_AZIENDALI[1:]):
            with tabs[i + 3]:
                cursor.execute(
                    f"{SQL_SELECT} WHERE ramo = ? ORDER BY data_scadenza ASC",
                    (ramo_nome,)
                )
                mostra_contratti(cursor.fetchall(), key_prefix=f"branch_{i}")

        # Tab 9: Non più in vigore
        with tabs[-1]:
            cursor.execute(
                f"{SQL_SELECT} WHERE ramo = 'Non più in vigore' ORDER BY data_scadenza DESC"
            )
            archived_rows = cursor.fetchall()
            
            if not archived_rows:
                st.info("Nessun contratto presente nella sezione 'Non più in vigore'.")
            else:
                anni_presenti = sorted(list(set([r[5][:4] for r in archived_rows if r[5] and len(r[5]) >= 4])), reverse=True)
                sub_tabs_anni = st.tabs(["📂 Tutti Archiviati"] + [f"📅 Anno {anno}" for anno in anni_presenti])
                
                with sub_tabs_anni[0]:
                    mostra_contratti(archived_rows, key_prefix="arch_all")
                
                for idx, anno in enumerate(anni_presenti):
                    with sub_tabs_anni[idx + 1]:
                        rows_anno = [r for r in archived_rows if r[5].startswith(anno)]
                        mostra_contratti(rows_anno, key_prefix=f"arch_anno_{anno}")
                
        conn.close()
