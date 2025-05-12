import streamlit as st
import pandas as pd
import openai
import os

# =========================
# 1. File Loader Section
# =========================
# Purpose: Upload and preview CSV file
# UI: st.file_uploader, preview table
# Backend: Read CSV, validate, store in session_state

st.title("Naming Convention Fuckup Nuh Stop Mi!")

uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        st.session_state['df'] = df
        st.success("File uploaded successfully!")
        st.subheader("Preview of uploaded data:")
        st.dataframe(df.head(10))
    except Exception as e:
        st.error(f"Error reading CSV file: {e}")
else:
    if 'df' not in st.session_state:
        st.info("Please upload a CSV file to get started.")
    st.stop()

# =========================
# 2. Input Form for Search Terms
# =========================
# Purpose: User inputs search words/phrases
# UI: Text input (comma/line separated)
# Backend: Parse, validate, store in session_state

st.subheader("Step 2: Enter Keywords")
search_terms_input = st.text_area(
    "Enter keywords or phrases (comma or line separated):",
    value=st.session_state.get('search_terms_raw', ''),
    height=100
)
if st.button("Save Keywords"):
    terms = [t.strip().lower() for t in search_terms_input.replace(',', '\n').split('\n') if t.strip()]
    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        st.error("Please enter at least one keyword.")
    else:
        st.session_state['search_terms'] = unique_terms
        st.session_state['search_terms_raw'] = search_terms_input
        st.success(f"Saved {len(unique_terms)} keyword(s).")
if 'search_terms' in st.session_state:
    bold_terms = [f'**{term}**' for term in st.session_state['search_terms']]
    st.info(f"Current keywords: {', '.join(bold_terms)}")

# =========================
# 3. Column Selector for Search
# =========================
# Purpose: User selects column to search
# UI: Dropdown with column names
# Backend: Validate, store in session_state

if 'df' in st.session_state and 'search_terms' in st.session_state:
    st.subheader("Step 3: Select Column to Search")
    df = st.session_state['df']
    string_columns = [col for col in df.columns if df[col].dtype == object or pd.api.types.is_string_dtype(df[col])]
    if not string_columns:
        st.warning("No string columns found in the uploaded CSV. Please upload a file with at least one text column.")
    else:
        selected_col = st.selectbox("Choose the column to search for your keywords:", string_columns, key="search_col")
        if st.button("Save Search Column"):
            if selected_col not in df.columns:
                st.error("Selected column does not exist.")
            elif df[selected_col].dropna().empty:
                st.warning("The selected column is empty.")
                st.session_state['search_column'] = selected_col
            else:
                st.session_state['search_column'] = selected_col
                st.success(f"Column '{selected_col}' selected for searching.")

# =========================
# 4. Fuzzy Matching for Misspellings/Variants
# =========================
# Purpose: Suggest fuzzy matches for keywords from column values
# UI: Multiselect for user to accept fuzzy matches
# Backend: Use rapidfuzz to find close matches

if (
    'df' in st.session_state and
    'search_terms' in st.session_state and
    'search_column' in st.session_state
):
    st.subheader("Step 4: Find and Select Fuzzy Matches (Misspellings/Variants)")
    st.markdown("""
    In this step, we search for words in your CSV that are potentially misspelled versions of your input keywords. For each keyword you provide, we look for similar words (tokens) in the selected column that might be typos, abbreviations, or variants. Only individual words (split by underscores) are considered for matching.
    """)
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        st.error("The rapidfuzz library is required for fuzzy matching. Please install it with 'pip install rapidfuzz' and restart the app.")
        st.stop()
    df = st.session_state['df']
    col = st.session_state['search_column']
    keywords = st.session_state['search_terms']
    unique_values = df[col].dropna().astype(str).unique()
    tokens = set()
    for val in unique_values:
        tokens.update(val.split('_'))
    tokens = list(tokens)
    fuzzy_matches = {}

    # Dynamic threshold: lower for short keywords, higher for longer
    def get_threshold(word):
        if len(word) <= 2:
            return 50  # very short, allow even more variants
        elif len(word) <= 3:
            return 60
        elif len(word) <= 5:
            return 70
        else:
            return 80

    for keyword in keywords:
        threshold = get_threshold(keyword)
        matches = process.extract(keyword, tokens, scorer=fuzz.ratio, limit=15)
        close_matches = [(m[0], m[1]) for m in matches if m[1] >= threshold and m[0].lower() != keyword.lower()]
        if close_matches:
            fuzzy_matches[keyword] = [m[0] for m in close_matches]
            st.markdown(f"**Fuzzy matches for '{keyword}' (score ≥ {threshold}):**")
            for m in close_matches:
                st.write(f"{m[0]} (score: {m[1]})")
        else:
            st.markdown(f"**No fuzzy matches for '{keyword}' above threshold {threshold}.**")
    selected_fuzzy = {}
    if fuzzy_matches:
        st.info("Review and select fuzzy matches (misspellings/variants) to include in your search. Your original keywords are always included.")
        for keyword, matches in fuzzy_matches.items():
            selected = st.multiselect(
                f"Fuzzy matches for '{keyword}':",
                matches,
                default=matches,
                key=f"fuzzy_{keyword}"
            )
            selected_fuzzy[keyword] = selected
    else:
        st.info("No fuzzy matches found for your keywords in the selected column.")
    if st.button("Save Fuzzy Matches"):
        all_keywords = list(keywords)
        for matchlist in selected_fuzzy.values():
            for m in matchlist:
                if m.lower() not in [t.lower() for t in all_keywords]:
                    all_keywords.append(m)
        st.session_state['accepted_fuzzy_terms'] = all_keywords
        st.success(f"Saved {len(all_keywords)} keywords for next step.")
    if 'accepted_fuzzy_terms' in st.session_state:
        accepted = st.session_state['accepted_fuzzy_terms']
        accepted_display = [f'**{kw}**' if kw in keywords else kw for kw in accepted]
        st.info(f"Accepted keywords: {', '.join(accepted_display)}")

