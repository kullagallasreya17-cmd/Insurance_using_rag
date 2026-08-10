from langchain_community.document_loaders import PyPDFLoader
import os


def load_documents(folder_path: str = "documents"):

    documents = []

    if not os.path.exists(folder_path):
        print("Documents folder not found.")
        return documents

    for file in os.listdir(folder_path):

        if file.endswith(".pdf"):

            pdf_path = os.path.join(folder_path, file)

            loader = PyPDFLoader(pdf_path)

            documents.extend(loader.load())

    print(f"{len(documents)} pages loaded.")

    return documents