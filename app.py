import streamlit as st
import sqlite3
import os
from datetime import datetime

# Configurazione pagina
st.set_page_config(page_title="Gestionale Contratti", page_icon="📄", layout="wide")

# Directory per salvare gli allegati
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
            file_path TEXT
        )
    ''')
    
    # Aggiornamento automatico per database esistenti senza la colonna ISTAT
    try:
        cursor.execute("ALTER TABLE contratti ADD COLUMN soggetto_istat TEXT DEFAULT 'No'")
    except sqlite3.OperationalError:
        pass  # La colonna esiste già

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
    # Header e Logout
    col_head1, col_head2 = st.columns([4, 1])
    with col_head1:
        st.title("📄 Gestionale Contratti")
    with col_head2:
        if st.button("🚪 Esci"):
            st.session_state["autenticato"] = False
            st.rerun()

    st.markdown("---")

    # Layout a due colonne: Form Inserimento (Sinistra) | Lista Contratti (Destra)
    col_left, col_right = st.columns([1, 2])

    # --- FORM NUOVO CONTRATTO ---
    with col_left:
        st.subheader("➕ Nuovo Contratto")
        with st.form("form_contratto", clear_on_submit=True):
            cliente = st.text_input("Nome Cliente")
            titolo = st.text_input("Titolo Contratto")
            data_inizio = st.date_input("Data Inizio", datetime.now())
            data_scadenza = st.date_input("Data Scadenza", datetime.now())
            importo = st.number_input("Importo (€)", min_value=0.0, step=100.0)
            
            # Campo Selezione ISTAT
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
                    
                    # Salvataggio nel DB
                    conn = sqlite3.connect("database.sqlite")
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO contratti (cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (cliente, titolo, str(data_inizio), str(data_scadenza), importo, istat_val, path_salvato))
                    conn.commit()
                    conn.close()
                    
                    st.success("Contratto salvato con successo!")
                    st.rerun()
                else:
                    st.warning("Compila tutti i campi obbligatori.")

    # --- TABELLA E LISTA CONTRATTI ---
    with col_right:
        st.subheader("📋 Contratti in Essere")
        
        conn = sqlite3.connect("database.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT id, cliente, titolo, data_inizio, data_scadenza, importo, soggetto_istat, file_path FROM contratti ORDER BY data_scadenza ASC")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            st.info("Nessun contratto presente nel database.")
        else:
            for r in rows:
                c_id, c_cliente, c_titolo, c_inizio, c_scadenza, c_importo, c_istat, c_file = r
                
                with st.expander(f"📌 **{c_cliente}** - {c_titolo} (Scadenza: {c_scadenza})"):
                    st.write(f"**Importo:** € {c_importo:,.2f}")
                    st.write(f"**Data Inizio:** {c_inizio}")
                    st.write(f"**Soggetto a ISTAT:** {c_istat if c_istat else 'No'}")
                    
                    if c_file and os.path.exists(c_file):
                        with open(c_file, "rb") as f:
                            st.download_button(
                                label="📁 Scarica Allegato",
                                data=f,
                                file_name=os.path.basename(c_file),
                                key=f"dl_{c_id}"
                            )
