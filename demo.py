from src.pipeline.video_pipeline import TrainingPipeline


if __name__ == "__main__":

    video_url = "YOUR_YOUTUBE_URL"
    training_pipeline = TrainingPipeline()
    artifact = training_pipeline.run_pipeline(
        video_url=video_url
    )
    print(artifact)