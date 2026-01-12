import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(
    page_title="Validador de Credores – PCASP",
    layout="wide"
)

st.title("📊 Validação de Credores – Grupos 7 e 8")
st.caption(
    "Upload de CSV para validação automática entre "
    "Atos Potenciais Ativos (Grupo 7) e sua Execução (Grupo 8)."
)

uploaded_file = st.file_uploader(
    "📤 Envie o arquivo CSV do balancete",
    type=["csv"]
)

# ======================================================
# PROCESSAMENTO COMEÇA AQUI
# ======================================================
if uploaded_file:

    # --- Leitura robusta do CSV ---
    df = pd.read_csv(
        uploaded_file,
        sep=";",
        decimal=",",
        encoding="latin1",
        engine="python"
    )

    # --- Normalização dos nomes das colunas ---
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
    )

    # --- Mapeamento de colunas esperadas ---
    col_mascara = "mascara"
    col_desc = "descricao"
    col_saldo = "saldo atual"
    col_tipo = "tipo saldo"

    # (opcional para depuração)
    # st.write("Colunas detectadas:", df.columns.tolist())

    # --- 1️⃣ Reconstrução da máscara ---
    ultima = None
    completas = []

    for _, row in df.iterrows():
        if pd.notna(row.get(col_mascara)):
            ultima = str(row[col_mascara]).strip()
        completas.append(ultima)

    df["mascara_completa"] = completas

    # --- 2️⃣ Identificação do grupo (7 ou 8) ---
    df["grupo"] = df["mascara_completa"].str.extract(r"^([78])")

    df = df[df["grupo"].isin(["7", "8"])]

    # --- 3️⃣ Normalização da máscara (família lógica) ---
    def normalizar_mascara(m):
        if not isinstance(m, str):
            return None
        partes = m.split(".")
        return ".".join(partes[1:6])  # ignora 7/8 e limita ao nível lógico

    df["mascara_normalizada"] = df["mascara_completa"].apply(normalizar_mascara)

    # --- 4️⃣ Valor para comparação ---
    def valor_comparacao(row):
        if row["grupo"] == "7" and row[col_tipo] == "D":
            return row[col_saldo]
        if row["grupo"] == "8" and row[col_tipo] == "C":
            return row[col_saldo]
        return 0

    df["valor"] = df.apply(valor_comparacao, axis=1)

    # --- Considerar apenas linhas de credor (CNPJ no texto) ---
    df = df[df[col_desc].str.contains(r"\d{11,14}", na=False)]

    # --- 5️⃣ Agrupamento (SOMA automática) ---
    resumo = (
        df.groupby(["mascara_normalizada", col_desc, "grupo"])["valor"]
        .sum()
        .reset_index()
    )

    g7 = resumo[resumo["grupo"] == "7"].rename(columns={"valor": "valor_grupo_7"})
    g8 = resumo[resumo["grupo"] == "8"].rename(columns={"valor": "valor_grupo_8"})

    comparacao = pd.merge(
        g7,
        g8,
        on=["mascara_normalizada", col_desc],
        how="outer"
    ).fillna(0)

    # --- 6️⃣ Validação ---
    comparacao["diferenca"] = (
        comparacao["valor_grupo_7"] - comparacao["valor_grupo_8"]
    )

    comparacao["status"] = comparacao["diferenca"].apply(
        lambda x: "CORRETO" if abs(x) < 0.01 else "DIVERGENTE"
    )

    corretos = comparacao[comparacao["status"] == "CORRETO"]
    divergentes = comparacao[comparacao["status"] == "DIVERGENTE"]

    # --- Exibição ---
    st.subheader("⚠️ Credores com Divergência")
    st.dataframe(divergentes, use_container_width=True)

    # --- Exportação ---
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        corretos.to_excel(writer, sheet_name="Credores Corretos", index=False)
        divergentes.to_excel(writer, sheet_name="Credores com Divergência", index=False)

    st.download_button(
        "📥 Baixar resultado",
        data=output.getvalue(),
        file_name="resultado_validacao_credores.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
