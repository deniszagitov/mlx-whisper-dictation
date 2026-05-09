"""Тесты runtime-адаптера cache скачиваемых моделей."""

from src.infrastructure.model_cache import is_huggingface_model_id


def test_is_huggingface_model_id_accepts_repo_id():
    """Hugging Face repo id должен считаться скачиваемой моделью."""
    assert is_huggingface_model_id("mlx-community/whisper-turbo") is True


def test_is_huggingface_model_id_rejects_local_paths():
    """Локальные пути нельзя автоматически удалять или скачивать как repo id."""
    assert is_huggingface_model_id("/models/whisper") is False
    assert is_huggingface_model_id("~/models/whisper") is False
    assert is_huggingface_model_id("./models/whisper") is False