# =========================
# 5. Column Selector for Output
# =========================
# Purpose: Choose/create output column
# UI: Dropdown + new column input
# Backend: Validate/add column, store in session_state

if 'df' in st.session_state and 'accepted_fuzzy_terms' in st.session_state:
    st.subheader("Step 6: Select or Create Output Column")
    df = st.session_state['df']
    columns = list(df.columns)
    default_new_col = "search_result"
    selectbox_options = ["<Create new column>"] + columns
    selected_output_col = st.selectbox(
        "Select an existing column for output or create a new one:",
        options=selectbox_options
    )
    new_col_name = ""
    if selected_output_col == "<Create new column>":
        new_col_name = st.text_input(
            "Enter new column name:",
            value=default_new_col,
            key="new_output_col_name"
        )
    if st.button("Save Output Column"):
        output_col = new_col_name if selected_output_col == "<Create new column>" else selected_output_col
        output_col = output_col.strip()
        if not output_col:
            st.error("Output column name cannot be empty.")
        elif output_col in df.columns and selected_output_col == "<Create new column>":
            st.error(f"Column '{output_col}' already exists. Please choose a different name.")
        else:
            st.session_state['output_column'] = output_col
            if output_col not in df.columns:
                df[output_col] = ""
                st.session_state['df'] = df
            st.success(f"Output column set to '{output_col}'.")
    if 'output_column' in st.session_state:
        pass  # Removed redundant info message about current output column

# =========================
# 6. Python-based Search & Populate
# =========================
# Purpose: Search and populate output column
# Backend: Vectorized search, update DataFrame, error handling

import io

if (
    'df' in st.session_state and
    'search_column' in st.session_state and
    'accepted_fuzzy_terms' in st.session_state and
    'output_column' in st.session_state
):
    st.subheader("Step 7: Search and Populate Output Column (Preview)")
    df = st.session_state['df'].copy()
    search_col = st.session_state['search_column']
    output_col = st.session_state['output_column']
    terms = st.session_state['accepted_fuzzy_terms']
    terms_lower = [t.lower() for t in terms]

    def find_matches(cell):
        if pd.isna(cell):
            return ''
        cell_str = str(cell).lower()
        matches = [t for t in terms_lower if t in cell_str]
        return ', '.join(matches) if matches else ''
    
    df[output_col] = df[search_col].apply(find_matches)

    st.session_state['processed_df'] = df

    preview_df = df[df[output_col].astype(str).str.strip() != '']
    st.success(f"Search complete! Preview of updated '{output_col}' column (showing only rows with matches):")
    st.dataframe(preview_df.head(20))

    if preview_df.empty:
        st.warning("No matches detected in the selected column.")

# =========================
# 7. Download Updated CSV
# =========================
# Purpose: Download processed CSV
# UI: st.download_button
# Backend: Convert to CSV, serve for download, error handling

try:
    if 'processed_df' in st.session_state:
        st.subheader("Step 8: Download Updated CSV")
        default_filename = f"namingconvention_output_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv"
        filename = st.text_input(
            "Enter filename for download (including .csv):",
            value=default_filename,
            key="download_filename"
        )

        csv_buffer = io.StringIO()
        st.session_state['processed_df'].to_csv(csv_buffer, index=False)
        csv_bytes = csv_buffer.getvalue().encode('utf-8')

        st.download_button(
            label=f"Download CSV as {filename}",
            data=csv_bytes,
            file_name=filename,
            mime='text/csv'
        )
except Exception as e:
    st.error(f"An unexpected error occurred during download: {e}")


