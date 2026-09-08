import streamlit as st
import sqlite3
import os
from datetime import datetime

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
            data_inizio TEXT NOT NULL,
            data_scadenza TEXT NOT NULL,
            importo REAL,
            soggetto_istat TEXT DEFAULT 'No',
            ramo TEXT DEFAULT 'Ufficio Tecnico',
            sottocategoria TEXT DEFAULT '',
            file_path TEXT
        )
    ''')
    
    # Migrazioni automatiche per database esistenti
    for col, col_type in [("soggetto_istat", "TEXT DEFAULT 'No'"), 
                          ("ramo", "TEXT DEFAULT 'Ufficio Tecnico'"), 
                          ("sottocategoria", "TEXT DEFAULT ''")]:
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
            cliente = st.text_input("Nome Cliente / Fornitore")
            titolo = st.text_input("Titolo Contratto")
            data_inizio = st.date_input("Data Inizio", datetime.now())
            data_scadenza = st.date_input("Data Scadenza", datetime.now())
            importo = st.number_input("Importo (€)", min_value=0.0, step=100.0)
            
            soggetto_istat = st.checkbox("Soggetto ad adeguamento ISTAT")
            file_allegato = st.file_uploader("Allegato (PDF/DOC)", type=["pdf", "doc", "docx"])
            
            salva = st.form_submit_button("Salva Contratto")
            
            if salva:
                if cliente and titolo:
                    path_salvato = None
                    if file_allegato:
                        path_salvato = os.path.join(UPLOAD_DIR, file_allegato.name)
                        with open(path_salvato, "wb") as f:
                            f.write(file_allegato.getbuffer())
                    
                    istat_val = "Sì" if soggetto_istat else "No"
                    
                    conn = sqlite3.connect("database.sqlite")
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO contratti (cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (cliente, titolo, str(data_inizio), str(data_scadenza), importo, istat_val, ramo_selezionato, sottocategoria_selezionata, path_salvato))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"Contratto salvato con successo!")
                    st.rerun()
                else:
                    st.warning("Compila tutti i campi obbligatori.")

    # --- ARCHIVIO DIVISO PER RAMI E SOTTOCATEGORIE ---
    with col_right:
        st.subheader("📋 Archivio Contratti")
        
        # Schede dell'archivio (inclusa la scheda "Non più in vigore")
        nomi_tabs = ["📂 Tutti Attivi"] + [f"🏢 {r}" for r in RAMI_AZIENDALI] + ["📦 Non più in vigore"]
        tabs = st.tabs(nomi_tabs)
        
        def mostra_contratti(rows):
            """Funzione per renderizzare la lista dei contratti con azioni (Elimina / Sposta / Ripristina)"""
            if not rows:
                st.info("Nessun contratto presente in questa sezione.")
                return
            
            for r in rows:
                c_id, c_cliente, c_titolo, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_subcat, c_file = r
                
                header_text = f"📌 **[{c_ramo}]** {c_cliente} - {c_titolo} (Scadenza: {c_scadenza})"
                if c_subcat and c_ramo == "Ufficio Tecnico":
                    header_text = f"📌 **[{c_ramo} / {c_subcat}]** {c_cliente} - {c_titolo} (Scadenza: {c_scadenza})"
                
                with st.expander(header_text):
                    st.write(f"**Cliente/Fornitore:** {c_cliente}")
                    st.write(f"**Ramo:** {c_ramo}")
                    if c_subcat and c_ramo == "Ufficio Tecnico":
                        st.write(f"**Sottocategoria:** {c_subcat}")
                    st.write(f"**Importo:** € {c_importo:,.2f}")
                    st.write(f"**Validità:** dal {c_inizio} al {c_scadenza}")
                    st.write(f"**Soggetto a ISTAT:** {c_istat if c_istat else 'No'}")
                    
                    if c_file and os.path.exists(c_file):
                        with open(c_file, "rb") as f:
                            st.download_button(
                                label="📁 Scarica Allegato",
                                data=f,
                                file_name=os.path.basename(c_file),
                                key=f"dl_{c_id}"
                            )
                    
                    st.markdown("---")
                    col_b1, col_b2 = st.columns(2)
                    
                    # Pulsante Sposta / Ripristina
                    with col_b1:
                        if c_ramo != "Non più in vigore":
                            if st.button("📦 Sposta in 'Non più in vigore'", key=f"arch_{c_id}"):
                                conn = sqlite3.connect("database.sqlite")
                                cursor = conn.cursor()
                                cursor.execute("UPDATE contratti SET ramo = 'Non più in vigore' WHERE id = ?", (c_id,))
                                conn.commit()
                                conn.close()
                                st.success("Contratto spostato in 'Non più in vigore'!")
                                st.rerun()
                        else:
                            ramo_ripristino = st.selectbox("Ripristina in:", RAMI_AZIENDALI, key=f"sel_rest_{c_id}")
                            if st.button("↩️ Ripristina Contratto", key=f"rest_{c_id}"):
                                conn = sqlite3.connect("database.sqlite")
                                cursor = conn.cursor()
                                cursor.execute("UPDATE contratti SET ramo = ? WHERE id = ?", (ramo_ripristino, c_id))
                                conn.commit()
                                conn.close()
                                st.success(f"Contratto ripristinato in '{ramo_ripristino}'!")
                                st.rerun()
                                
                    # Pulsante Elimina
                    with col_b2:
                        if st.button("🗑️ Elimina Contratto", key=f"del_{c_id}"):
                            conn = sqlite3.connect("database.sqlite")
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM contratti WHERE id = ?", (c_id,))
                            conn.commit()
                            conn.close()
                            
                            # Cancella il file allegato se esiste
                            if c_file and os.path.exists(c_file):
                                try:
                                    os.remove(c_file)
                                except Exception:
                                    pass
                                    
                            st.success("Contratto eliminato con successo!")
                            st.rerun()

        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()

        # Tab 1: Tutti i contratti attivi
        with tabs[0]:
            cursor.execute("SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path FROM contratti WHERE ramo != 'Non più in vigore' ORDER BY data_scadenza ASC")
            mostra_contratti(cursor.fetchall())

        # Tab 2: Ufficio Tecnico con Sotto-Tab per Sottocategorie
        with tabs[1]:
            sub_tabs = st.tabs(["📂 Tutti Ufficio Tecnico"] + [f"🏷️ {s}" for s in SOTTOCATEGORIE_UFFICIO_TECNICO])
            
            with sub_tabs[0]:
                cursor.execute("SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path FROM contratti WHERE ramo = 'Ufficio Tecnico' ORDER BY data_scadenza ASC")
                mostra_contratti(cursor.fetchall())
            
            for j, sub_cat in enumerate(SOTTOCATEGORIE_UFFICIO_TECNICO):
                with sub_tabs[j + 1]:
                    cursor.execute(
                        "SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path FROM contratti WHERE ramo = 'Ufficio Tecnico' AND sottocategoria = ? ORDER BY data_scadenza ASC",
                        (sub_cat,)
                    )
                    mostra_contratti(cursor.fetchall())

        # Tab 3-7: Gli altri rami aziendali attivi
        for i, ramo_nome in enumerate(RAMI_AZIENDALI[1:]):
            with tabs[i + 2]:
                cursor.execute(
                    "SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path FROM contratti WHERE ramo = ? ORDER BY data_scadenza ASC",
                    (ramo_nome,)
                )
                mostra_contratti(cursor.fetchall())

        # Tab 8: Non più in vigore (Suddiviso in sotto-schede per Anno di scadenza)
        with tabs[-1]:
            cursor.execute(
                "SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, sottocategoria, file_path FROM contratti WHERE ramo = 'Non più in vigore' ORDER BY data_scadenza DESC"
            )
            archived_rows = cursor.fetchall()
            
            if not archived_rows:
                st.info("Nessun contratto presente nella sezione 'Non più in vigore'.")
            else:
                # Estrae gli anni unici dalle date dei contratti archiviati
                anni_presenti = sorted(list(set([r[4][:4] for r in archived_rows if r[4] and len(r[4]) >= 4])), reverse=True)
                
                sub_tabs_anni = st.tabs(["📂 Tutti Archiviati"] + [f"📅 Anno {anno}" for anno in anni_presenti])
                
                # Sotto-Tab "Tutti Archiviati"
                with sub_tabs_anni[0]:
                    mostra_contratti(archived_rows)
                
                # Sotto-Tab per ciascun singolo Anno
                for idx, anno in enumerate(anni_presenti):
                    with sub_tabs_anni[idx + 1]:
                        rows_anno = [r for r in archived_rows if r[4].startswith(anno)]
                        mostra_contratti(rows_anno)
                
        conn.close()
