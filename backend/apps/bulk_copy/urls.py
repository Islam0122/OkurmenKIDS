from rest_framework.routers import DefaultRouter

from .views import BulkCopyViewSet

router = DefaultRouter()
router.register("operations", BulkCopyViewSet, basename="bulk-copy")

urlpatterns = router.urls
