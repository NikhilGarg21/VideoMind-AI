from src.pipeline.qa_pipeline import QAPipeline
from src.entity.artifact_entity import EmbeddingArtifact


def main():

    embedding_artifact = EmbeddingArtifact(
        index_file_path="artifact/embedding/index.faiss",
        metadata_file_path="artifact/embedding/metadata.json",
    )

    qa_pipeline = QAPipeline(embedding_artifact)

    print("\nQ&A Pipeline Ready!")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if not question:
            continue

        try:
            result = qa_pipeline.ask(question)

            print("\nAnswer:")
            print(result["answer"])

            print("\nSources:")
            for source in result.get("sources", []):
                print(
                    f"{source['start_time']} - {source['end_time']}"
                )

            print()

        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()