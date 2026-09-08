import streamlit as st
import sqlite3
import os
from datetime import datetime

# Configurazione pagina
st.set_page_config(page_title="Gestionale Contratti", page_icon="📄", layout="wide")

# Directory per salvare gli allegati
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Elenco dei Rami Aziendali
RAMI_AZIENDALI = [
    "Manutenzione",
    "Terminalistici",
    "Amministrazione",
    "ICT",
    "Convenzioni",
    "Consulenza QS"
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
            ramo TEXT DEFAULT 'Manutenzione',
            file_path TEXT
        )
    ''')
    
    # Migrazioni per database esistenti
    try:
        cursor.execute("ALTER TABLE contratti ADD COLUMN soggetto_istat TEXT DEFAULT 'No'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE contratti ADD COLUMN ramo TEXT DEFAULT 'Manutenzione'")
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
        with st.form("form_contratto", clear_on_submit=True):
            cliente = st.text_input("Nome Cliente / Fornitore")
            titolo = st.text_input("Titolo Contratto")
            
            # Selezione Ramo Aziendale
            ramo_selezionato = st.selectbox("Ramo Aziendale", RAMI_AZIENDALI)
            
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
                        INSERT INTO contratti (cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (cliente, titolo, str(data_inizio), str(data_scadenza), importo, istat_val, ramo_selezionato, path_salvato))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"Contratto salvato nella sezione '{ramo_selezionato}'!")
                    st.rerun()
                else:
                    st.warning("Compila tutti i campi obbligatori.")

    # --- ARCHIVIO DIVISO PER RAMI AZIENDALI ---
    with col_right:
        st.subheader("📋 Archivio Contratti")
        
        # Creazione delle schede (Tabs)
        nomi_tabs = ["📂 Tutti"] + [f"🏢 {r}" for r in RAMI_AZIENDALI]
        tabs = st.tabs(nomi_tabs)
        
        def mostra_contratti(rows):
            """Funzione di supporto per renderizzare i contratti"""
            if not rows:
                st.info("Nessun contratto presente in questa sezione.")
                return
            
            for r in rows:
                c_id, c_cliente, c_titolo, c_inizio, c_scadenza, c_importo, c_istat, c_ramo, c_file = r
                
                with st.expander(f"📌 **[{c_ramo}]** {c_cliente} - {c_titolo} (Scadenza: {c_scadenza})"):
                    st.write(f"**Cliente/Fornitore:** {c_cliente}")
                    st.write(f"**Ramo:** {c_ramo}")
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

        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()

        # Tab 1: Tutti i contratti
        with tabs[0]:
            cursor.execute("SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, file_path FROM contratti ORDER BY data_scadenza ASC")
            mostra_contratti(cursor.fetchall())

        # Tab 2-7: Un tab dedicato per ogni singolo ramo
        for i, ramo_nome in enumerate(RAMI_AZIENDALI):
            with tabs[i + 1]:
                cursor.execute(
                    "SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, ramo, file_path FROM contratti WHERE ramo = ? ORDER BY data_scadenza ASC",
                    (ramo_nome,)
                )
                mostra_contratti(cursor.fetchall())
                
        conn.close()
