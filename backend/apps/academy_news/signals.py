"""Any article / photo / author change clears the public cache at once."""
from django.conf import settings
from django.db.models.signals import post_delete, post_save

from .models import Article, ArticlePhoto
from .public import bump_cache_version

for _model in (Article, ArticlePhoto, settings.AUTH_USER_MODEL):
    _name = _model if isinstance(_model, str) else _model.__name__
    post_save.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_news_save_{_name}")
    post_delete.connect(bump_cache_version, sender=_model, dispatch_uid=f"public_news_delete_{_name}")
