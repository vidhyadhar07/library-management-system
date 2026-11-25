import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd

# ---------------------------------------------------------
# DATABASE INITIALIZATION
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("library.db")
    cursor = conn.cursor()
    
    # Books Table with Category
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            copies INTEGER NOT NULL
        )
    """)
    
    # Transactions Table with Due Dates & Fines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            member_name TEXT,
            issue_date TEXT,
            due_date TEXT,
            return_date TEXT,
            fine_amount REAL DEFAULT 0.0,
            status TEXT,
            FOREIGN KEY (book_id) REFERENCES books (id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# STREAMLIT USER INTERFACE
# ---------------------------------------------------------
st.set_page_config(page_title="Library Management System", layout="wide")
st.title("📚 Library Management System")

menu = ["Dashboard", "Book Management", "Issue / Return Book", "Fines & Reports"]
choice = st.sidebar.selectbox("Navigation Menu", menu)

# ---------------------------------------------------------
# 1. DASHBOARD OVERVIEW
# ---------------------------------------------------------
if choice == "Dashboard":
    st.header("📊 Library Statistics")
    
    conn = sqlite3.connect("library.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT SUM(copies) FROM books")
    total_books = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'Issued'")
    issued_books = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(fine_amount) FROM transactions WHERE status = 'Returned'")
    total_fines = cursor.fetchone()[0] or 0.0
    
    conn.close()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Book Copies", total_books)
    col2.metric("Currently Issued", issued_books)
    col3.metric("Total Fines Collected", f"${total_fines:.2f}")

# ---------------------------------------------------------
# 2. BOOK MANAGEMENT (WITH CATEGORIES)
# ---------------------------------------------------------
elif choice == "Book Management":
    st.header("📖 Catalog & Category Management")
    
    tab1, tab2 = st.tabs(["Add Book", "View Catalog"])
    
    with tab1:
        st.subheader("Add New Book")
        title = st.text_input("Title")
        author = st.text_input("Author")
        category = st.selectbox(
            "Category", 
            ["Fiction", "Non-Fiction", "Science & Tech", "History", "Biography", "Other"]
        )
        copies = st.number_input("Number of Copies", min_value=1, value=1)
        
        if st.button("Save Book"):
            if title and author:
                conn = sqlite3.connect("library.db")
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO books (title, author, category, copies) VALUES (?, ?, ?, ?)",
                    (title, author, category, copies)
                )
                conn.commit()
                conn.close()
                st.success(f"Added '{title}' under category '{category}'!")
            else:
                st.error("Please fill in all required fields.")
                
    with tab2:
        st.subheader("Book Directory")
        conn = sqlite3.connect("library.db")
        
        # Category Filter
        cat_filter = st.selectbox(
            "Filter Directory by Category", 
            ["All", "Fiction", "Non-Fiction", "Science & Tech", "History", "Biography", "Other"]
        )
        
        if cat_filter != "All":
            df = pd.read_sql_query("SELECT * FROM books WHERE category = ?", conn, params=(cat_filter,))
        else:
            df = pd.read_sql_query("SELECT * FROM books", conn)
            
        conn.close()
        st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------
# 3. ISSUE & RETURN (WITH FINE TRACKING)
# ---------------------------------------------------------
elif choice == "Issue / Return Book":
    st.header("🔄 Issue & Return Operations")
    
    tab_issue, tab_return = st.tabs(["Issue Book", "Return Book"])
    
    with tab_issue:
        st.subheader("Issue a Book")
        conn = sqlite3.connect("library.db")
        books_df = pd.read_sql_query("SELECT id, title, copies FROM books WHERE copies > 0", conn)
        
        if not books_df.empty:
            book_dict = dict(zip(books_df['id'], books_df['title']))
            selected_book_id = st.selectbox("Select Book", options=list(book_dict.keys()), format_func=lambda x: f"{book_dict[x]} (ID: {x})")
            member_name = st.text_input("Borrower Name")
            days_allowed = st.number_input("Loan Duration (Days)", min_value=1, value=14)
            
            if st.button("Issue Book"):
                if member_name:
                    issue_dt = date.today()
                    due_dt = issue_dt + timedelta(days=days_allowed)
                    
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO transactions (book_id, member_name, issue_date, due_date, fine_amount, status)
                        VALUES (?, ?, ?, ?, 0.0, 'Issued')
                    """, (selected_book_id, member_name, str(issue_dt), str(due_dt)))
                    
                    cursor.execute("UPDATE books SET copies = copies - 1 WHERE id = ?", (selected_book_id,))
                    conn.commit()
                    st.success(f"Issued '{book_dict[selected_book_id]}' to {member_name}. Due Date: {due_dt}")
                else:
                    st.error("Please enter borrower name.")
        else:
            st.info("No books currently available for checkout.")
        conn.close()

    with tab_return:
        st.subheader("Return a Book & Process Fine")
        DAILY_FINE_RATE = 1.00  # $1.00 fine per overdue day
        
        conn = sqlite3.connect("library.db")
        tx_df = pd.read_sql_query("SELECT id, member_name, book_id, due_date FROM transactions WHERE status = 'Issued'", conn)
        
        if not tx_df.empty:
            tx_dict = dict(zip(tx_df['id'], tx_df.apply(lambda r: f"TX #{r['id']} | Member: {r['member_name']} | Due: {r['due_date']}", axis=1)))
            selected_tx_id = st.selectbox("Select Active Loan", options=list(tx_dict.keys()), format_func=lambda x: tx_dict[x])
            
            if st.button("Process Return"):
                cursor = conn.cursor()
                cursor.execute("SELECT book_id, due_date FROM transactions WHERE id = ?", (selected_tx_id,))
                row = cursor.fetchone()
                
                b_id, due_date_str = row[0], row[1]
                due_date_obj = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                today_obj = date.today()
                
                # Calculate Fines
                overdue_days = (today_obj - due_date_obj).days
                calculated_fine = max(0.0, overdue_days * DAILY_FINE_RATE)
                
                cursor.execute("""
                    UPDATE transactions 
                    SET return_date = ?, fine_amount = ?, status = 'Returned' 
                    WHERE id = ?
                """, (str(today_obj), calculated_fine, selected_tx_id))
                
                cursor.execute("UPDATE books SET copies = copies + 1 WHERE id = ?", (b_id,))
                conn.commit()
                
                if calculated_fine > 0:
                    st.warning(f"Book Returned! Loan was overdue by {overdue_days} days. Total Fine Charged: ${calculated_fine:.2f}")
                else:
                    st.success("Book Returned on time! No fine charged.")
        else:
            st.info("No active loans pending return.")
        conn.close()

# ---------------------------------------------------------
# 4. FINES & REPORTS
# ---------------------------------------------------------
elif choice == "Fines & Reports":
    st.header("📋 Financial & Audit Records")
    
    conn = sqlite3.connect("library.db")
    tx_all = pd.read_sql_query("""
        SELECT 
            t.id AS "Transaction ID",
            b.title AS "Book Title",
            b.category AS "Category",
            t.member_name AS "Borrower",
            t.issue_date AS "Issue Date",
            t.due_date AS "Due Date",
            t.return_date AS "Return Date",
            t.fine_amount AS "Fine ($)",
            t.status AS "Status"
        FROM transactions t
        JOIN books b ON t.book_id = b.id
    """, conn)
    conn.close()
    
    st.dataframe(tx_all, use_container_width=True)